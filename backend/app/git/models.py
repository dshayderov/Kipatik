from sqlalchemy import (
    Column, Integer, String, ForeignKey, DateTime, JSON, Table,
    Enum, Boolean, Text, UniqueConstraint, Float,
)
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
import enum
from app.core.crypto import EncryptedString
from app.core.database import Base

# ... (omitted code for brevity, but I must provide the full block in replace)

# Таблица для связи многие-ко-многим между задачами и коммитами
task_commits = Table(
    "task_commits",
    Base.metadata,
    Column("task_id", Integer, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("commit_id", Integer, ForeignKey("git_commits.id", ondelete="CASCADE"), primary_key=True),
)

# Таблица для связи многие-ко-многим между задачами и ветками
task_branches = Table(
    "task_branches",
    Base.metadata,
    Column("task_id", Integer, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("branch_id", Integer, ForeignKey("git_branches.id", ondelete="CASCADE"), primary_key=True),
)

# Таблица для связи многие-ко-многим между задачами и PR
task_pull_requests = Table(
    "task_pull_requests",
    Base.metadata,
    Column("task_id", Integer, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("pull_request_id", Integer, ForeignKey("git_pull_requests.id", ondelete="CASCADE"), primary_key=True),
)

class GitProviderType(str, enum.Enum):
    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"
    GITEA = "gitea"
    GITLAB_CUSTOM = "gitlab_custom"

class PRState(str, enum.Enum):
    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"

class GitAccount(Base):
    """Аккаунты пользователей в Git-сервисах (OAuth)"""
    __tablename__ = "user_git_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    provider = Column(Enum(GitProviderType), nullable=False)
    server_url = Column(String, nullable=True) # NULL для облачных
    
    provider_user_id = Column(String, nullable=True) # ID пользователя в самом Git
    username = Column(String, nullable=True)
    
    access_token = Column(EncryptedString, nullable=False) # шифруется в БД
    refresh_token = Column(EncryptedString, nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", backref=backref("git_accounts", cascade="all, delete-orphan"))

class GitRepository(Base):
    __tablename__ = "git_repositories"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False) # Removed unique=True
    url = Column(String, nullable=False)
    repo_name = Column(String, nullable=True) # e.g. "owner/repo"
    api_url = Column(String, nullable=True) # URL API для Self-hosted инстансов
    # Ветка по умолчанию для сверки и создания feature-веток
    default_branch = Column(String, default="main")
    # Фильтр по путям для монорепозиториев: префиксы через запятую.
    # Пустое значение = репозиторий не фильтруется.
    path_filter = Column(String, nullable=True)
    provider = Column(Enum(GitProviderType), default=GitProviderType.GITHUB)
    
    webhook_id = Column(String, nullable=True)
    webhook_secret = Column(String, nullable=True)
    
    access_token = Column(EncryptedString, nullable=True) # токен синхронизации, шифруется в БД
    is_active = Column(Boolean, default=True)
    connected_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Состояние периодической сверки (reconcile) — для индикатора состояния
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_status = Column(String, default="pending")  # pending | ok | error | skipped
    last_sync_error = Column(Text, nullable=True)
    last_event_at = Column(DateTime(timezone=True), nullable=True)

    # Состояние фонового дооболнения.
    #
    # Сверка (last_sync_*) только забирает коммиты — это быстро. Дальше
    # идёт тяжёлая часть: тексты изменений (отдельный запрос к API
    # провайдера на коммит) и трассировка моделью. Она выполняется в
    # фоне, поэтому пользователю нужно видеть, что процесс идёт, а не
    # что он завис. Отдельный статус, а не флаг в last_sync_status:
    # «загружено успешно» и «разобрано моделью» — разные вещи.
    enrichment_status = Column(String, default="pending")  # pending | running | done | error
    enrichment_total = Column(Integer, default=0)          # сколько коммитов в работе
    enrichment_done = Column(Integer, default=0)           # сколько обработано
    enrichment_error = Column(Text, nullable=True)
    enrichment_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    project = relationship("Project", backref=backref("repositories", cascade="all, delete-orphan")) # Multiple repos per project
    connected_by = relationship("User")
    branches = relationship("Branch", back_populates="repository", cascade="all, delete-orphan")
    commits = relationship("Commit", back_populates="repository", cascade="all, delete-orphan")
    pull_requests = relationship("PullRequest", back_populates="repository", cascade="all, delete-orphan")

class UnlinkedGitEvent(Base):
    """События, которые не удалось привязать к задачам автоматически"""
    __tablename__ = "unlinked_git_events"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("git_repositories.id", ondelete="CASCADE"), nullable=False)
    
    event_type = Column(String, nullable=False) # push, pull_request, etc.
    external_id = Column(String, nullable=True) # SHA коммита или ID PR
    payload = Column(JSON, nullable=False)
    
    status = Column(String, default="pending") # pending, linked, ignored
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    repository = relationship("GitRepository")

class GitEventLog(Base):
    """Лог всех входящих вебхуков для аудита"""
    __tablename__ = "git_events_log"

    # Провайдеры повторяют доставку при таймаутах. Идентификатор доставки
    # защищает от повторной обработки одного и того же события.
    __table_args__ = (
        UniqueConstraint("repository_id", "delivery_id", name="uq_git_events_log_delivery"),
    )

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("git_repositories.id", ondelete="CASCADE"), nullable=True) # Может быть анонимным если не найден репозиторий
    
    provider = Column(String, nullable=True)
    event_type = Column(String, nullable=True)
    payload = Column(JSON, nullable=True)
    headers = Column(JSON, nullable=True)

    # Факт проверки подписи (ранее индикатор в /git/verify был захардкожен)
    signature_verified = Column(Boolean, default=False, nullable=False)
    # ID доставки провайдера — основа для дедупликации повторных отправок
    delivery_id = Column(String, nullable=True, index=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Commit(Base):
    __tablename__ = "git_commits"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("git_repositories.id", ondelete="CASCADE"), nullable=False)
    
    sha = Column(String, nullable=False, index=True)
    message = Column(String)
    author = Column(String)
    # Атрибуция автора: пользователь системы, сопоставленный по email.
    # Nullable — коммит может сделан пользователем, удалённым из системы.
    author_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    # Email автора из репозитория: основной ключ сопоставления с пользователем
    author_email = Column(String, nullable=True, index=True)
    timestamp = Column(DateTime(timezone=True))
    
    meta_data = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Тип коммита по модели анализа кода: bugfix | feature | refactor |
    # docs | test | chore. Считается один раз при привязке коммита
    # к задаче и хранится здесь, а не пересчитывается при открытии
    # карточки: классификация на CPU занимает сотни миллисекунд,
    # и в запросе карточки это было бы заметно.
    commit_type = Column(String, nullable=True)
    commit_type_confidence = Column(Float, nullable=True)
    commit_type_at = Column(DateTime(timezone=True), nullable=True)

    repository = relationship("GitRepository", back_populates="commits")
    tasks = relationship("Task", secondary=task_commits, back_populates="commits")
    author_user = relationship("User", foreign_keys=[author_id])

class Branch(Base):
    __tablename__ = "git_branches"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("git_repositories.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    repository = relationship("GitRepository", back_populates="branches")
    tasks = relationship("Task", secondary=task_branches, back_populates="branches")

class PullRequest(Base):
    __tablename__ = "git_pull_requests"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("git_repositories.id", ondelete="CASCADE"), nullable=False)
    external_id = Column(Integer, nullable=False) # ID из GitHub/GitLab
    
    title = Column(String, nullable=False)
    state = Column(Enum(PRState), default=PRState.OPEN)
    url = Column(String)
    source_branch = Column(String)
    target_branch = Column(String)
    merged_at = Column(DateTime(timezone=True), nullable=True)

    # Агрегированные данные PR для карточки задачи
    additions = Column(Integer, default=0)
    deletions = Column(Integer, default=0)
    changed_files = Column(Integer, default=0)
    # Список ревьюеров: [{login, state, requested_at?}]
    reviewers = Column(JSON, nullable=True)
    # Сводный статус CI: success | failure | pending | unknown
    ci_status = Column(String, nullable=True)
    ci_url = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    repository = relationship("GitRepository", back_populates="pull_requests")
    tasks = relationship("Task", secondary=task_pull_requests, back_populates="pull_requests")


class GitAuthorMapping(Base):
    """Сопоставление Git-автора с пользователем системы.

    Автоматика (email / логин провайдера) работает не всегда: у разработчика
    может быть личный почтовый адрес в коммитах, другой логин на self-hosted
    GitLab или аккаунт, удалённый из системы. Здесь хранятся явные
    (в том числе ручные) сопоставления, чтобы привязка не зависела от угадывания.
    """
    __tablename__ = "git_author_mappings"

    __table_args__ = (
        UniqueConstraint("repository_id", "author_key", name="uq_git_author_mappings_repo_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    # NULL = правило действует во всех репозиториях системы
    repository_id = Column(Integer, ForeignKey("git_repositories.id", ondelete="CASCADE"), nullable=True)

    # Нормализованный ключ автора (lowercase). Обычно это email.
    author_key = Column(String, nullable=False, index=True)
    author_name = Column(String, nullable=True)
    author_email = Column(String, nullable=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # auto_email | auto_username | manual
    source = Column(String, default="manual", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User")


class CommitFile(Base):
    """Файл, изменённый в коммите.

    Нужен для блока «Изменённые файлы» в карточке задачи и для
    фильтра монорепозиториев по путям.
    """
    __tablename__ = "commit_files"

    __table_args__ = (
        UniqueConstraint("commit_id", "path", name="uq_commit_files_commit_path"),
    )

    id = Column(Integer, primary_key=True, index=True)
    commit_id = Column(Integer, ForeignKey("git_commits.id", ondelete="CASCADE"), nullable=False, index=True)

    path = Column(String, nullable=False)
    previous_path = Column(String, nullable=True)  # для переименований
    # added | modified | removed | renamed
    status = Column(String, default="modified")
    additions = Column(Integer, default=0)
    deletions = Column(Integer, default=0)
    # Текст правок по файлу. Модели анализа кода обучались на нём,
    # поэтому без него они видят только имя файла. Держим ограниченной
    # длины: у одного коммита суммарно патчи легко занимают сотни КБ.
    patch = Column(Text, nullable=True)
    # Правка не получена целиком (обрезана или недоступна у провайдера)
    patch_truncated = Column(Boolean, default=False)

    commit = relationship("Commit", backref=backref("files", cascade="all, delete-orphan"))


class TaskGitLink(Base):
    """Провенанс связи задачи с объектом Git.

    Раньше связь была «голая» Many-to-Many, поэтому было невозможно
    отличить «нашлось по регулярке #123» от «человек подтвердил вручную»
    и нельзя было отозвать одну связь, не удаляя общую строку.

    link_type: commit | branch | pull_request
    source:    regex | pr | branch | manual | model
    """
    __tablename__ = "task_git_links"

    __table_args__ = (
        UniqueConstraint(
            "task_id", "link_type", "target_id", name="uq_task_git_links_unique"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)

    link_type = Column(String, nullable=False)
    # Внешний ключ в соответствующую таблицу (git_commits / git_branches / git_pull_requests)
    target_id = Column(Integer, nullable=False, index=True)

    # regex | pr | branch | manual | model
    source = Column(String, default="regex", nullable=False)
    # Уверенность 0..1 — заполняется моделью трассировки
    confidence = Column(Float, nullable=True)
    # Кто подтвердил связь вручную
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # proposed | confirmed | rejected
    #
    # Предложение модели не является фактом: пока статус proposed,
    # коммит не показывается в блоке «Разработка» как связанный.
    # Только подтверждённые связи участвуют в оценке прогресса.
    status = Column(String, default="confirmed", nullable=False)
    # Почему связь предложена — показывается пользователю
    reason = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    created_by = relationship("User")
