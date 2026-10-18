"""Управление хранилищем — эндпоинты администратора.

Панель закрывает три вещи, которые иначе требуют правки кода:
лимиты вложений, срок хранения корзины и её автоочистку.

Все три параметра применяются без перезапуска: значения читаются
из базы на каждой загрузке файла и на каждом проходе цикла
очистки.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.projects.models import Project
from app.storage import purge as purge_mod
from app.storage import settings as storage_settings
from app.users.models import User

router = APIRouter()


class StorageUpdate(BaseModel):
    max_file_size_mb: Optional[int] = None
    allowed_extensions: Optional[str] = None
    default_project_limit_mb: Optional[int] = None
    trash_retention_days: Optional[int] = None
    auto_purge_enabled: Optional[bool] = None
    purge_interval_hours: Optional[int] = None


class ProjectLimit(BaseModel):
    limit_mb: Optional[int] = None


class PurgeResult(BaseModel):
    status: str
    removed: int
    files_removed: int
    freed_bytes: int
    retention_days: Optional[int] = None


@router.get("/storage")
async def read_storage(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """Настройки и текущее состояние хранилища."""
    settings = await storage_settings.refresh(db)
    stats = await purge_mod.storage_stats(db)

    return {
        "settings": settings,
        "limits": {
            "max_file_size_mb": (settings["max_file_size_mb"],) + storage_settings.LIMITS["max_file_size_mb"],
            "default_project_limit_mb": (
                settings["default_project_limit_mb"],
            ) + storage_settings.LIMITS["default_project_limit_mb"],
            "trash_retention_days": (
                settings["trash_retention_days"],
            ) + storage_settings.LIMITS["trash_retention_days"],
            "purge_interval_hours": (
                settings["purge_interval_hours"],
            ) + storage_settings.LIMITS["purge_interval_hours"],
        },
        "stats": stats,
    }


@router.patch("/storage")
async def update_storage(
    payload: StorageUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """Меняет настройки хранилища.

    Передаются только изменяемые поля: null означает «не трогать»,
    а не «сбросить в ноль».
    """
    values = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not values:
        raise HTTPException(status_code=400, detail="Нечего менять")

    try:
        settings = await storage_settings.update(db, values, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stats = await purge_mod.storage_stats(db)
    return {"settings": settings, "stats": stats}


@router.patch("/storage/projects/{project_id}/limit")
async def set_project_limit(
    project_id: int,
    payload: ProjectLimit,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """Задаёт лимит хранилища конкретного проекта.

    limit_mb = null возвращает проект к общему лимиту из настроек.
    """
    from app.projects.models import Project

    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Проект не найден")

    if payload.limit_mb is None:
        project.storage_limit_bytes = None
    else:
        low, high = storage_settings.LIMITS["default_project_limit_mb"]
        if not low <= payload.limit_mb <= high:
            raise HTTPException(
                status_code=400, detail=f"limit_mb: допустимо от {low} до {high}"
            )
        project.storage_limit_bytes = payload.limit_mb * 1024 * 1024

    await db.commit()
    stats = await purge_mod.storage_stats(db)
    return {"settings": storage_settings.get(), "stats": stats}


@router.post("/storage/purge", response_model=PurgeResult)
async def purge_now(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """Очищает корзину целиком, независимо от срока хранения."""
    result = await purge_mod.empty_trash(db)
    return PurgeResult(status="success", **result)


@router.post("/storage/purge/expired", response_model=PurgeResult)
async def purge_expired(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """Очищает только то, что уже перевалило через срок хранения.

    Отличается от полной очистки: свежие удаления остаются на месте.
    """
    result = await purge_mod.purge_trash(db)
    return PurgeResult(status="success", **result)