from typing import Any, Dict, List, Optional
import asyncio
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.api import deps
from app.core.config import settings
from sqlalchemy import func
from app.git.tasks import process_git_webhook
from app.git.models import (
    GitRepository, GitProviderType, UnlinkedGitEvent, GitEventLog,
    Commit, Branch, PullRequest, task_commits,
    task_branches, task_pull_requests,
)
from app.tasks.models import Task
from app.users.models import User
from sqlalchemy import select, desc
import hashlib
import hmac
import secrets as pysecrets
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class UnlinkedEventSchema(BaseModel):
    id: int
    event_type: str
    external_id: Optional[str] = None
    payload: Dict
    created_at: datetime
    class Config: from_attributes = True

class VerificationResult(BaseModel):
    repo_found: bool = False
    # Секрет настроен — без него вебхуки не принимаются
    secret_configured: bool = False
    # Приходят ли события (по логу доставок)
    event_received: bool = False
    # Прошла ли подпись последнего принятого события проверку
    signature_verified: bool = False
    last_event_at: Optional[datetime] = None
    last_event_verified_at: Optional[datetime] = None
    # Состояние периодической сверки (reconcile)
    last_sync_at: Optional[datetime] = None
    last_sync_status: str = "pending"
    last_sync_error: Optional[str] = None


def generate_webhook_secret() -> str:
    """Генерирует секрет для HMAC-подписи вебхуков"""
    return pysecrets.token_hex(32)

async def _assert_repo_access(db: AsyncSession, current_user: User, project_id: int) -> None:
    """Проверяет, что пользователь — участник проекта (или суперпользователь)."""
    from app.projects.models import ProjectMember

    member_res = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == current_user.id,
        )
    )
    if member_res.scalar_one_or_none() is None and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not a member of this project")


@router.get("/unlinked/{project_id}", response_model=List[UnlinkedEventSchema])
async def get_unlinked_events(
    project_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """Получить список непривязанных событий для проекта"""
    await _assert_repo_access(db, current_user, project_id)

    repo_result = await db.execute(select(GitRepository).filter(GitRepository.project_id == project_id))
    repo_ids = [r.id for r in repo_result.scalars().all()]
    
    if not repo_ids:
        return []

    result = await db.execute(
        select(UnlinkedGitEvent)
        .filter(UnlinkedGitEvent.repository_id.in_(repo_ids), UnlinkedGitEvent.status == "pending")
        .order_by(desc(UnlinkedGitEvent.created_at))
        .limit(50)
    )
    return result.scalars().all()

@router.post("/verify/{repository_id}", response_model=VerificationResult)
async def verify_repository(
    repository_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """Проверка статуса подключения репозитория.

    Все флаги отражают фактическое состояние. Раньше webhook_registered и
    signature_verified возвращались как True при наличии любой записи в логе,
    что делало индикатор бесполезным.
    """
    result = await db.execute(select(GitRepository).filter(GitRepository.id == repository_id))
    repo = result.scalar_one_or_none()

    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    await _assert_repo_access(db, current_user, repo.project_id)

    res = VerificationResult(
        repo_found=True,
        secret_configured=bool(repo.webhook_secret),
        last_sync_at=repo.last_sync_at,
        last_sync_status=repo.last_sync_status or "pending",
        last_sync_error=repo.last_sync_error,
    )

    log_result = await db.execute(
        select(GitEventLog)
        .filter(GitEventLog.repository_id == repository_id)
        .order_by(desc(GitEventLog.created_at))
    )
    last_log = log_result.scalars().first()

    if last_log:
        res.event_received = True
        res.last_event_at = last_log.created_at
        res.signature_verified = bool(last_log.signature_verified)
        if last_log.signature_verified:
            res.last_event_verified_at = last_log.created_at

    return res

@router.post("/link-event/{event_id}/{task_id}")
async def link_git_event_manually(
    event_id: int,
    task_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """Вручную привязать непривязанное событие к задаче"""
    # 1. Находим событие
    result = await db.execute(select(UnlinkedGitEvent).filter(UnlinkedGitEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # 2. Находим репозиторий
    result = await db.execute(select(GitRepository).filter(GitRepository.id == event.repository_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    # 3. Проверяем доступ к проекту репозитория
    await _assert_repo_access(db, current_user, repo.project_id)

    # 4. Находим задачу
    result = await db.execute(select(Task).filter(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 5. Проверяем проект
    if task.project_id != repo.project_id:
        raise HTTPException(status_code=400, detail="Task and Repository belong to different projects")

    # 5. Привязываем
    from app.git.base import GitEvent
    git_event = GitEvent.model_validate(event.payload)
    
    # В зависимости от типа события привязываем коммиты или PR
    from app.git.services import TaskLinkingService, GitEventService
    
    if git_event.type == "push":
        for commit_dto in git_event.commits:
            # Ищем или создаем коммит
            res = await db.execute(select(Commit).filter(Commit.sha == commit_dto.sha, Commit.repository_id == repo.id))
            commit = res.scalar_one_or_none()
            if not commit:
                commit = Commit(
                    repository_id=repo.id,
                    sha=commit_dto.sha,
                    message=commit_dto.message,
                    author=commit_dto.author,
                    timestamp=commit_dto.timestamp,
                    meta_data={"url": commit_dto.url}
                )
                db.add(commit)
                await db.flush()
            
            if commit not in task.commits:
                task.commits.append(commit)
                
    elif git_event.type == "pull_request":
        if git_event.pull_request:
            await GitEventService.process_pull_request(db, repo, git_event.pull_request, [task_id])

    # 6. Помечаем событие как привязанное
    event.status = "linked"
    
    await db.commit()
    return {"status": "success"}

class TokenCheckRequest(BaseModel):
    provider: GitProviderType
    token: Optional[str] = None


class TokenCheckResult(BaseModel):
    ok: bool
    supported: bool = True
    username: Optional[str] = None
    error: Optional[str] = None


class WebhookStatus(BaseModel):
    repository_id: int
    auto_register_supported: bool = True
    callback_url: str
    secret_configured: bool = False
    webhook_id: Optional[str] = None
    registered_remotely: bool = False
    remote_webhooks: List[Dict] = []
    message: Optional[str] = None


def _callback_url(repository_id: int) -> str:
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    return f"{base}{settings.API_V1_STR}/git/webhook/{repository_id}"


async def _load_repo(db: AsyncSession, repository_id: int, current_user: User) -> GitRepository:
    result = await db.execute(
        select(GitRepository).filter(GitRepository.id == repository_id)
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    await _assert_repo_access(db, current_user, repo.project_id)
    return repo


@router.post("/token/check", response_model=TokenCheckResult)
async def check_provider_token(
    body: TokenCheckRequest,
    current_user: User = Depends(deps.get_current_user),
):
    """Шаг мастера подключения: проверка токена до привязки репозитория."""
    from app.git.factory import get_git_provider

    try:
        provider = get_git_provider(body.provider, token=body.token)
        result = await provider.validate_token()
    except Exception as exc:
        return TokenCheckResult(ok=False, error=f"{type(exc).__name__}: {exc}")
    return TokenCheckResult(**result)


@router.get("/{repository_id}/webhook", response_model=WebhookStatus)
async def get_webhook_status(
    repository_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Состояние вебхука: наш секрет, зарегистрирован ли он у провайдера."""
    repo = await _load_repo(db, repository_id, current_user)
    status = WebhookStatus(
        repository_id=repo.id,
        callback_url=_callback_url(repo.id),
        secret_configured=bool(repo.webhook_secret),
        webhook_id=repo.webhook_id,
    )

    from app.git.factory import get_git_provider

    if repo.access_token:
        try:
            provider = get_git_provider(
                repo.provider, token=repo.access_token, api_url=repo.api_url
            )
            hooks = await provider.list_webhooks(repo.id)
            status.remote_webhooks = hooks
            status.registered_remotely = any(
                h.get("url") == status.callback_url for h in hooks
            )
        except Exception as exc:
            status.message = f"Не удалось получить список вебхуков: {exc}"

    if not status.registered_remotely:
        status.message = status.message or (
            "Вебхук не зарегистрирован у провайдера. "
            "Нажмите «Зарегистрировать автоматически» или настройте вручную."
        )
    return status


@router.post("/{repository_id}/sync")
async def sync_repository_now(
    repository_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Запустить сверку и дождаться разбора.

    Без этого кнопка «подключить» выглядит рабочей, но данных не видно:
    ближайшая фоновая сверка — через GIT_SYNC_INTERVAL_SECONDS (5 минут),
    и в разработке ждать её неудобно.

    Сверка отвечает за секунды, а разбор моделью — минуты. Поэтому запрос
    ждёт конца фоновой доработки, но не дольше ENRICHMENT_WAIT_SECONDS:
    иначе пользователь нажал кнопку и сразу ушёл, а предложения появились
    бы через полминуты на пустом месте.

    Возвращаем 200 даже при status=error — ошибка уже записана в
    last_sync_error, и клиенту она нужнее, чем код ответа.
    """
    from app.git.services import (
        ENRICHMENT_WAIT_SECONDS,
        SyncService,
        _enrichment_running,
    )

    repo = await _load_repo(db, repository_id, current_user)

    stats = await SyncService.sync_repository(db, repo)

    # Ждём фоновую доработку, но с потолком: если модель считает дольше,
    # отдаём управление и показываем прогресс — он обновится позже.
    waited = 0.0
    poll = 0.5
    while repository_id in _enrichment_running and waited < ENRICHMENT_WAIT_SECONDS:
        await asyncio.sleep(poll)
        waited += poll

    # Обновляем объект: и сверка, и доработка могли поменять статус
    await db.refresh(repo)

    return {
        **stats,
        "last_sync_status": repo.last_sync_status,
        "last_sync_error": repo.last_sync_error,
        "default_branch": repo.default_branch,
        "enrichment_status": repo.enrichment_status,
        "enrichment_total": repo.enrichment_total,
        "enrichment_done": repo.enrichment_done,
        "enrichment_error": repo.enrichment_error,
        "waited_seconds": round(waited, 1),
        "still_running": repository_id in _enrichment_running,
    }


@router.post("/{repository_id}/webhook/register", response_model=WebhookStatus)
async def register_repository_webhook(
    repository_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Автоматически зарегистрировать вебхук через API провайдера."""
    if not settings.GIT_WEBHOOK_AUTO_REGISTER:
        raise HTTPException(status_code=503, detail="Авторегистрация отключена")

    repo = await _load_repo(db, repository_id, current_user)

    if not repo.webhook_secret:
        repo.webhook_secret = generate_webhook_secret()
        await db.commit()
        await db.refresh(repo)

    if not repo.access_token:
        raise HTTPException(
            status_code=400,
            detail="Нет токена провайдера — укажите его в профиле",
        )

    from app.git.factory import get_git_provider

    provider = get_git_provider(
        repo.provider, token=repo.access_token, api_url=repo.api_url
    )
    callback = _callback_url(repo.id)

    try:
        result = await provider.register_webhook(repo.id, callback, repo.webhook_secret)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Провайдер отклонил регистрацию: {exc}"
        )

    if not result.get("supported", True):
        # Провайдер не поддерживает авторегистрацию — показываем ручной путь
        return WebhookStatus(
            repository_id=repo.id,
            auto_register_supported=False,
            callback_url=callback,
            secret_configured=True,
            message=(
                "Этот провайдер не поддерживает авторегистрацию. "
                "Скопируйте URL и секрет и настройте вебхук вручную."
            ),
        )

    repo.webhook_id = result.get("id")
    await db.commit()
    await db.refresh(repo)

    return WebhookStatus(
        repository_id=repo.id,
        callback_url=callback,
        secret_configured=True,
        webhook_id=repo.webhook_id,
        registered_remotely=True,
        remote_webhooks=[result],
        message=(
            "Вебхук уже был зарегистрирован"
            if result.get("already_exists")
            else "Вебхук зарегистрирован"
        ),
    )


@router.delete("/{repository_id}/webhook")
async def unregister_repository_webhook(
    repository_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Удалить вебхук на стороне провайдера."""
    repo = await _load_repo(db, repository_id, current_user)

    if repo.webhook_id and repo.access_token:
        from app.git.factory import get_git_provider

        try:
            provider = get_git_provider(
                repo.provider, token=repo.access_token, api_url=repo.api_url
            )
            await provider.delete_webhook(repo.id, repo.webhook_id)
        except Exception:
            # Не ломаем отключение: провайдер мог уже удалить хук сам
            pass

    repo.webhook_id = None
    await db.commit()
    return {"status": "success"}


class AuthorEntry(BaseModel):
    author_key: str
    author_name: Optional[str] = None
    author_email: Optional[str] = None
    commits: int = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    source: Optional[str] = None


class MappingStats(BaseModel):
    total_commits: int = 0
    attributed_commits: int = 0
    distinct_authors: int = 0
    unmatched_authors: int = 0
    auto_matched_authors: int = 0


class AuthorsReport(BaseModel):
    repository_id: int
    authors: List[AuthorEntry] = []
    stats: MappingStats = MappingStats()


class MappingCreate(BaseModel):
    author_key: str
    user_id: int
    scope: str = "repository"  # repository | global
    apply_to_existing: bool = True


class MappingResult(BaseModel):
    status: str
    author_key: Optional[str] = None
    updated_commits: int = 0
    scanned_commits: Optional[int] = None


@router.get("/{repository_id}/authors", response_model=AuthorsReport)
async def get_repository_authors(
    repository_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Список авторов коммитов репозитория с признаком распознавания.

    Нужен, чтобы увидеть, чьи коммиты система не смогла сопоставить:
    у разработчика может быть личная почта, другой логин или удалённый аккаунт.
    """
    repo = await _load_repo(db, repository_id, current_user)

    from app.git.author_mapping import AuthorMappingService

    report = await AuthorMappingService.analyze(db, repo.id)
    return AuthorsReport(**report)


@router.get("/{repository_id}/authors/candidates")
async def get_author_candidates(
    repository_id: int,
    q: str = "",
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Пользователи, которым можно сопоставить автора (для выпадающего списка)."""
    await _load_repo(db, repository_id, current_user)

    from app.models import User

    query = select(User).filter(User.is_active.is_(True))
    if q:
        pattern = f"%{q.lower()}%"
        query = query.where(
            func.lower(User.email).like(pattern) | func.lower(func.coalesce(User.full_name, "")).like(pattern)
        )
    result = await db.execute(query.limit(50))
    users = result.scalars().all()
    return [
        {"id": u.id, "full_name": u.full_name, "email": u.email, "avatar_url": u.avatar_url}
        for u in users
    ]


@router.post("/{repository_id}/authors/map", response_model=MappingResult)
async def map_git_author(
    repository_id: int,
    body: MappingCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Сопоставить Git-автора с пользователем системы (вручную).

    Правило сохраняется, поэтому следующие коммиты этого автора будут
    атрибутированы автоматически. Уже сохранённые коммиты обновляются
    по умолчанию.
    """
    repo = await _load_repo(db, repository_id, current_user)

    from app.git.author_mapping import AuthorMappingService

    scope_repo_id = None if body.scope == "global" else repo.id
    try:
        result = await AuthorMappingService.set_mapping(
            db,
            scope_repo_id,
            body.author_key,
            body.user_id,
            source="manual",
            apply_to_existing=body.apply_to_existing and scope_repo_id is not None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return MappingResult(**result)


@router.post("/{repository_id}/authors/rematch", response_model=MappingResult)
async def rematch_git_authors(
    repository_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Прогнать все неатрибутированные коммиты через текущие правила."""
    repo = await _load_repo(db, repository_id, current_user)

    from app.git.author_mapping import AuthorMappingService

    result = await AuthorMappingService.rematch_all(db, repo.id)
    return MappingResult(**result)


@router.delete("/{repository_id}/authors/{mapping_id}")
async def delete_author_mapping(
    repository_id: int,
    mapping_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Удалить правило сопоставления.

    Коммиты не переатрибутируются обратно: author_id остаётся, чтобы
    не терять уже показанную пользователю историю.
    """
    await _load_repo(db, repository_id, current_user)

    from app.git.models import GitAuthorMapping
    from app.git.author_mapping import AuthorMappingService

    mapping = (
        await db.execute(
            select(GitAuthorMapping).filter(GitAuthorMapping.id == mapping_id)
        )
    ).scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    await AuthorMappingService.delete_mapping(db, mapping_id)
    return {"status": "success"}


class CommitFileSchema(BaseModel):
    path: str
    previous_path: Optional[str] = None
    status: str = "modified"
    additions: int = 0
    deletions: int = 0


class LinkInfo(BaseModel):
    id: int
    link_type: str
    target_id: int
    source: str
    confidence: Optional[float] = None
    created_by: Optional[str] = None
    created_at: datetime


class TaskCommitSchema(BaseModel):
    id: int
    sha: str
    message: str
    author: Optional[str] = None
    author_id: Optional[int] = None
    timestamp: Optional[datetime] = None
    url: Optional[str] = None
    additions: int = 0
    deletions: int = 0
    files: List[CommitFileSchema] = []
    # Тип по модели (ЛР №3): bugfix | feature | refactor | docs | test | chore.
    # reliable=False означает, что класс входит в число тех, где
    # классификатор проверен — для остальных тип ориентировочный.
    commit_type: Optional[str] = None
    commit_type_confidence: Optional[float] = None
    commit_type_reliable: bool = False
    # Провенанс связи с задачей
    link_id: Optional[int] = None
    link_source: Optional[str] = None
    link_status: Optional[str] = None
    confidence: Optional[float] = None
    created_by: Optional[str] = None


class TaskPRSchema(BaseModel):
    id: int
    external_id: int
    title: str
    state: str
    url: Optional[str] = None
    source_branch: Optional[str] = None
    target_branch: Optional[str] = None
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0
    reviewers: List[Dict] = []
    ci_status: Optional[str] = None
    ci_url: Optional[str] = None
    link_id: Optional[int] = None
    link_source: Optional[str] = None


class TaskBranchSchema(BaseModel):
    id: int
    name: str
    link_id: Optional[int] = None
    link_source: Optional[str] = None


class RejectedLinkSchema(BaseModel):
    link_id: int
    target_id: int
    sha: str
    commit_message: str
    reason: Optional[str] = None
    rejected_at: Optional[datetime] = None


class TaskDevCard(BaseModel):
    task_id: int
    branches: List[TaskBranchSchema] = []
    pull_requests: List[TaskPRSchema] = []
    commits: List[TaskCommitSchema] = []
    files: List[CommitFileSchema] = []
    totals: Dict = {}
    # Отклонённые моделью привязки: человек отказался, но может
    # пересмотреть. В основном списке их нет намеренно.
    rejected: List[RejectedLinkSchema] = []


async def _load_task_with_access(db: AsyncSession, task_id: int, current_user: User):
    result = await db.execute(select(Task).filter(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await _assert_task_view_access_for_repo(db, current_user, task)
    return task


async def _assert_repo_admin(db: AsyncSession, repository_id: int, current_user: User) -> None:
    """Требует права администратора проекта, которому принадлежит репозиторий.

    Дозаполнение правок ходит в API провайдера от имени пользователя,
    поэтому вклад в лимиты делает тот, кто запустил. Просить на это
    обычного участника проекта нельзя.
    """
    from app.core.roles import Permission
    from app.projects.models import Project, ProjectMember

    repo = (
        await db.execute(select(GitRepository).where(GitRepository.id == repository_id))
    ).scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    if current_user.is_superuser:
        return

    member = (
        await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == repo.project_id,
                ProjectMember.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this project")

    role = (
        await db.execute(select(Project).where(Project.id == repo.project_id))
    ).scalar_one_or_none()

    from app.core.roles import ROLE_PERMISSIONS

    allowed = ROLE_PERMISSIONS.get(member.role, set())
    if Permission.PROJECT_CONNECT_REPO not in allowed:
        raise HTTPException(
            status_code=403,
            detail="Недостаточно прав для загрузки правок в репозитории",
        )


async def _assert_task_view_access_for_repo(db: AsyncSession, current_user: User, task: Task) -> None:
    from app.projects.models import ProjectMember

    member_res = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == task.project_id,
            ProjectMember.user_id == current_user.id,
        )
    )
    if member_res.scalar_one_or_none() is None and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not a member of this project")


@router.get("/task/{task_id}/card", response_model=TaskDevCard)
async def get_task_dev_card(
    task_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Данные блока «Разработка» карточки задачи.

    Ветки, PR, коммиты и изменённые файлы вместе с провенансом каждой связи.
    """
    from app.git.models import CommitFile, TaskGitLink

    await _load_task_with_access(db, task_id, current_user)

    # Карта провенанса: (link_type, target_id) -> link
    link_rows = (
        await db.execute(select(TaskGitLink).where(TaskGitLink.task_id == task_id))
    ).scalars().all()

    # Предложения модели показываются отдельным блоком и ждут решения.
    # Пока пользователь их не принял, в «Коммиты» они попадать не должны:
    # иначе блок утверждал бы то, чего ещё не подтвердили.
    all_links = link_rows
    # Показываются подтверждённые связи. Отклонённые уходят в отдельный
    # список: человек их отклонил, но возможность пересмотреть нужна —
    # иначе отказ становится необратимым.
    rejected_links = [l for l in all_links if l.status == "rejected"]
    link_rows = [
        l for l in all_links if l.status not in ("proposed", "rejected")
    ]

    links = {(x.link_type, x.target_id): x for x in link_rows}

    creator_names = {}
    user_ids = {x.created_by_id for x in all_links if x.created_by_id}
    if user_ids:
        from app.models import User as _U
        for u in (await db.execute(select(_U).filter(_U.id.in_(user_ids)))).scalars().all():
            creator_names[u.id] = u.full_name or u.email

    # Коммиты
    commits_res = await db.execute(
        select(Commit).filter(Commit.id.in_([tid for (lt, tid) in links if lt == "commit"] or [0]))
    )
    commits = commits_res.scalars().all()

    commit_out: List[TaskCommitSchema] = []
    for c in sorted(commits, key=lambda x: x.timestamp or datetime.min, reverse=True):
        link = links.get(("commit", c.id))
        files = (
            await db.execute(select(CommitFile).where(CommitFile.commit_id == c.id))
        ).scalars().all()

        # Тип коммита: модель определила его один раз при привязке
        from app.git.commit_types import describe as describe_type

        kind = describe_type(c, None)

        commit_out.append(
            TaskCommitSchema(
                id=c.id,
                sha=c.sha,
                message=c.message or "",
                author=c.author,
                author_id=c.author_id,
                timestamp=c.timestamp,
                url=(c.meta_data or {}).get("url"),
                additions=sum(f.additions or 0 for f in files),
                deletions=sum(f.deletions or 0 for f in files),
                files=[
                    CommitFileSchema(
                        path=f.path,
                        previous_path=f.previous_path,
                        status=f.status or "modified",
                        additions=f.additions or 0,
                        deletions=f.deletions or 0,
                    )
                    for f in files
                ],
                commit_type=kind["type"],
                commit_type_confidence=kind["confidence"],
                commit_type_reliable=kind["reliable"],
                link_id=link.id if link else None,
                link_source=link.source if link else None,
                link_status=link.status if link else None,
                confidence=link.confidence if link else None,
                created_by=creator_names.get(link.created_by_id) if link else None,
            )
        )

    # PR
    prs = (
        await db.execute(
            select(PullRequest).filter(
                PullRequest.id.in_([tid for (lt, tid) in links if lt == "pull_request"] or [0])
            )
        )
    ).scalars().all()
    pr_out = []
    for pr in sorted(prs, key=lambda x: x.id, reverse=True):
        link = links.get(("pull_request", pr.id))
        pr_out.append(
            TaskPRSchema(
                id=pr.id,
                external_id=pr.external_id,
                title=pr.title,
                state=pr.state.value if hasattr(pr.state, "value") else str(pr.state),
                url=pr.url,
                source_branch=pr.source_branch,
                target_branch=pr.target_branch,
                additions=pr.additions or 0,
                deletions=pr.deletions or 0,
                changed_files=pr.changed_files or 0,
                reviewers=pr.reviewers or [],
                ci_status=pr.ci_status,
                ci_url=pr.ci_url,
                link_id=link.id if link else None,
                link_source=link.source if link else None,
            )
        )

    # Ветки
    branches = (
        await db.execute(
            select(Branch).filter(
                Branch.id.in_([tid for (lt, tid) in links if lt == "branch"] or [0])
            )
        )
    ).scalars().all()
    br_out = [
        TaskBranchSchema(
            id=b.id,
            name=b.name,
            link_id=links[("branch", b.id)].id if ("branch", b.id) in links else None,
            link_source=links[("branch", b.id)].source if ("branch", b.id) in links else None,
        )
        for b in branches
    ]

    # Все изменённые файлы по задаче (для сводного списка)
    all_commit_ids = [c.id for c in commits]
    files_out: List[CommitFileSchema] = []
    seen_paths = set()
    if all_commit_ids:
        for f in (
            await db.execute(
                select(CommitFile).where(CommitFile.commit_id.in_(all_commit_ids))
            )
        ).scalars().all():
            if f.path in seen_paths:
                continue
            seen_paths.add(f.path)
            files_out.append(
                CommitFileSchema(
                    path=f.path,
                    previous_path=f.previous_path,
                    status=f.status or "modified",
                    additions=f.additions or 0,
                    deletions=f.deletions or 0,
                )
            )
    files_out.sort(key=lambda x: x.path)

    # Отклонённые привязки — отдельным списком, с теми же данными,
    # что нужны для показа. Связь может остаться и на удалённый
    # коммит (у target_id нет внешнего ключа), такие пропускаем.
    rejected_out: List[RejectedLinkSchema] = []
    rejected_ids = [l.target_id for l in rejected_links]
    if rejected_ids:
        rej_commits = {
            c.id: c
            for c in (
                await db.execute(select(Commit).where(Commit.id.in_(rejected_ids)))
            ).scalars().all()
        }
        for l in rejected_links:
            commit = rej_commits.get(l.target_id)
            if commit is None:
                continue
            rejected_out.append(
                RejectedLinkSchema(
                    link_id=l.id,
                    target_id=l.target_id,
                    sha=commit.sha,
                    commit_message=commit.message or "",
                    reason=l.reason,
                )
            )

    return TaskDevCard(
        task_id=task_id,
        branches=br_out,
        pull_requests=pr_out,
        commits=commit_out,
        files=files_out,
        rejected=rejected_out,
        totals={
            "commits": len(commit_out),
            "files": len(files_out),
            "additions": sum(c.additions for c in commit_out),
            "deletions": sum(c.deletions for c in commit_out),
        },
    )


class PatchBackfillRequest(BaseModel):
    limit: Optional[int] = None


class PatchBackfillResult(BaseModel):
    status: str
    enabled: bool
    examined: int = 0
    filled: int = 0
    skipped: int = 0
    failed: int = 0
    patches_saved: int = 0
    characters_saved: int = 0
    errors: List[str] = []


@router.post("/{repository_id}/patches/backfill", response_model=PatchBackfillResult)
async def backfill_patches(
    repository_id: int,
    request: PatchBackfillRequest = PatchBackfillRequest(),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Дозаполнить тексты изменений у коммитов репозитория.

    Нужны моделям анализа кода: без них модель видит только имена файлов.
    Каждый коммит — отдельный запрос к API провайдера, поэтому запуск
    ограничен по числу коммитов и делается вручную.
    """
    from app.git.patches import backfill_commit_patches

    result = await db.execute(
        select(GitRepository).where(GitRepository.id == repository_id)
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    await _assert_repo_admin(db, repository_id, current_user)

    stats = await backfill_commit_patches(db, repo, limit=request.limit)
    if not stats["enabled"] and stats["examined"]:
        # Явное предупреждение: пользователь мог не заметить выключенный флаг
        stats["errors"].append("GIT_FETCH_PATCHES=false — включите в .env")
    return PatchBackfillResult(status="success", **stats)


class LinkCreate(BaseModel):
    link_type: str  # commit | branch | pull_request
    target_id: int


class LinkDeleteResult(BaseModel):
    status: str
    link_id: int


@router.post("/task/{task_id}/links", response_model=LinkInfo)
async def create_task_git_link(
    task_id: int,
    body: LinkCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Привязать объект Git к задаче вручную («Перепривязать»)."""
    from app.git.models import Commit, Branch, PullRequest, TaskGitLink
    from app.git.services import TaskLinkingService
    from app.core.roles import Permission
    from app.tasks.api import get_member_and_check_permission

    task = await _load_task_with_access(db, task_id, current_user)
    await get_member_and_check_permission(
        db, current_user.id, task.project_id, Permission.TASK_GIT_LINK
    )

    # Проверка «уже привязан» делается запросом к ассоциативной таблице,
    # а не через task.commits / task.branches / task.pull_requests.
    # Обращение к relationship после уже выполненного execute()
    # инвалидирует объект задачи, и ленивая загрузка уходит вне greenlet —
    # ровно тот MissingGreenlet, из-за которого ручная привязка не работала
    # вообще: эндпоинт отвечал 500, а окно выбора показывалось пустым.
    models_and_tables = {
        "commit": (Commit, task_commits),
        "branch": (task_branches, task_branches),
        "pull_request": (PullRequest, task_pull_requests),
    }

    if body.link_type not in models_and_tables:
        raise HTTPException(status_code=400, detail="Unknown link_type")

    model, table = models_and_tables[body.link_type]
    obj = (
        await db.execute(select(model).filter(model.id == body.target_id))
    ).scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail=f"{body.link_type} not found")

    target_column = "commit_id" if body.link_type == "commit" else (
        "branch_id" if body.link_type == "branch" else "pull_request_id"
    )

    already = (
        await db.execute(
            select(table.c.task_id).where(
                table.c.task_id == task_id,
                table.c[target_column] == body.target_id,
            )
        )
    ).scalar_one_or_none()
    if already is None:
        await db.execute(
            table.insert().values(task_id=task_id, **{target_column: body.target_id})
        )

    await TaskLinkingService.record_link(
        db, task.id, body.link_type, body.target_id,
        source="manual", created_by_id=current_user.id,
    )
    await db.commit()

    link = (
        await db.execute(
            select(TaskGitLink).where(
                TaskGitLink.task_id == task.id,
                TaskGitLink.link_type == body.link_type,
                TaskGitLink.target_id == body.target_id,
            )
        )
    ).scalar_one()
    return LinkInfo(
        id=link.id,
        link_type=link.link_type,
        target_id=link.target_id,
        source=link.source,
        confidence=link.confidence,
        created_by=current_user.full_name or current_user.email,
        created_at=link.created_at,
    )


@router.delete("/task/{task_id}/links/{link_id}", response_model=LinkDeleteResult)
async def delete_task_git_link(
    task_id: int,
    link_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Отвязать объект Git от задачи («Отвязать»).

    Связь удаляется и из провенанса, и из M2M-таблиц, чтобы объект
    действительно перестал показываться в карточке.
    """
    from app.git.models import Commit, Branch, PullRequest, TaskGitLink
    from app.core.roles import Permission
    from app.tasks.api import get_member_and_check_permission

    task = await _load_task_with_access(db, task_id, current_user)
    await get_member_and_check_permission(
        db, current_user.id, task.project_id, Permission.TASK_GIT_LINK
    )

    link = (
        await db.execute(
            select(TaskGitLink).filter(
                TaskGitLink.id == link_id, TaskGitLink.task_id == task_id
            )
        )
    ).scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    if link.link_type == "commit":
        obj = (await db.execute(select(Commit).filter(Commit.id == link.target_id))).scalar_one_or_none()
        if obj and obj in task.commits:
            task.commits.remove(obj)
    elif link.link_type == "branch":
        obj = (await db.execute(select(Branch).filter(Branch.id == link.target_id))).scalar_one_or_none()
        if obj and obj in task.branches:
            task.branches.remove(obj)
    elif link.link_type == "pull_request":
        obj = (await db.execute(select(PullRequest).filter(PullRequest.id == link.target_id))).scalar_one_or_none()
        if obj and obj in task.pull_requests:
            task.pull_requests.remove(obj)

    await db.delete(link)
    await db.commit()
    return LinkDeleteResult(status="success", link_id=link_id)


@router.get("/task/{task_id}/unlinked-candidates")
async def get_task_unlinked_candidates(
    task_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Коммиты и PR проекта, ещё не связанные с задачей — для «Перепривязать»."""
    from app.git.models import Commit, GitRepository, PullRequest, TaskGitLink

    task = await _load_task_with_access(db, task_id, current_user)

    # Раньше здесь стояли два бага сразу: TaskGitLink не импортировался,
    # а строки выборки распаковывались как пары (link_type, target_id),
    # хотя select() отдаёт ORM-объекты. Эндпоинт падал с 500, а окно
    # выбора показывалось пустым — ошибку съедал catch на фронтенде.
    links = (
        await db.execute(
            select(
                TaskGitLink.link_type, TaskGitLink.target_id, TaskGitLink.status
            ).where(TaskGitLink.task_id == task_id)
        )
    ).all()

    # Предложения тоже исключаются: коммит, уже предложенный этой
    # задаче, повторно предлагать незачем. Отклонённые, наоборот,
    # показываются — иначе отказ был бы тупиком, из которого
    # вернуть коммит вручную нечем.
    linked_commits = {
        tid for (lt, tid, st) in links
        if lt == "commit" and st != "rejected"
    }
    linked_prs = {tid for (lt, tid, st) in links if lt == "pull_request" and st != "rejected"}

    repo_ids = [
        r.id for r in (
            await db.execute(select(GitRepository).filter(GitRepository.project_id == task.project_id))
        ).scalars().all()
    ]

    commits_out = []
    if repo_ids:
        for c in (
            await db.execute(
                select(Commit).filter(
                    Commit.repository_id.in_(repo_ids),
                    Commit.id.notin_(linked_commits or {0}),
                ).order_by(Commit.timestamp.desc()).limit(50)
            )
        ).scalars().all():
            commits_out.append(
                {"id": c.id, "sha": c.sha, "message": c.message, "author": c.author}
            )

    prs_out = []
    if repo_ids:
        for pr in (
            await db.execute(
                select(PullRequest).filter(
                    PullRequest.repository_id.in_(repo_ids),
                    PullRequest.id.notin_(linked_prs or {0}),
                ).order_by(PullRequest.id.desc()).limit(50)
            )
        ).scalars().all():
            prs_out.append(
                {"id": pr.id, "external_id": pr.external_id, "title": pr.title, "state": str(pr.state)}
            )

    return {"commits": commits_out, "pull_requests": prs_out}


async def verify_github_signature(request: Request, secret: str):
    """Проверка подписи GitHub вебхука"""
    signature = request.headers.get("X-Hub-Signature-256")
    if not signature:
        raise HTTPException(status_code=403, detail="Missing GitHub signature")
    
    body = await request.body()
    expected_signature = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=403, detail="Invalid GitHub signature")

async def verify_gitlab_signature(request: Request, secret: str):
    """Проверка подписи GitLab вебхука"""
    signature = request.headers.get("X-Gitlab-Token")
    if not signature:
        raise HTTPException(status_code=403, detail="Missing GitLab token")
    
    if not hmac.compare_digest(signature, secret):
        raise HTTPException(status_code=403, detail="Invalid GitLab token")

async def verify_gitea_signature(request: Request, secret: str):
    """Проверка подписи Gitea вебхука"""
    # Gitea может отправлять подпись в X-Gitea-Signature
    signature = request.headers.get("X-Gitea-Signature")
    if not signature:
        # Если подписи нет, но секрет задан - это ошибка безопасности
        raise HTTPException(status_code=403, detail="Missing Gitea signature")
    
    body = await request.body()
    # Gitea использует HMAC-SHA256
    expected_signature = hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=403, detail="Invalid Gitea signature")

@router.post("/webhook/{repository_id}")
async def git_webhook(
    repository_id: int,
    request: Request,
    x_github_event: str = Header(None, alias="X-GitHub-Event"),
    x_gitlab_event: str = Header(None, alias="X-GitLab-Event"),
    x_gitea_event: str = Header(None, alias="X-Gitea-Event"),
    x_github_delivery: str = Header(None, alias="X-GitHub-Delivery"),
    x_gitlab_delivery: str = Header(None, alias="X-Gitlab-Event-UUID"),
    db: AsyncSession = Depends(deps.get_db)
) -> Any:
    """Прием вебхука от Git-провайдера"""
    # 1. Проверяем существование репозитория
    result = await db.execute(select(GitRepository).filter(GitRepository.id == repository_id))
    repo = result.scalar_one_or_none()
    
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    # 2. Проверка безопасности.
    #    Секрет обязателен: без него доставка принималась без проверки подписи,
    #    и любой мог подделать push и размазать задачи по колонкам.
    if not repo.webhook_secret:
        raise HTTPException(
            status_code=503,
            detail="Webhook secret is not configured for this repository",
        )

    signature_verified = True
    try:
        if repo.provider == GitProviderType.GITHUB:
            await verify_github_signature(request, repo.webhook_secret)
        elif repo.provider in [GitProviderType.GITLAB, GitProviderType.GITLAB_CUSTOM]:
            await verify_gitlab_signature(request, repo.webhook_secret)
        elif repo.provider == GitProviderType.GITEA:
            await verify_gitea_signature(request, repo.webhook_secret)
        elif repo.provider == GitProviderType.BITBUCKET:
            # У Bitbucket своя схема подписи, провайдер пока не реализует парсинг
            signature_verified = False
        else:
            signature_verified = False
    except HTTPException:
        raise
    except Exception:
        signature_verified = False

    # 3. Получаем Payload
    payload = await request.json()

    # 4. Определяем тип события
    event_type = "push" # default
    if repo.provider == GitProviderType.GITHUB:
        event_type = x_github_event or "push"
    elif repo.provider in [GitProviderType.GITLAB, GitProviderType.GITLAB_CUSTOM]:
        event_type = x_gitlab_event or "push"
    elif repo.provider == GitProviderType.GITEA:
        event_type = x_gitea_event or "push"

    # Идентификатор доставки — основа для дедупликации повторных отправок
    delivery_id = x_github_delivery or x_gitlab_delivery

    # 5. Отправляем в очередь (Celery)
    process_git_webhook.delay(
        repository_id, payload, event_type, signature_verified, delivery_id
    )

    return {"status": "accepted"}

# --------------------------------------------------------------------- #
# Трассировка по смыслу изменений (второй эшелон)
#
# Модель не создаёт факты, а предлагает. Предложение лежит со статусом
# proposed и не попадает в блок «Разработка» и в оценку прогресса,
# пока пользователь не подтвердит его.
# --------------------------------------------------------------------- #
class TraceSuggestRequest(BaseModel):
    limit: Optional[int] = None


class TraceSuggestResult(BaseModel):
    status: str
    enabled: bool = True
    examined: int = 0
    proposed: int = 0
    already_linked: int = 0
    below_threshold: int = 0
    skipped: int = 0
    no_patches: int = 0
    reasons: List[str] = []


class SuggestionOut(BaseModel):
    link_id: int
    task_id: int
    task_title: str
    commit_id: int
    sha: str
    commit_message: str
    confidence: Optional[float] = None
    reason: Optional[str] = None
    source: str = "model"
    created_at: Optional[datetime] = None
    # Время самого коммита, а не момента создания предложения:
    # по нему список выстраивается в порядке работы.
    commit_timestamp: Optional[datetime] = None


class SuggestionDecision(BaseModel):
    status: str
    link_id: int
    task_id: int


async def _links_with_status(
    db: AsyncSession,
    project_id: int,
    task_id: Optional[int] = None,
    repository_id: Optional[int] = None,
):
    """Предложения проекта с указанным статусом.

    task_id сужает выборку до одной задачи, repository_id — до одного
    репозитория. Проверка принадлежности задачи проекту остаётся общей:
    чужая задача не должна открываться по её номеру из другого проекта.

    Ограничение по репозиторию обязательно: связи хранят только
    target_id, поэтому без него предложения одного репозитория
    попадали в карточку задачи, выбранную по другому репозиторию, —
    и переключатель репозитория в карточке ничего не менял.
    """
    from app.git.models import Commit as _C
    from app.git.models import TaskGitLink as _L
    from app.tasks.models import Task as _T

    task_ids = (
        await db.execute(select(_T.id).where(_T.project_id == project_id))
    ).scalars().all()
    if not task_ids:
        return []
    if task_id is not None:
        if task_id not in task_ids:
            return []
        task_ids = [task_id]

    stmt = (
        select(_L)
        .join(_C, _C.id == _L.target_id)
        .where(
            _L.task_id.in_(task_ids),
            _L.status == "proposed",
            _L.link_type == "commit",
        )
    )
    if repository_id is not None:
        stmt = stmt.where(_C.repository_id == repository_id)
    return (await db.execute(stmt)).scalars().all()


@router.post("/{repository_id}/trace/suggest", response_model=TraceSuggestResult)
async def suggest_traces(
    repository_id: int,
    request: TraceSuggestRequest = TraceSuggestRequest(),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Подобрать привязки для коммитов, которые регулярки пропустили.

    Требует правки репозитория: модель работает на CPU и запрос занимает
    сотни миллисекунд на коммит, запускать это должен человек, а не фон.
    """
    from app.git.tracing import suggest_for_unlinked_commits

    result = await db.execute(
        select(GitRepository).where(GitRepository.id == repository_id)
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    await _assert_repo_admin(db, repository_id, current_user)

    limit = request.limit if request.limit is not None else settings.GIT_TRACE_SYNC_LIMIT
    stats = await suggest_for_unlinked_commits(db, repo, max(1, min(limit, 100)))
    return TraceSuggestResult(status="success", **stats)


@router.get("/{repository_id}/suggestions", response_model=List[SuggestionOut])
async def list_suggestions(
    repository_id: int,
    task_id: Optional[int] = None,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Предложения модели по репозиторию — ждут подтверждения.

    task_id ограничивает выдачу предложениями одной задачи. Карточка
    задачи показывает именно свои: без фильтра каждая задача проекта
    видела все предложения репозитория, и пользователь решал в чужой
    карточке за чужие изменения.
    """
    from app.git.models import Commit, TaskGitLink
    from app.projects.models import Project
    from app.tasks.models import Task

    repo = (
        await db.execute(select(GitRepository).where(GitRepository.id == repository_id))
    ).scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    project = (
        await db.execute(select(Project).where(Project.id == repo.project_id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Смотреть предложения может любой участник проекта — это не изменение
    from app.projects.models import ProjectMember

    if not current_user.is_superuser:
        member = (
            await db.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == project.id,
                    ProjectMember.user_id == current_user.id,
                )
            )
        ).scalar_one_or_none()
        if not member:
            raise HTTPException(status_code=403, detail="Not a member of this project")

    links = await _links_with_status(
        db, repo.project_id, task_id, repository_id=repository_id
    )

    if not links:
        return []

    tasks = {
        t.id: t
        for t in (
            await db.execute(
                select(Task).where(Task.id.in_([l.task_id for l in links]))
            )
        ).scalars().all()
    }
    commits = {
        c.id: c
        for c in (
            await db.execute(
                select(Commit).where(Commit.id.in_([l.target_id for l in links]))
            )
        ).scalars().all()
    }

    out: List[SuggestionOut] = []
    ordered: List[tuple] = []
    for l in links:
        task = tasks.get(l.task_id)
        commit = commits.get(l.target_id)
        if not task or not commit:
            continue
        out.append(
            SuggestionOut(
                link_id=l.id,
                task_id=task.id,
                task_title=task.title,
                commit_id=commit.id,
                sha=commit.sha,
                commit_message=commit.message or "",
                confidence=l.confidence,
                reason=l.reason,
                source=l.source,
                created_at=l.created_at,
                commit_timestamp=commit.timestamp,
            )
        )
        ordered.append((commit.timestamp, l.confidence, len(out) - 1))

    # Предложения идут в порядке работы: от раннего коммита к позднему.
    # По уверенности список читался прыжками — сначала свежий коммит,
    # потом возвращение к тому, что шёл до него, и одна задача вроде
    # «заголовки», «пустое значение», «разделитель» распадалась на
    # несвязанные куски. Уверенность остаётся вторым ключом: при
    # одинаковом времени она по-прежнему видна в бейдже.
    ordered.sort(key=lambda x: (x[0] is None, x[0] or datetime.min, -(x[1] or 0)))
    return [out[i] for _, _, i in ordered]


# Маршрут объявлен раньше /suggestions/{link_id}/{decision} не случайно:
# иначе «restore» был бы разобран как значение decision, и возвращал бы
# 400 «decision must be confirm or reject».
@router.post("/suggestions/{link_id}/restore", response_model=SuggestionDecision)
async def restore_suggestion(
    link_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Возвращает отклонённое предложение к рассмотрению.

    Отказ — это ответ человека модели, а не удаление коммита из
    системы. Иногда решение нужно пересмотреть: коммит могли внести
    уже после отказа, или человек отклонил по невнимательности.
    Поэтому отказ обратим.
    """
    from app.core.roles import Permission
    from app.git.models import TaskGitLink
    from app.tasks.api import get_member_and_check_permission

    link = (
        await db.execute(select(TaskGitLink).where(TaskGitLink.id == link_id))
    ).scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    if link.status != "rejected":
        raise HTTPException(
            status_code=400, detail="Связь не отклонена — восстанавливать нечего"
        )

    task = (
        await db.execute(select(Task).filter(Task.id == link.task_id))
    ).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    await get_member_and_check_permission(
        db, current_user.id, task.project_id, Permission.TASK_GIT_LINK
    )

    # Атрибуты ставятся до execute(): запрос к таблице инвалидирует
    # объекты сессии, и обращение к link после него потребовало бы
    # перезагрузки вне greenlet.
    link.status = "proposed"
    link.reason = "Возвращено к рассмотрению"

    # Строка в task_commits возвращается обязательно. Её создаёт
    # propose_link вместе с предложением, а отклонение удаляет — и без
    # этого возврата цикл «скрыть → вернуть» менял счётчик на вкладке
    # «Разработка» на единицу в меньшую сторону навсегда: предложение
    # снова было на месте, а бейдж помнил, что его якобы не было.
    if link.link_type == "commit":
        present = (
            await db.execute(
                select(task_commits.c.task_id).where(
                    task_commits.c.task_id == link.task_id,
                    task_commits.c.commit_id == link.target_id,
                )
            )
        ).scalar()
        if present is None:
            await db.execute(
                task_commits.insert().values(
                    task_id=link.task_id, commit_id=link.target_id
                )
            )

    await db.commit()
    return SuggestionDecision(status="proposed", link_id=link.id, task_id=link.task_id)


@router.post("/suggestions/{link_id}/{decision}", response_model=SuggestionDecision)
async def decide_suggestion(
    link_id: int,
    decision: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Подтвердить или скрыть предложение модели.

    decision: confirm | reject
    """
    from app.core.roles import Permission
    from app.git.models import Commit, TaskGitLink
    from app.tasks.api import get_member_and_check_permission

    if decision not in ("confirm", "reject"):
        raise HTTPException(status_code=400, detail="decision must be confirm or reject")

    link = (
        await db.execute(select(TaskGitLink).where(TaskGitLink.id == link_id))
    ).scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    task = (
        await db.execute(
            select(Task).filter(Task.id == link.task_id)
        )
    ).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    await get_member_and_check_permission(
        db, current_user.id, task.project_id, Permission.TASK_GIT_LINK
    )

    if decision == "confirm":
        # source отвечает на вопрос «как связь найдена», status — «подтвердил
        # ли человек». Раньше подтверждение переписывало source в "manual",
        # и после нажатия «Принять» бейдж «модель» исчезал навсегда: по
        # карточке нельзя было понять, что коммит сопоставила модель.
        # Признак ручного подтверждения — сам status и created_by_id.
        #
        # Исключение — предложение, найденное регуляркой: там source
        # остаётся "regex", и решение человека тоже должно быть видно.
        link.status = "confirmed"
        link.created_by_id = current_user.id

        # Запись в task_commits обеспечиваем здесь, а не полагаемся на
        # то, что предложение её создало: карточка читает коммиты через
        # task_git_links, и если m2m останется пустой, данные будут
        # разъезжаться — часть кода смотрит в одно, часть в другое.
        if link.link_type == "commit":
            exists = (
                await db.execute(
                    select(task_commits.c.task_id).where(
                        task_commits.c.task_id == link.task_id,
                        task_commits.c.commit_id == link.target_id,
                    )
                )
            ).scalar()
            if exists is None:
                await db.execute(
                    task_commits.insert().values(
                        task_id=link.task_id, commit_id=link.target_id
                    )
                )

        await db.commit()

        # Тип считаем сразу после подтверждения. Иначе бейдж в карточке
        # появился бы только при следующей синхронизации, и выглядело бы
        # так, будто подтверждение не сработало. Коммитов мало, модель
        # на них уходит на секунды.
        if link.link_type == "commit" and settings.CODE_MODEL_ENABLED:
            from app.git.services import TaskLinkingService

            await TaskLinkingService.classify_new_links(db, [link.target_id])

        return SuggestionDecision(status="confirmed", link_id=link.id, task_id=link.task_id)

    # Скрыть: связь помечается отклонённой, а не удаляется.
    #
    # Раньше строка удалялась целиком, и это ломало две вещи. Первая:
    # модель при следующей сверке предлагала тот же коммит в ту же задачу
    # снова — предложение не исчезало, а возвращалось по кругу. Вторая:
    # отклонённый коммит нельзя было потом привязать вручную, потому что
    # ручная привязка опирается на существующую строку связи.
    #
    # Через ассоциативную таблицу, а не task.commits: после commit
    # сессия сбрасывает состояние связи, и обращение к ней потребовало бы
    # IO вне greenlet — тот же MissingGreenlet, что и в трассировке.
    # Атрибуты ставятся ДО запроса к ассоциативной таблице: execute()
    # инвалидирует объекты сессии, и обращение к link после него
    # потребовало бы перезагрузки вне greenlet — тот же MissingGreenlet,
    # что уже возникал в этом файле.
    link.status = "rejected"
    link.reason = "Отклонено пользователем"
    link.created_by_id = current_user.id

    if link.link_type == "commit":
        await db.execute(
            task_commits.delete().where(
                task_commits.c.task_id == link.task_id,
                task_commits.c.commit_id == link.target_id,
            )
        )

    await db.commit()
    return SuggestionDecision(status="rejected", link_id=link.id, task_id=link.task_id)



class CommitTypeBackfillResult(BaseModel):
    status: str
    examined: int = 0
    classified: int = 0
    failed: int = 0


@router.post("/{repository_id}/commit-types/backfill", response_model=CommitTypeBackfillResult)
async def backfill_commit_types(
    repository_id: int,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Определить тип для привязанных коммитов, у которых его ещё нет.

    Нужно для коммитов, привязанных до включения классификатора, и для
    тех, чей тип не удалось посчитать в момент привязки.
    """
    result = await db.execute(
        select(GitRepository).where(GitRepository.id == repository_id)
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    await _assert_repo_admin(db, repository_id, current_user)

    from app.git.commit_types import backfill_commit_types as _backfill

    stats = await _backfill(
        db, repo_id=repository_id, limit=max(1, min(limit or 50, 200))
    )
    return CommitTypeBackfillResult(status="success", **stats)
