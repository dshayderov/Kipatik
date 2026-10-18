import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, Table, DateTime, Enum as SQLEnum, BigInteger, Boolean, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base

class InviteStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"

class ProjectInvite(Base):
    __tablename__ = "project_invites"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id"))
    inviter_id = Column(Integer, ForeignKey("users.id"))
    role = Column(String, default="developer")
    status = Column(SQLEnum(InviteStatus), default=InviteStatus.PENDING)
    created_at = Column(DateTime, default=datetime.utcnow)

    inviter = relationship("User", foreign_keys=[inviter_id])
    user = relationship("User", foreign_keys=[user_id])

class ProjectMember(Base):
    __tablename__ = "project_members"
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=True)
    role = Column(String, default="developer") # Keep for backward compatibility or remove later

    role_obj = relationship("Role")

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)
    permissions = Column(String, nullable=False, default="[]") # JSON list of strings
    is_system = Column(Boolean, default=False)

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    description = Column(String)
    git_url = Column(String)
    
    owner_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="projects")
    
    # Участники проекта
    members = relationship("User", secondary="project_members", backref="joined_projects", overlaps="project_members")
    project_members = relationship("ProjectMember", backref="project", cascade="all, delete-orphan", overlaps="members,joined_projects")
    
    # Каждый проект имеет одну основную Kanban-доску
    board = relationship("Board", back_populates="project", uselist=False, cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")

    # Квоты на хранение файлов
    storage_used_bytes = Column(BigInteger, default=0)
    # Лимит на проект. Значение по умолчанию берётся из настроек
    # хранилища (storage_settings.default_project_limit_mb), поэтому
    # поле nullable: иначе 500 МБ осталось бы зашитым в модели и
    # изменение администратором не действовало бы на новые проекты.
    storage_limit_bytes = Column(BigInteger, nullable=True)

    # Фон страницы проекта. Общий для всех участников: меняют его те
    # же, кто меняет название, — право project:edit.
    #
    # Вид и адрес хранятся раздельно. Адресом владеет исключительно
    # загрузка файла: так строка вида "custom" не может остаться без
    # картинки, а значит и без битого фона.
    #   none    — белый, как было до этого поля;
    #   default — базовый фон, входящий в поставку;
    #   custom  — загруженный руководителем проекта.
    background = Column(String, nullable=False, server_default="none", default="none")
    background_url = Column(String)

    rules = Column(JSON, default={
        "required_fields": ["title"], # title is always required by default
        "auto_assign_on_move": False,
        "column_role_locks": {}, # {column_id: [roles]}
        "start_date_logic": "created_at" # created_at, manual_pm, manual_assignee
    })
