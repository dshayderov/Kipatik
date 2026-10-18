import uuid
from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime
from app.schemas.user import User as UserSchema

# Типы задач.
#
# Набор совпадает с COMMIT_TYPES из app/ai/classifier — с
# типами, которые классификатор определяет для коммитов. Совпадение
# позволяет сравнивать заявленный тип задачи с тем, что модель
# насчитала по её коммитам: расхождение «задача — дефект, а коммиты —
# функциональность» измеряется и годится для отчёта.
#
# В колонке хранится строка, поэтому расширение перечня — это правка
# этого списка и списка в интерфейсе (frontend/src/types/taskType.ts),
# без миграции типа данных.
TASK_TYPES = {"bugfix", "feature", "refactor", "docs", "test", "chore"}


def _validate_task_type(v):
    """Пустое значение — «без типа», неизвестное — ошибка запроса.

    Значение приходит из выпадающего списка, но endpoint доступен и
    напрямую: без проверки опечатка молча превратилась бы в подпись,
    которой нет ни в одном переводе.
    """
    if v is None or v == "":
        return None
    if v not in TASK_TYPES:
        raise ValueError(f"task_type must be one of {sorted(TASK_TYPES)} or empty")
    return v


class SubTaskBase(BaseModel):
    title: str
    is_completed: bool = False

class SubTaskCreate(SubTaskBase):
    task_id: int

class SubTask(SubTaskBase):
    id: int
    task_id: int
    class Config: from_attributes = True

class ReactionSchema(BaseModel):
    id: int
    user_id: int
    emoji: str
    class Config: from_attributes = True

class AttachmentSchema(BaseModel):
    id: uuid.UUID
    filename: str
    path: str
    size_bytes: int
    mime_type: Optional[str] = None
    uploaded_by: int
    project_id: int
    task_id: int
    comment_id: Optional[int] = None
    status: str
    created_at: datetime
    deleted_at: Optional[datetime] = None
    class Config: from_attributes = True

class TaskCommentBase(BaseModel):
    content: str

class TaskCommentCreate(TaskCommentBase):
    task_id: int
    parent_id: Optional[int] = None
    attachment_ids: Optional[List[uuid.UUID]] = []

class TaskCommentUpdate(BaseModel):
    content: str
    attachments_to_remove: Optional[List[uuid.UUID]] = []

class TaskComment(TaskCommentBase):
    id: int
    task_id: int
    user_id: int
    parent_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    author: Optional[UserSchema] = None
    reactions: List[ReactionSchema] = []
    attachments: List[AttachmentSchema] = []
    class Config: from_attributes = True

class TaskActivitySchema(BaseModel):
    id: int
    task_id: int
    user_id: Optional[int] = None
    user: Optional[UserSchema] = None
    activity_type: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class CommitSchema(BaseModel):
    id: int
    sha: str
    message: str
    author: str
    timestamp: datetime
    meta_data: Optional[dict] = None
    class Config: from_attributes = True

class BranchSchema(BaseModel):
    id: int
    name: str
    class Config: from_attributes = True

class PullRequestSchema(BaseModel):
    id: int
    external_id: int
    title: str
    state: str
    url: Optional[str] = None
    source_branch: Optional[str] = None
    target_branch: Optional[str] = None
    class Config: from_attributes = True

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    priority: int = 1
    task_type: Optional[str] = None
    start_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    column_id: Optional[int] = None

    _check_task_type = field_validator("task_type")(_validate_task_type)

class TaskCreate(TaskBase):
    project_id: int
    parent_id: Optional[int] = None
    dependency_ids: Optional[List[int]] = []
    subtasks: Optional[List[SubTaskBase]] = []

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    task_type: Optional[str] = None

    _check_task_type = field_validator("task_type")(_validate_task_type)
    start_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    column_id: Optional[int] = None
    assignee_id: Optional[int] = None
    parent_id: Optional[int] = None
    dependency_ids: Optional[List[int]] = None

class Task(TaskBase):
    id: int
    project_id: int
    assignee_id: Optional[int] = None
    parent_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    subtasks: List[SubTask] = []
    comments: List[TaskComment] = []
    activities: List[TaskActivitySchema] = []
    dependencies: List[int] = []
    commits: List[CommitSchema] = []
    branches: List[BranchSchema] = []
    pull_requests: List[PullRequestSchema] = []
    
    @field_validator("dependencies", mode="before")
    @classmethod
    def get_dependency_ids(cls, v):
        if hasattr(v, '__iter__') and not isinstance(v, (str, bytes)):
            try:
                return [d.id for d in v if hasattr(d, 'id')]
            except:
                return v
        return v

    class Config:
        from_attributes = True
