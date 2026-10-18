from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, desc, text
from sqlalchemy.orm import selectinload
from typing import List, Literal, Optional
from pydantic import BaseModel
from app.core.database import get_db
from app.api import deps
from app.models import User, Notification
from app.git.models import GitRepository, GitProviderType
from app.projects.models import Project, ProjectMember, ProjectInvite, InviteStatus
from app.core.roles import Permission, ProjectRole, ROLE_PERMISSIONS
from app.schemas.user import User as UserSchema, ProjectMember as ProjectMemberSchema
from app.notifications.services import NotificationService
from app.notifications.models import NotificationType
from datetime import datetime
import os
import shutil

router = APIRouter()
# ... (existing code)

from app.schemas.role import Role as RoleSchema
from app.api.v1.endpoints.git import generate_webhook_secret

@router.get("/roles", response_model=List[RoleSchema])
async def get_available_roles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    Get all available project roles.
    """
    from app.projects.models import Role
    result = await db.execute(select(Role))
    return result.scalars().all()

@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    # Удалять может только владелец или суперюзер. 
    # Даже если у PROJECT_MANAGER есть право PROJECT_DELETE, удаление всего проекта - критичная операция.
    # Но для гибкости проверим право PROJECT_DELETE.
    
    # Получаем членство текущего пользователя
    member_res = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == current_user.id
        )
    )
    member = member_res.scalar_one_or_none()
    
    # Если не участник, проверяем is_superuser
    if not member and not current_user.is_superuser:
         raise HTTPException(status_code=403, detail="Permission denied")
         
    if member:
        allowed_permissions = ROLE_PERMISSIONS.get(member.role, set())
        if Permission.PROJECT_DELETE not in allowed_permissions and not current_user.is_superuser:
             raise HTTPException(status_code=403, detail="Permission denied")

    # Физическое удаление файлов
    project_files_path = os.path.join("uploads", "projects", str(project_id))
    if os.path.exists(project_files_path):
        try:
            shutil.rmtree(project_files_path)
        except Exception as e:
            print(f"Error deleting project files: {e}")

    await db.delete(project)
    await db.commit()
    return {"status": "success", "message": "Project deleted"}

class ProjectInviteSchema(BaseModel):
    id: int
    project_id: int
    user_id: int
    inviter_id: int
    role: str
    status: str
    created_at: datetime
    user: Optional[UserSchema] = None
    class Config: from_attributes = True

class GitRepositorySchema(BaseModel):
    id: int
    url: str
    repo_name: Optional[str] = None
    api_url: Optional[str] = None
    default_branch: Optional[str] = "main"
    path_filter: Optional[str] = None
    provider: GitProviderType
    webhook_id: Optional[str] = None
    webhook_secret: Optional[str] = None
    is_active: Optional[bool] = True
    connected_by_id: Optional[int] = None
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    last_event_at: Optional[datetime] = None
    # Фоновая доработка: правки и разбор моделью. Отдельный статус,
    # потому что «коммиты загружены» и «разбор закончен» — разные вещи,
    # и без отдельного поля интерфейс не отличит «работает» от «зависло».
    enrichment_status: Optional[str] = None
    enrichment_total: Optional[int] = 0
    enrichment_done: Optional[int] = 0
    enrichment_error: Optional[str] = None
    enrichment_at: Optional[datetime] = None
    class Config: from_attributes = True

class GitRepositoryCreate(BaseModel):
    url: str
    repo_name: Optional[str] = None
    api_url: Optional[str] = None
    provider: GitProviderType = GitProviderType.GITHUB
    webhook_secret: Optional[str] = None
    # Ветка по умолчанию обязана приниматься здесь: мастер подключения
    # присылает её с первого шага. Раньше поле не было в схеме, Pydantic
    # его отбрасывал, и репозиторий создавался с веткой main из
    # дефолта модели — синхронизация потом искала несуществующую ветку.
    default_branch: Optional[str] = None
    path_filter: Optional[str] = None


class GitRepositoryUpdate(BaseModel):
    url: Optional[str] = None
    repo_name: Optional[str] = None
    api_url: Optional[str] = None
    default_branch: Optional[str] = None
    path_filter: Optional[str] = None
    webhook_secret: Optional[str] = None
    is_active: Optional[bool] = None
    regenerate_secret: bool = False

class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    git_url: str | None = None

class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    git_url: str | None = None
    # Вид фона. Значение "custom" здесь запрещено намеренно: файл
    # загружается отдельным запросом, и только он выставляет custom
    # вместе с адресом. Принимать custom здесь значило бы разрешить
    # поставить вид без картинки — то есть битый фон.
    background: Literal["none", "default"] | None = None

class ProjectSchema(BaseModel):
    id: int
    name: str
    description: str | None = None
    git_url: str | None = None
    background: str = "none"
    background_url: str | None = None
    repositories: List[GitRepositorySchema] = []
    owner_id: int
    user_role: Optional[str] = None # Роль текущего пользователя в проекте
    members: Optional[List[UserSchema]] = None
    class Config: from_attributes = True

@router.get("/", response_model=List[ProjectSchema])
async def read_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    # Показываем проекты, где пользователь является участником
    query = (
        select(Project, ProjectMember.role)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == current_user.id)
        .options(selectinload(Project.repositories), selectinload(Project.members).selectinload(User.git_accounts))
    )
    result = await db.execute(query)
    rows = result.all()
    
    projects = []
    for project, role in rows:
        project.user_role = role
        projects.append(project)
        
    return projects

@router.post("/", response_model=ProjectSchema)
async def create_project(
    project_in: ProjectCreate, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    if not current_user.can_create_projects and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="You do not have permission to create projects")
        
    project = Project(
        name=project_in.name, 
        description=project_in.description, 
        git_url=project_in.git_url, 
        owner_id=current_user.id
    )
    db.add(project)
    await db.flush() # Получаем ID проекта
    
    # Добавляем владельца в список участников с ролью project_manager
    from app.projects.models import Role
    role_res = await db.execute(select(Role).where(Role.name == ProjectRole.PROJECT_MANAGER))
    pm_role = role_res.scalar_one_or_none()
    
    member = ProjectMember(
        project_id=project.id,
        user_id=current_user.id,
        role=ProjectRole.PROJECT_MANAGER,
        role_id=pm_role.id if pm_role else None
    )
    db.add(member)
    
    await db.commit()
    
    # Re-fetch to load relationships
    result = await db.execute(
        select(Project)
        .where(Project.id == project.id)
        .options(selectinload(Project.repositories), selectinload(Project.members).selectinload(User.git_accounts))
    )
    created_project = result.scalar_one()
    created_project.user_role = ProjectRole.PROJECT_MANAGER

    return created_project

@router.get("/{project_id}", response_model=ProjectSchema)
async def read_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    result = await db.execute(
        select(Project, ProjectMember.role)
        .join(ProjectMember, (ProjectMember.project_id == Project.id) & (ProjectMember.user_id == current_user.id))
        .where(Project.id == project_id)
        .options(selectinload(Project.repositories), selectinload(Project.members).selectinload(User.git_accounts))
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found or access denied")
    
    project, role = row
    project.user_role = role
    return project

async def _token_for_provider(
    db: AsyncSession,
    user_id: int,
    provider: GitProviderType,
    server_url: str | None = None,
) -> str | None:
    """Токен провайдера: сначала OAuth, затем личный токен (PAT).

    Раньше здесь читались колонки users.*_token напрямую, из-за чего
    OAuth-токен (он лежит в user_git_accounts) никогда не использовался.
    """
    from app.git.token_resolver import resolve_user_token

    return await resolve_user_token(db, user_id, provider, server_url)


def _schedule_initial_sync(repo_id: int) -> None:
    """Запускает первичную сверку в фоне.

    Синхронизация идёт в СВОЕЙ сессии: раньше сюда передавалась сессия запроса,
    которая закрывается после ответа, и фоновая задача падала на закрытой сессии.
    """
    import asyncio

    async def _run() -> None:
        from app.core.database import SessionLocal
        from app.git.models import GitRepository as _Repo
        from app.git.services import SyncService
        from sqlalchemy import select as _select

        async with SessionLocal() as session:
            found = await session.execute(_select(_Repo).filter(_Repo.id == repo_id))
            repo_obj = found.scalar_one_or_none()
            if repo_obj:
                await SyncService.sync_repository(session, repo_obj)

    try:
        asyncio.create_task(_run())
    except RuntimeError:
        # Нет работающего event loop (например, в тестах/скриптах)
        pass


@router.get("/{project_id}/repositories", response_model=List[GitRepositorySchema])
async def read_project_repositories(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    member: ProjectMember = Depends(deps.check_permission(Permission.PROJECT_VIEW)),
):
    """Список всех репозиториев проекта (проект может иметь несколько)."""
    result = await db.execute(
        select(GitRepository).where(GitRepository.project_id == project_id)
    )
    return result.scalars().all()


@router.post("/{project_id}/repositories", response_model=GitRepositorySchema)
async def create_project_repository(
    project_id: int,
    repo_in: GitRepositoryCreate,
    db: AsyncSession = Depends(get_db),
    member: ProjectMember = Depends(deps.check_permission(Permission.PROJECT_CONNECT_REPO)),
):
    """Привязать Git-репозиторий к проекту.

    Один проект может иметь несколько репозиториев. Повторный вызов с тем же
    URL обновляет существующую запись, с новым — создаёт дополнительную.
    Раньше здесь был scalar_one_or_none() по всем репозиториям проекта,
    что падало, как только репозиториев становилось больше одного.
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one()

    result = await db.execute(select(User).where(User.id == member.user_id))
    current_user = result.scalar_one()

    token = await _token_for_provider(
        db, current_user.id, repo_in.provider, repo_in.api_url
    )

    result = await db.execute(
        select(GitRepository).where(
            GitRepository.project_id == project_id,
            GitRepository.url == repo_in.url,
        )
    )
    existing_repo = result.scalar_one_or_none()

    if existing_repo:
        existing_repo.repo_name = repo_in.repo_name or existing_repo.repo_name
        existing_repo.api_url = repo_in.api_url
        existing_repo.provider = repo_in.provider
        # Ветку и фильтр обновляем только если их прислали: повторное
        # подключение того же URL не должно затирать настройки, заданные
        # ранее через PATCH.
        if repo_in.default_branch:
            existing_repo.default_branch = repo_in.default_branch
        if repo_in.path_filter is not None:
            existing_repo.path_filter = repo_in.path_filter
        # Секрет для подписи вебхуков генерируется автоматически, если
        # пользователь не задал его сам: без секрета доставка не проходит
        # проверку подписи и события не обрабатываются.
        existing_repo.webhook_secret = (
            repo_in.webhook_secret or existing_repo.webhook_secret or generate_webhook_secret()
        )
        if token:
            existing_repo.access_token = token
        existing_repo.connected_by_id = current_user.id
        existing_repo.is_active = True
        repo = existing_repo
    else:
        repo = GitRepository(
            project_id=project_id,
            url=repo_in.url,
            repo_name=repo_in.repo_name,
            api_url=repo_in.api_url,
            provider=repo_in.provider,
            webhook_secret=repo_in.webhook_secret or generate_webhook_secret(),
            access_token=token,
            connected_by_id=current_user.id,
            # Пустое значение оставляем на дефолт модели: ветка по
            # умолчанию нужна всегда, а null здесь ломает сверку.
            default_branch=(repo_in.default_branch or "main"),
            path_filter=repo_in.path_filter,
        )
        db.add(repo)

    await db.commit()
    await db.refresh(repo)

    _schedule_initial_sync(repo.id)

    return repo


# Старый путь оставлен для совместимости с существующим фронтендом
@router.post("/{project_id}/repository", response_model=GitRepositorySchema)
async def create_project_repository_legacy(
    project_id: int,
    repo_in: GitRepositoryCreate,
    db: AsyncSession = Depends(get_db),
    member: ProjectMember = Depends(deps.check_permission(Permission.PROJECT_CONNECT_REPO)),
):
    return await create_project_repository(project_id, repo_in, db, member)


@router.patch("/{project_id}/repositories/{repository_id}", response_model=GitRepositorySchema)
async def update_project_repository(
    project_id: int,
    repository_id: int,
    repo_in: GitRepositoryUpdate,
    db: AsyncSession = Depends(get_db),
    member: ProjectMember = Depends(deps.check_permission(Permission.PROJECT_CONNECT_REPO)),
):
    """Обновить репозиторий, в том числе перевыпустить секрет вебхука."""
    result = await db.execute(
        select(GitRepository).filter(
            GitRepository.id == repository_id,
            GitRepository.project_id == project_id,
        )
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    data = repo_in.model_dump(exclude_unset=True)

    if data.pop("regenerate_secret", False):
        repo.webhook_secret = generate_webhook_secret()
    if "webhook_secret" in data and data["webhook_secret"]:
        repo.webhook_secret = data["webhook_secret"]
    if data.get("url"):
        repo.url = data["url"]
    if "api_url" in data:
        repo.api_url = data["api_url"]
    if "repo_name" in data:
        repo.repo_name = data["repo_name"]
    if "default_branch" in data:
        repo.default_branch = data["default_branch"]
    if "path_filter" in data:
        repo.path_filter = data["path_filter"]
    if "is_active" in data:
        repo.is_active = data["is_active"]

    await db.commit()
    await db.refresh(repo)
    return repo


@router.delete("/{project_id}/repositories/{repository_id}")
async def delete_project_repository(
    project_id: int,
    repository_id: int,
    db: AsyncSession = Depends(get_db),
    member: ProjectMember = Depends(deps.check_permission(Permission.PROJECT_CONNECT_REPO)),
):
    """Отключить репозиторий проекта."""
    result = await db.execute(
        select(GitRepository).filter(
            GitRepository.id == repository_id,
            GitRepository.project_id == project_id,
        )
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    # task_git_links.target_id — обычный Integer без внешнего ключа, поэтому
    # при удалении репозитория связи переживают коммиты и остаются
    # висеть на несуществующие id. Убираем их явно, иначе в прогрессе
    # задач появляются коммиты, которых больше нет.
    from app.git.models import Commit as _C
    from app.git.models import TaskGitLink as _L
    from app.models import task_commits

    await db.execute(
        text(
            "DELETE FROM task_git_links WHERE link_type = 'commit' AND target_id IN "
            "(SELECT id FROM git_commits WHERE repository_id = :r)"
        ),
        {"r": repository_id},
    )
    await db.execute(
        task_commits.delete().where(
            task_commits.c.commit_id.in_(
                select(_C.id).where(_C.repository_id == repository_id)
            )
        )
    )

    await db.delete(repo)
    await db.commit()
    return {"status": "success"}


@router.get("/{project_id}/members", response_model=List[dict])
async def read_project_members(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    member: ProjectMember = Depends(deps.check_permission(Permission.PROJECT_VIEW))
):
    query = (
        select(User, ProjectMember.role)
        .join(ProjectMember, (ProjectMember.user_id == User.id) & (ProjectMember.project_id == project_id))
    )
    result = await db.execute(query)
    rows = result.all()
    
    members_data = []
    for user, role in rows:
        members_data.append({
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "avatar_url": user.avatar_url,
            "role": role
        })
    return members_data

@router.post("/{project_id}/invites/{user_id}", response_model=ProjectInviteSchema)
async def create_project_invite(
    project_id: int,
    user_id: int,
    role: ProjectRole = ProjectRole.DEVELOPER,
    db: AsyncSession = Depends(get_db),
    current_member: ProjectMember = Depends(deps.check_permission(Permission.PROJECT_INVITE))
):
    # Менеджер может назначать роли, но не выше своей
    if current_member.role == ProjectRole.MANAGER and role == ProjectRole.PROJECT_MANAGER:
        raise HTTPException(status_code=403, detail="Manager cannot assign Project Manager role")
    
    # Проверяем, существует ли пользователь
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Проверяем, не является ли он уже участником
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, 
            ProjectMember.user_id == user_id
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User is already a member")

    # Проверяем, нет ли уже активного приглашения
    result = await db.execute(
        select(ProjectInvite).where(
            ProjectInvite.project_id == project_id,
            ProjectInvite.user_id == user_id,
            ProjectInvite.status == InviteStatus.PENDING
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Invitation already sent")

    # Создаем приглашение
    invite = ProjectInvite(
        project_id=project_id,
        user_id=user_id,
        inviter_id=current_member.user_id,
        role=role,
        status=InviteStatus.PENDING
    )
    db.add(invite)
    await db.flush()

    # Получаем название проекта для уведомления
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one()

    # Создаем уведомление
    await NotificationService.create_notification(
        db=db,
        user_id=user_id,
        title="Приглашение в проект",
        message=f"Вас пригласили в проект '{project.name}' на роль {role.replace('_', ' ')}",
        notification_type=NotificationType.PROJECT_INVITE,
        project_id=project_id,
        invite_id=invite.id
    )
    
    await db.commit()
    await db.refresh(invite)
    return invite

@router.get("/{project_id}/invites", response_model=List[ProjectInviteSchema])
async def read_project_invites(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    member: ProjectMember = Depends(deps.check_permission(Permission.PROJECT_VIEW))
):
    """Список исходящих приглашений проекта"""
    result = await db.execute(
        select(ProjectInvite)
        .options(selectinload(ProjectInvite.user))
        .where(
            ProjectInvite.project_id == project_id,
            ProjectInvite.status == InviteStatus.PENDING
        )
    )
    return result.scalars().all()

@router.post("/invites/{invite_id}/accept")
async def accept_invite(
    invite_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    result = await db.execute(
        select(ProjectInvite).where(ProjectInvite.id == invite_id, ProjectInvite.user_id == current_user.id)
    )
    invite = result.scalar_one_or_none()
    if not invite or invite.status != InviteStatus.PENDING:
        raise HTTPException(status_code=404, detail="Invitation not found or already processed")

    # Добавляем в участники
    from app.projects.models import Role
    role_res = await db.execute(select(Role).where(Role.name == invite.role))
    role_obj = role_res.scalar_one_or_none()

    member = ProjectMember(
        project_id=invite.project_id,
        user_id=current_user.id,
        role=invite.role,
        role_id=role_obj.id if role_obj else None
    )
    db.add(member)
    
    # Обновляем статус приглашения
    invite.status = InviteStatus.ACCEPTED
    
    # Помечаем уведомление как прочитанное
    await db.execute(
        update(Notification)
        .where(Notification.invite_id == invite_id, Notification.user_id == current_user.id)
        .values(is_read=True)
    )

    # Уведомляем отправителя
    result = await db.execute(select(Project).where(Project.id == invite.project_id))
    project = result.scalar_one()
    
    await NotificationService.create_notification(
        db=db,
        user_id=invite.inviter_id,
        title="Приглашение принято",
        message=f"Пользователь {current_user.email} принял приглашение в проект '{project.name}'",
        notification_type=NotificationType.INFO,
        project_id=invite.project_id
    )
    
    await db.commit()
    return {"status": "success", "project_id": invite.project_id}

@router.post("/invites/{invite_id}/decline")
async def decline_invite(
    invite_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    result = await db.execute(
        select(ProjectInvite).where(ProjectInvite.id == invite_id, ProjectInvite.user_id == current_user.id)
    )
    invite = result.scalar_one_or_none()
    if not invite or invite.status != InviteStatus.PENDING:
        raise HTTPException(status_code=404, detail="Invitation not found or already processed")

    invite.status = InviteStatus.DECLINED

    # Помечаем уведомление как прочитанное
    await db.execute(
        update(Notification)
        .where(Notification.invite_id == invite_id, Notification.user_id == current_user.id)
        .values(is_read=True)
    )

    # Уведомляем отправителя
    result = await db.execute(select(Project).where(Project.id == invite.project_id))
    project = result.scalar_one()

    await NotificationService.create_notification(
        db=db,
        user_id=invite.inviter_id,
        title="Приглашение отклонено",
        message=f"Пользователь {current_user.email} отклонил приглашение в проект '{project.name}'",
        notification_type=NotificationType.INFO,
        project_id=invite.project_id
    )

    await db.commit()
    return {"status": "success"}

@router.delete("/{project_id}/members/{user_id}")
async def remove_project_member(
    project_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_member: ProjectMember = Depends(deps.check_permission(Permission.PROJECT_REMOVE_MEMBER))
):
    # Проверяем роль участника, которого удаляем
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, 
            ProjectMember.user_id == user_id
        )
    )
    target_member = result.scalar_one_or_none()
    if not target_member:
        raise HTTPException(status_code=404, detail="Member not found")
        
    # Менеджер не может удалить проектного менеджера
    if current_member.role == ProjectRole.MANAGER and target_member.role == ProjectRole.PROJECT_MANAGER:
        raise HTTPException(status_code=403, detail="Manager cannot remove Project Manager")
        
    await db.delete(target_member)
    await db.commit()
    return {"message": "Member removed"}

@router.get("/{project_id}/activity")
async def get_project_activity(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """Лента активности проекта (задачи + git)"""
    from app.tasks.models import TaskActivity, Task
    from app.git.models import GitEventLog, GitRepository
    
    # 1. Получаем активности задач
    task_activities_query = (
        select(TaskActivity)
        .join(Task, Task.id == TaskActivity.task_id)
        .where(Task.project_id == project_id)
        .options(selectinload(TaskActivity.user))
        .order_by(desc(TaskActivity.created_at))
        .limit(50)
    )
    task_res = await db.execute(task_activities_query)
    task_activities = task_res.scalars().all()
    
    # 2. Получаем git события
    repo_query = select(GitRepository).where(GitRepository.project_id == project_id)
    repo_res = await db.execute(repo_query)
    repo_ids = [r.id for r in repo_res.scalars().all()]
    
    git_activities = []
    if repo_ids:
        git_query = (
            select(GitEventLog)
            .where(GitEventLog.repository_id.in_(repo_ids))
            .order_by(desc(GitEventLog.created_at))
            .limit(50)
        )
        git_res = await db.execute(git_query)
        git_activities = git_res.scalars().all()
        
    # 3. Объединяем и сортируем
    combined = []
    for a in task_activities:
        combined.append({
            "type": "task",
            "id": a.id,
            "activity_type": a.activity_type,
            "description": a.description,
            "old_value": a.old_value,
            "new_value": a.new_value,
            "created_at": a.created_at,
            "user": {
                "id": a.user.id,
                "full_name": a.user.full_name,
                "email": a.user.email,
                "avatar_url": a.user.avatar_url
            } if a.user else None,
            "task_id": a.task_id
        })
        
    for g in git_activities:
        combined.append({
            "type": "git",
            "id": g.id,
            "event_type": g.event_type,
            "provider": g.provider,
            "payload": g.payload,
            "created_at": g.created_at
        })
        
    combined.sort(key=lambda x: x["created_at"], reverse=True)
    return combined[:100]

# --- Фон проекта ------------------------------------------------------
#
# Файл кладётся рядом с остальными файлами проекта и раздаётся через
# /uploads, как аватары. Имя всегда одно и то же — background.<ext>:
# фон у проекта один, и варианты расширения незачем копить на диске.
BACKGROUND_STEM = "background"

# По расширению не судим — файл приходит под именем background.<что-то>
# и показывается через <img>. Смотрим сигнатуру, как у аватаров.
BACKGROUND_SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": ".png",
    b"\xff\xd8\xff": ".jpg",
}


def _background_dir(project_id: int) -> str:
    return os.path.join("uploads", "projects", str(project_id))


def _stored_background(project_id: int) -> Optional[str]:
    """Путь к файлу фона на диске, если он там есть."""
    directory = _background_dir(project_id)
    if not os.path.isdir(directory):
        return None
    for name in os.listdir(directory):
        if name.startswith(BACKGROUND_STEM + "."):
            return os.path.join(directory, name)
    return None


def _delete_background_file(project) -> Optional[str]:
    """Убирает файл фона проекта. Возвращает удалённый путь."""
    path = _stored_background(project.id)
    if not path:
        return None
    try:
        os.remove(path)
    except OSError as exc:
        # Файл может быть занят. Настройку всё равно применяем: сорванная
        # картинка лучше, чем фон, который нельзя снять.
        print(f"[background] project {project.id}: {path} не удалён — {exc}")
        return None
    return path


def _background_url(project_id: int, ext: str) -> str:
    """Адрес с меткой времени — иначе браузер держит старую картинку."""
    path = os.path.join(_background_dir(project_id), BACKGROUND_STEM + ext)
    try:
        mtime = int(os.path.getmtime(path))
    except OSError:
        mtime = 0
    return f"/uploads/projects/{project_id}/{BACKGROUND_STEM}{ext}?v={mtime}"


@router.post("/{project_id}/background", response_model=ProjectSchema)
async def upload_project_background(
    project_id: int,
    *,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_member: ProjectMember = Depends(deps.check_permission(Permission.PROJECT_EDIT)),
):
    """Загружает свой фон проекта и сразу включает его."""
    from app.storage import settings as storage_settings

    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    data = await file.read()

    if not data:
        raise HTTPException(status_code=400, detail="Файл пуст")

    max_size = storage_settings.max_file_size_bytes()
    if len(data) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"Файл больше {storage_settings.get()['max_file_size_mb']} МБ",
        )

    ext = None
    for signature, sig_ext in BACKGROUND_SIGNATURES.items():
        if data.startswith(signature):
            ext = sig_ext
            break
    if ext is None:
        raise HTTPException(
            status_code=400,
            detail="Поддерживаются только PNG и JPEG",
        )

    directory = _background_dir(project_id)
    os.makedirs(directory, exist_ok=True)
    _delete_background_file(project)

    path = os.path.join(directory, BACKGROUND_STEM + ext)
    with open(path, "wb") as buffer:
        buffer.write(data)

    project.background = "custom"
    project.background_url = _background_url(project_id, ext)
    await db.commit()

    return await _load_project_for_response(db, project_id, current_member.role)


@router.delete("/{project_id}/background", response_model=ProjectSchema)
async def delete_project_background(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_member: ProjectMember = Depends(deps.check_permission(Permission.PROJECT_EDIT)),
):
    """Снимает свой фон: картинка удаляется с диска, фон становится белым."""
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    removed = _delete_background_file(project)
    if removed:
        print(f"[background] project {project_id}: removed {removed}")

    project.background = "none"
    project.background_url = None
    await db.commit()

    return await _load_project_for_response(db, project_id, current_member.role)


async def _load_project_for_response(
    db: AsyncSession, project_id: int, role: str
) -> Project:
    """Перечитывает проект вместе со связями и проставляет роль.

    members подгружается обязательно: схема ответа читает project.members,
    а после commit объект истёк, и обращение к неподгруженной связи
    уходит вне greenlet — MissingGreenlet, то есть 500 на любое
    обновление проекта. Список проектов подгружает members сразу,
    поэтому там ответа не было видно.
    """
    project = (
        await db.execute(
            select(Project)
            .where(Project.id == project_id)
            .options(
                selectinload(Project.repositories),
                selectinload(Project.members).selectinload(User.git_accounts),
            )
        )
    ).scalar_one()
    project.user_role = role
    return project


@router.patch("/{project_id}", response_model=ProjectSchema)
async def update_project(
    project_id: int,
    project_in: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_member: ProjectMember = Depends(deps.check_permission(Permission.PROJECT_EDIT))
):
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
    )
    project = result.scalar_one()
    
    update_data = project_in.model_dump(exclude_unset=True)

    # Уход с пользовательского фона удаляет сам файл. Иначе он остался
    # бы лежать в uploads навсегда: сменить фон на базовый или снять
    # его, не тронув диск, нельзя, а чистить такие файлы было бы нечем.
    if update_data.get("background") in ("none", "default"):
        removed = _delete_background_file(project)
        if removed:
            print(f"[background] project {project_id}: removed {removed}")
        project.background_url = None

    for field, value in update_data.items():
        setattr(project, field, value)
    
    db.add(project)
    await db.commit()

    # Re-fetch to load relationships
    return await _load_project_for_response(db, project_id, current_member.role)

@router.post("/{project_id}/verify-sql")
async def verify_project_sql(
    project_id: int,
    query_data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    sql_query = query_data.get("query")
    if not sql_query:
        raise HTTPException(status_code=400, detail="No query provided")
    
    # Только PM/Manager могут проверять SQL
    member_res = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == current_user.id
        )
    )
    member = member_res.scalar_one_or_none()
    if (not member or member.role not in [ProjectRole.PROJECT_MANAGER, ProjectRole.MANAGER]) and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Permission denied")

    try:
        # Пытаемся выполнить запрос в подтранзакции (dry run)
        # begin_nested() создает SAVEPOINT
        async with db.begin_nested():
            forbidden = ["drop", "truncate", "grant", "revoke", "alter user", "delete from users", "update users"]
            if any(word in sql_query.lower() for word in forbidden):
                raise Exception("Query contains forbidden keywords or target tables")
                
            await db.execute(text(sql_query))
            # При выходе из блока async with без исключения, SQLAlchemy попытается закоммитить SAVEPOINT, 
            # но мы принудительно делаем ROLLBACK всего в конце эндпоинта или просто полагаемся на то что мы не коммитим внешнюю транзакцию.
            # Для надежности - вызываем rollback именно для этого nested блока.
            await db.rollback()
            
        return {"status": "valid", "message": "SQL is valid"}
    except Exception as e:
        return {"status": "invalid", "error": str(e)}
