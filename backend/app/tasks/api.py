from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import joinedload, selectinload
from typing import List
import os
import shutil
import uuid
from datetime import datetime
from app.core.database import get_db
from app.storage import settings as storage_settings
from app.tasks.models import Task, SubTask, TaskComment, CommentReaction, Attachment, TaskActivity
from app.boards.models import Board, Column
from app.projects.models import Project
from app.models import User
from app.api import deps
from app.schemas.task import (
    Task as TaskSchema, 
    TaskCreate, 
    TaskUpdate, 
    SubTask as SubTaskSchema, 
    SubTaskCreate,
    SubTaskBase,
    TaskComment as CommentSchema,
    TaskCommentCreate,
    TaskCommentUpdate,
    ReactionSchema,
    AttachmentSchema,
    TaskActivitySchema
)

from app.core.roles import Permission, ProjectRole, ROLE_PERMISSIONS
from app.projects.models import ProjectMember
from app.notifications.services import NotificationService
from app.notifications.models import NotificationType
from pydantic import BaseModel

router = APIRouter()


class TaskSearchHit(BaseModel):
    """Одна найденная задача вместе с её проектом."""
    task_id: int
    title: str
    task_type: str | None = None
    priority: int = 0
    due_date: datetime | None = None
    project_id: int
    project_name: str


@router.get("/search", response_model=List[TaskSearchHit])
async def search_tasks(
    q: str = "",
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Поиск задач по названию и описанию.

    Ищет сразу по всем проектам, где пользователь участник, а не по
    текущему: строка поиска стоит в шапке и работает на всех
    страницах, в том числе там, где проекта не выбрано.

    Права проверяются по самому факту членства: задача из проекта, в
    который пользователя не пускают, в выдачу не попадает.
    """
    text = (q or "").strip()
    if len(text) < 2:
        return []

    limit = max(1, min(limit, 50))

    result = await db.execute(
        select(Task, Project.name)
        .join(Project, Project.id == Task.project_id)
        .join(ProjectMember, ProjectMember.project_id == Task.project_id)
        .where(
            ProjectMember.user_id == current_user.id,
            Task.title.ilike(f"%{text}%"),
        )
        .order_by(Task.updated_at.desc().nullslast(), Task.id.desc())
        .limit(limit)
    )

    return [
        TaskSearchHit(
            task_id=task.id,
            title=task.title,
            task_type=task.task_type,
            priority=task.priority or 0,
            due_date=task.due_date,
            project_id=task.project_id,
            project_name=project_name,
        )
        for task, project_name in result.all()
    ]

async def get_member_and_check_permission(
    db: AsyncSession, 
    user_id: int, 
    project_id: int, 
    permission: Permission
) -> ProjectMember:
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, 
            ProjectMember.user_id == user_id
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this project")
    
    allowed_permissions = ROLE_PERMISSIONS.get(member.role, set())
    if permission not in allowed_permissions:
        raise HTTPException(status_code=403, detail=f"Permission denied: {permission}")
    
    return member

async def check_task_access(
    db: AsyncSession, 
    user_id: int, 
    task: Task, 
    permission: Permission,
    new_assignee_id: int | None = None
):
    member = await get_member_and_check_permission(db, user_id, task.project_id, permission)
    
    if permission in [Permission.TASK_EDIT, Permission.TASK_DELETE, Permission.TASK_MANAGE_PRIORITY]:
        if member.role in [ProjectRole.DEVELOPER, ProjectRole.TESTER]:
            if task.assignee_id != user_id:
                raise HTTPException(status_code=403, detail="You can only edit tasks assigned to you")

    if permission == Permission.TASK_ASSIGN_OTHER and new_assignee_id is not None:
        if new_assignee_id != user_id:
            if member.role == ProjectRole.TESTER:
                raise HTTPException(status_code=403, detail="Testers cannot assign tasks to others")
            if member.role == ProjectRole.DEVELOPER and task.assignee_id != user_id:
                raise HTTPException(status_code=403, detail="Developers can only reassign tasks they are currently working on")
    
    return member

async def log_activity(
    db: AsyncSession,
    task_id: int,
    user_id: int,
    activity_type: str,
    old_value: str | None = None,
    new_value: str | None = None,
    description: str | None = None
):
    activity = TaskActivity(
        task_id=task_id,
        user_id=user_id,
        activity_type=activity_type,
        old_value=old_value,
        new_value=new_value,
        description=description
    )
    db.add(activity)

@router.get("/my-tasks", response_model=List[TaskSchema])
async def read_my_tasks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """
    Get all tasks assigned to the current user across all projects.
    """
    result = await db.execute(
        select(Task)
        .options(
            joinedload(Task.assignee).selectinload(User.git_accounts),
            joinedload(Task.comments).joinedload(TaskComment.author).selectinload(User.git_accounts),
            joinedload(Task.comments).joinedload(TaskComment.reactions),
            joinedload(Task.comments).joinedload(TaskComment.attachments),
            selectinload(Task.activities).joinedload(TaskActivity.user).selectinload(User.git_accounts),

            selectinload(Task.subtasks),
            selectinload(Task.dependencies),
            selectinload(Task.commits),
            selectinload(Task.branches),
            selectinload(Task.pull_requests)
        )
        .filter(Task.assignee_id == current_user.id)
        .order_by(Task.due_date.asc().nullslast(), Task.priority.desc())
    )
    return result.unique().scalars().all()

@router.get("/", response_model=List[TaskSchema])
async def read_tasks(
    project_id: int, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    await get_member_and_check_permission(db, current_user.id, project_id, Permission.TASK_VIEW)

    result = await db.execute(
        select(Task)
        .options(
            joinedload(Task.assignee).selectinload(User.git_accounts),
            joinedload(Task.comments).joinedload(TaskComment.author).selectinload(User.git_accounts),
            joinedload(Task.comments).joinedload(TaskComment.reactions),
            joinedload(Task.comments).joinedload(TaskComment.attachments),
            selectinload(Task.activities).joinedload(TaskActivity.user).selectinload(User.git_accounts),

            selectinload(Task.subtasks),
            selectinload(Task.dependencies),
            selectinload(Task.commits),
            selectinload(Task.branches),
            selectinload(Task.pull_requests)
        )
        .filter(Task.project_id == project_id)
    )
    return result.unique().scalars().all()

@router.get("/{task_id}", response_model=TaskSchema)
async def read_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    result = await db.execute(
        select(Task)
        .options(
            joinedload(Task.assignee).selectinload(User.git_accounts),
            joinedload(Task.comments).joinedload(TaskComment.author).selectinload(User.git_accounts),
            joinedload(Task.comments).joinedload(TaskComment.reactions),
            joinedload(Task.comments).joinedload(TaskComment.attachments),
            selectinload(Task.activities).joinedload(TaskActivity.user).selectinload(User.git_accounts),

            selectinload(Task.subtasks),
            selectinload(Task.dependencies),
            selectinload(Task.commits),
            selectinload(Task.branches),
            selectinload(Task.pull_requests)
        )
        .where(Task.id == task_id)
    )
    task = result.unique().scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    await get_member_and_check_permission(db, current_user.id, task.project_id, Permission.TASK_VIEW)
        
    return task

@router.post("/", response_model=TaskSchema)
async def create_task(
    task_in: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    member = await get_member_and_check_permission(db, current_user.id, task_in.project_id, Permission.TASK_CREATE)

    # Получаем правила проекта
    project_res = await db.execute(select(Project).where(Project.id == task_in.project_id))
    project = project_res.scalar_one()
    rules = project.rules or {}

    # 1. Проверка обязательных полей
    required_fields = rules.get("required_fields", ["title"])
    for field in required_fields:
        val = getattr(task_in, field, None)
        if not val:
            raise HTTPException(status_code=400, detail=f"Field '{field}' is required by project rules")

    if not task_in.column_id:
        board_res = await db.execute(select(Board).filter(Board.project_id == task_in.project_id))
        board = board_res.scalar_one_or_none()
        if board:
            col_res = await db.execute(select(Column).filter(Column.board_id == board.id).order_by(Column.position))
            first_col = col_res.scalars().first()
            if first_col:
                task_in.column_id = first_col.id

    # 2. Логика даты начала (start_date_logic)
    start_logic = rules.get("start_date_logic", "created_at")
    if start_logic == "created_at":
        task_in.start_date = datetime.utcnow()
    elif start_logic == "manual_pm":
        # Если задает PM/Manager, а прислал кто-то другой - обнуляем, если не было задано
        if member.role not in [ProjectRole.PROJECT_MANAGER, ProjectRole.MANAGER]:
            task_in.start_date = None
    elif start_logic == "manual_assignee":
        # Если задает исполнитель, проверяем при обновлении. При создании - только если сам себе назначил
        if task_in.assignee_id != current_user.id:
            task_in.start_date = None

    data = task_in.model_dump(exclude={"dependency_ids", "subtasks"})
    task = Task(**data)

    if task_in.dependency_ids:
        dep_tasks = await db.execute(select(Task).where(Task.id.in_(task_in.dependency_ids)))
        task.dependencies = dep_tasks.scalars().all()

    # 3. Создание подзадач
    if task_in.subtasks:
        for st_in in task_in.subtasks:
            task.subtasks.append(SubTask(title=st_in.title, is_completed=st_in.is_completed))

    db.add(task)
    await db.flush()

    await log_activity(
        db, task.id, current_user.id, "task_created",
        description=f"Created task: {task.title}"
    )

    await db.commit()
    return await read_task(task.id, db, current_user)
@router.patch("/{task_id}", response_model=TaskSchema)
async def update_task(
    task_id: int,
    task_in: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    result = await db.execute(
        select(Task)
        .options(selectinload(Task.dependencies))
        .where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Получаем правила проекта
    project_res = await db.execute(select(Project).where(Project.id == task.project_id))
    project = project_res.scalar_one()
    rules = project.rules or {}

    permission = Permission.TASK_EDIT
    if task_in.assignee_id is not None:
        if task_in.assignee_id == current_user.id:
            permission = Permission.TASK_ASSIGN_SELF
        else:
            permission = Permission.TASK_ASSIGN_OTHER
            
    member = await check_task_access(db, current_user.id, task, permission, task_in.assignee_id)

    # 1. Проверка блокировки колонок (column_role_locks)
    if task_in.column_id is not None and task_in.column_id != task.column_id:
        column_locks = rules.get("column_role_locks", {})
        allowed_roles = column_locks.get(str(task_in.column_id))
        if allowed_roles and member.role not in allowed_roles:
            raise HTTPException(status_code=403, detail=f"Your role '{member.role}' is not allowed to move tasks to this column")

    # 2. Авто-назначение при перемещении (auto_assign_on_move)
    if task_in.column_id is not None and task_in.column_id != task.column_id:
        if rules.get("auto_assign_on_move"):
            # Автоматически назначаем текущего пользователя, если он еще не назначен
            if task.assignee_id != current_user.id:
                task_in.assignee_id = current_user.id

    # 3. Логика даты начала (start_date_logic) при обновлении
    if task_in.start_date is not None:
        start_logic = rules.get("start_date_logic", "created_at")
        if start_logic == "manual_pm":
            if member.role not in [ProjectRole.PROJECT_MANAGER, ProjectRole.MANAGER]:
                # Игнорируем изменение даты начала, если не PM
                task_in.start_date = task.start_date
        elif start_logic == "manual_assignee":
            if task.assignee_id != current_user.id:
                # Игнорируем изменение, если не исполнитель
                task_in.start_date = task.start_date

    old_status_id = task.column_id
    old_assignee_id = task.assignee_id
    old_priority = task.priority

    update_data = task_in.model_dump(exclude_unset=True, exclude={"dependency_ids"})
    for key, value in update_data.items():
        setattr(task, key, value)
    
    if task_in.dependency_ids is not None:
        if task_id in task_in.dependency_ids:
            raise HTTPException(status_code=400, detail="A task cannot depend on itself")
        dep_tasks = await db.execute(select(Task).where(Task.id.in_(task_in.dependency_ids)))
        task.dependencies = dep_tasks.scalars().all()

    if task_in.column_id is not None and task_in.column_id != old_status_id:
        old_col = await db.get(Column, old_status_id)
        new_col = await db.get(Column, task_in.column_id)
        await log_activity(
            db, task.id, current_user.id, "status_change",
            old_value=old_col.name if old_col else str(old_status_id),
            new_value=new_col.name if new_col else str(task_in.column_id),
            description=f"Changed status from {old_col.name if old_col else '?'} to {new_col.name if new_col else '?'}"
        )

    if "assignee_id" in update_data and task_in.assignee_id != old_assignee_id:
        old_user = await db.get(User, old_assignee_id) if old_assignee_id else None
        new_user = await db.get(User, task_in.assignee_id) if task_in.assignee_id else None
        await log_activity(
            db, task.id, current_user.id, "assignee_change",
            old_value=old_user.full_name or old_user.email if old_user else "Unassigned",
            new_value=new_user.full_name or new_user.email if new_user else "Unassigned",
            description=f"Assigned to {new_user.full_name or new_user.email if new_user else 'Unassigned'}"
        )

    if task_in.priority is not None and task_in.priority != old_priority:
        await log_activity(
            db, task.id, current_user.id, "priority_change",
            old_value=str(old_priority),
            new_value=str(task_in.priority),
            description=f"Changed priority to {task_in.priority}"
        )

    await db.commit()
    await db.refresh(task)

    if task.assignee_id and task.assignee_id != old_assignee_id and task.assignee_id != current_user.id:
        await NotificationService.create_notification(
            db=db,
            user_id=task.assignee_id,
            title="Назначена новая задача",
            message=f"Вы были назначены исполнителем задачи: {task.title}",
            notification_type=NotificationType.TASK_ASSIGNED,
            project_id=task.project_id,
            task_id=task.id
        )
        await db.commit()

    return await read_task(task.id, db, current_user)

@router.delete("/{task_id}")
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    await check_task_access(db, current_user.id, task, Permission.TASK_DELETE)
        
    await db.execute(
        update(Attachment)
        .where(Attachment.task_id == task_id)
        .values(status="deleted", deleted_at=func.now())
    )
    
    await db.delete(task)
    await db.commit()
    return {"status": "success"}

@router.post("/{task_id}/subtasks", response_model=SubTaskSchema)
async def create_subtask(
    task_id: int,
    subtask_in: SubTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task: raise HTTPException(status_code=404, detail="Task not found")

    await check_task_access(db, current_user.id, task, Permission.TASK_MANAGE_SUBTASKS)
    
    db_sub = SubTask(**subtask_in.model_dump())
    db.add(db_sub)
    await db.flush()
    
    await log_activity(
        db, task.id, current_user.id, "subtask_added",
        new_value=db_sub.title,
        description=f"Added subtask: {db_sub.title}"
    )
    
    await db.commit()
    await db.refresh(db_sub)
    return db_sub

@router.patch("/subtasks/{subtask_id}", response_model=SubTaskSchema)
async def update_subtask(
    subtask_id: int,
    subtask_in: SubTaskBase,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    result = await db.execute(
        select(SubTask).options(joinedload(SubTask.task)).where(SubTask.id == subtask_id)
    )
    db_sub = result.scalar_one_or_none()
    if not db_sub:
        raise HTTPException(status_code=404, detail="SubTask not found")
        
    await check_task_access(db, current_user.id, db_sub.task, Permission.TASK_MANAGE_SUBTASKS)
    
    old_completed = db_sub.is_completed
    for key, value in subtask_in.model_dump().items():
        setattr(db_sub, key, value)
        
    if old_completed != db_sub.is_completed:
        await log_activity(
            db, db_sub.task_id, current_user.id, "subtask_status",
            new_value="completed" if db_sub.is_completed else "pending",
            description=f"Marked subtask '{db_sub.title}' as {'done' if db_sub.is_completed else 'not done'}"
        )
        
    await db.commit()
    await db.refresh(db_sub)
    return db_sub

@router.delete("/subtasks/{subtask_id}")
async def delete_subtask(
    subtask_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    result = await db.execute(
        select(SubTask).options(joinedload(SubTask.task)).where(SubTask.id == subtask_id)
    )
    db_sub = result.scalar_one_or_none()
    if not db_sub:
        raise HTTPException(status_code=404, detail="SubTask not found")
        
    await check_task_access(db, current_user.id, db_sub.task, Permission.TASK_MANAGE_SUBTASKS)
    
    await log_activity(
        db, db_sub.task_id, current_user.id, "subtask_deleted",
        description=f"Deleted subtask: {db_sub.title}"
    )
    
    await db.delete(db_sub)
    await db.commit()
    return {"status": "success"}

@router.post("/{task_id}/comments", response_model=CommentSchema)
async def create_comment(
    task_id: int,
    comment_in: TaskCommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task: raise HTTPException(status_code=404, detail="Task not found")

    await get_member_and_check_permission(db, current_user.id, task.project_id, Permission.COMMENT_CREATE)
    
    db_comment = TaskComment(
        content=comment_in.content,
        task_id=task_id,
        parent_id=comment_in.parent_id,
        user_id=current_user.id
    )
    db.add(db_comment)
    await db.flush()
    
    if comment_in.attachment_ids:
        await db.execute(
            update(Attachment)
            .where(Attachment.id.in_(comment_in.attachment_ids))
            .values(comment_id=db_comment.id, status="active")
        )
    
    await log_activity(
        db, task_id, current_user.id, "comment_added",
        description="Added a comment"
    )
    
    await db.commit()
    
    try:
        await NotificationService.process_mentions(
            db, 
            comment_in.content, 
            task.project_id, 
            task.id, 
            current_user
        )
        await db.commit()
    except Exception as e:
        print(f"Mention error: {e}")

    result = await db.execute(
        select(TaskComment).options(
            joinedload(TaskComment.author),
            joinedload(TaskComment.reactions),
            joinedload(TaskComment.attachments)
        ).where(TaskComment.id == db_comment.id)
    )
    return result.unique().scalar_one()

@router.patch("/comments/{comment_id}", response_model=CommentSchema)
async def update_comment(
    comment_id: int,
    comment_in: TaskCommentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    result = await db.execute(
        select(TaskComment).where(TaskComment.id == comment_id)
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
        
    task_res = await db.execute(select(Task).where(Task.id == comment.task_id))
    task = task_res.scalar_one()
    
    await get_member_and_check_permission(db, current_user.id, task.project_id, Permission.COMMENT_EDIT_OWN)
    
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own comments")
        
    comment.content = comment_in.content
    comment.updated_at = datetime.utcnow()
    db.add(comment)
    
    if comment_in.attachments_to_remove:
        await db.execute(
            update(Attachment)
            .where(Attachment.id.in_(comment_in.attachments_to_remove))
            .values(status="deleted", deleted_at=func.now())
        )
    
    await db.commit()
    
    try:
        await NotificationService.process_mentions(
            db, 
            comment_in.content, 
            task.project_id, 
            task.id, 
            current_user
        )
        await db.commit()
    except Exception as e:
        print(f"Mention error in update: {e}")

    result = await db.execute(
        select(TaskComment).options(
            joinedload(TaskComment.author),
            joinedload(TaskComment.reactions),
            joinedload(TaskComment.attachments)
        ).where(TaskComment.id == comment_id)
    )
    
    return result.unique().scalar_one()

@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    result = await db.execute(select(TaskComment).where(TaskComment.id == comment_id))
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
        
    task_res = await db.execute(select(Task).where(Task.id == comment.task_id))
    task = task_res.scalar_one()
    
    member = await get_member_and_check_permission(db, current_user.id, task.project_id, Permission.COMMENT_CREATE)
    
    allowed_permissions = ROLE_PERMISSIONS.get(member.role, set())
    can_delete_any = Permission.COMMENT_DELETE_ANY in allowed_permissions
    is_author = comment.user_id == current_user.id
    
    if not can_delete_any and not is_author:
         raise HTTPException(status_code=403, detail="Permission denied")
         
    await db.execute(
        update(Attachment)
        .where(Attachment.comment_id == comment_id)
        .values(status="deleted", deleted_at=func.now())
    )
         
    await db.delete(comment)
    await db.commit()
    return {"status": "success"}

@router.post("/{task_id}/attachments", response_model=AttachmentSchema)
async def upload_attachment(
    task_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    res = await db.execute(select(Task).where(Task.id == task_id))
    task = res.scalar_one_or_none()
    if not task: raise HTTPException(status_code=404, detail="Task not found")
    
    project_res = await db.execute(select(Project).where(Project.id == task.project_id))
    project = project_res.scalar_one()
    
    await get_member_and_check_permission(db, current_user.id, task.project_id, Permission.TASK_VIEW)

    # Лимиты берутся из настроек хранилища, а не из констант: их должен
    # менять администратор из панели без правки кода и перезапуска.
    max_size = storage_settings.max_file_size_bytes()
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > max_size:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File too large: {file_size} bytes, "
                f"limit is {max_size} bytes "
                f"({storage_settings.get()['max_file_size_mb']} MB)"
            ),
        )

    allowed_extensions = set(storage_settings.extensions())
    _, ext = os.path.splitext(file.filename)
    if ext.lower() not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File type {ext} not allowed. "
                f"Allowed: {', '.join(sorted(allowed_extensions))}"
            ),
        )

    limit = project.storage_limit_bytes or storage_settings.default_project_limit_bytes()
    if project.storage_used_bytes + file_size > limit:
        raise HTTPException(status_code=400, detail="Project storage limit reached")

    attachment_id = uuid.uuid4()
    rel_path = f"projects/{task.project_id}/tasks/{task_id}/attachments"
    abs_path = os.path.join("uploads", rel_path)
    if not os.path.exists(abs_path):
        os.makedirs(abs_path, exist_ok=True)
    
    file_name = f"{attachment_id}{ext}"
    full_path = os.path.join(abs_path, file_name)
    
    with open(full_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    attachment = Attachment(
        id=attachment_id,
        filename=file.filename,
        path=os.path.join(rel_path, file_name).replace("\\", "/"),
        mime_type=file.content_type,
        size_bytes=file_size,
        task_id=task_id,
        project_id=task.project_id,
        uploaded_by=current_user.id,
        status="orphan"
    )
    db.add(attachment)
    
    project.storage_used_bytes += file_size
    
    await log_activity(
        db, task_id, current_user.id, "attachment_added",
        new_value=file.filename,
        description=f"Uploaded file: {file.filename}"
    )
    
    await db.commit()
    await db.refresh(attachment)
    return attachment

@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    res = await db.execute(select(Attachment).where(Attachment.id == attachment_id))
    attachment = res.scalar_one_or_none()
    if not attachment: raise HTTPException(status_code=404, detail="Attachment not found")
    
    await get_member_and_check_permission(db, current_user.id, attachment.project_id, Permission.TASK_VIEW)
    
    full_path = os.path.join("uploads", attachment.path)
    if not os.path.exists(full_path):
         raise HTTPException(status_code=404, detail="File not found on server")
         
    return FileResponse(
        full_path, 
        filename=attachment.filename,
        media_type=attachment.mime_type or "application/octet-stream"
    )

@router.delete("/attachments/{attachment_id}")
async def delete_attachment(
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    res = await db.execute(select(Attachment).where(Attachment.id == attachment_id))
    attachment = res.scalar_one_or_none()
    if not attachment: raise HTTPException(status_code=404, detail="Attachment not found")
    
    await get_member_and_check_permission(db, current_user.id, attachment.project_id, Permission.TASK_VIEW)
    
    if attachment.uploaded_by != current_user.id:
         project_res = await db.execute(select(Project).where(Project.id == attachment.project_id))
         project = project_res.scalar_one()
         if project.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Permission denied")

    attachment.status = "deleted"
    attachment.deleted_at = datetime.utcnow()
    
    await log_activity(
        db, attachment.task_id, current_user.id, "attachment_deleted",
        description=f"Deleted file: {attachment.filename}"
    )
    
    await db.commit()
    return {"status": "success"}

@router.post("/comments/{comment_id}/reactions")
async def toggle_reaction(
    comment_id: int,
    emoji: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    result = await db.execute(select(TaskComment).where(TaskComment.id == comment_id))
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
        
    task_res = await db.execute(select(Task).where(Task.id == comment.task_id))
    task = task_res.scalar_one()
    
    await get_member_and_check_permission(db, current_user.id, task.project_id, Permission.TASK_VIEW)
    
    # Check if reaction exists
    reaction_res = await db.execute(
        select(CommentReaction).where(
            CommentReaction.comment_id == comment_id,
            CommentReaction.user_id == current_user.id,
            CommentReaction.emoji == emoji
        )
    )
    existing_reaction = reaction_res.scalar_one_or_none()
    
    if existing_reaction:
        await db.delete(existing_reaction)
        await db.commit()
        return {"status": "removed"}
    else:
        new_reaction = CommentReaction(
            comment_id=comment_id,
            user_id=current_user.id,
            emoji=emoji
        )
        db.add(new_reaction)
        await db.commit()
        return {"status": "added"}
