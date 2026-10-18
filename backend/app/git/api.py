from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
from app.api import deps
from app.git.models import Commit, GitRepository, Branch
from app.tasks.models import Task
from app.users.models import User
from pydantic import BaseModel
from datetime import datetime
from app.api.v1.endpoints.git import router as webhook_router

router = APIRouter()

# Подключаем роуты вебхука
router.include_router(webhook_router)

class CommitSchema(BaseModel):
    id: int
    sha: str
    message: str
    author: str
    timestamp: datetime
    class Config: from_attributes = True

async def _assert_task_view_access(db: AsyncSession, current_user: User, task: Task) -> None:
    """Проверяет право просмотра задачи (участник проекта или суперпользователь)."""
    from app.projects.models import ProjectMember

    member_res = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == task.project_id,
            ProjectMember.user_id == current_user.id,
        )
    )
    if member_res.scalar_one_or_none() is None and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not a member of this project")


@router.get("/commits/{task_id}", response_model=List[CommitSchema])
async def get_task_commits(
    task_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """Получить все коммиты, связанные с конкретной задачей.

    Раньше здесь не было зависимости get_current_user, поэтому любой
    посетитель мог перебрать task_id и прочитать коммиты чужих задач.
    """
    result = await db.execute(
        select(Task).filter(Task.id == task_id)
        .options(selectinload(Task.commits))
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    await _assert_task_view_access(db, current_user, task)

    return task.commits

@router.post("/branches/{task_id}")
async def create_task_branch(
    task_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user)
):
    """Создать ветку для задачи в GitHub/GitLab"""
    # 1. Получаем задачу и проект
    result = await db.execute(
        select(Task).filter(Task.id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    # 2. Получаем репозиторий проекта
    from app.git.models import GitRepository
    res_repo = await db.execute(select(GitRepository).filter(GitRepository.project_id == task.project_id))
    repo = res_repo.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=400, detail="Git repository not configured for this project")
        
    # 3. Генерируем имя ветки: feature/task-{id}-{slug}
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", task.title.lower()).strip("-")
    branch_name = f"feature/task-{task.id}-{slug}"
    
    # 4. Вызываем провайдера
    from app.git.factory import get_git_provider
    provider = get_git_provider(repo.provider, token=repo.access_token, api_url=repo.api_url)
    
    try:
        await provider.create_branch(repo.id, branch_name)
        
        # 5. Привязываем ветку в БД (для моментального отображения)
        from app.git.models import Branch
        # Ищем или создаем
        res_branch = await db.execute(select(Branch).filter(Branch.name == branch_name, Branch.repository_id == repo.id))
        branch = res_branch.scalar_one_or_none()
        if not branch:
            branch = Branch(repository_id=repo.id, name=branch_name)
            db.add(branch)
            await db.flush()
            
        if branch not in task.branches:
            task.branches.append(branch)
            
        # 6. ПЕРЕХОД: Задача в работу (In Progress)
        from app.tasks.services import TaskStatusService
        await TaskStatusService.move_task_to_status(db, task.id, "IN_PROGRESS")
        
        await db.commit()
        return {"status": "success", "branch_name": branch_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create branch: {str(e)}")
