"""Управление нейросетевыми моделями — эндпоинты админки.

Панель показывает, какие модели есть, какие включены, чем это
решено (окружение или решение администратора), сколько занимает
артефакт на диске и загружена ли модель в память прямо сейчас.

Переключение действует без перезапуска: решение пишется в базу и
сразу попадает в кеш реестра, откуда его читает горячий путь —
синхронизация коммитов и расчёт прогресса.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import api as ai_api
from app.models.ai_settings import AIModelSetting
from app.api import deps
from app.users.models import User

router = APIRouter()


class ModelToggle(BaseModel):
    enabled: bool


class ModelOut(BaseModel):
    key: str
    title_key: str
    purpose_key: str
    kind: str
    enabled: bool
    env_default: bool
    overridden: bool
    depends_on: List[str] = []
    artifact: Optional[str] = None
    artifact_exists: bool = False
    artifact_size_mb: float = 0.0
    blocked_by: List[str] = []
    # Состояние в памяти заполняется при ответе: оно не хранится в базе.
    loaded: bool = False
    blocked_reason: Optional[str] = None
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


def _require_admin(current_user: User) -> None:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not a superuser")


@router.get("/models", response_model=List[ModelOut])
async def list_models(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """Список моделей с их состоянием.

    Перечитывает кеш реестра из базы: настройки мог поменять другой
    администратор, а процесс-копия мог ещё не увидеть изменения.
    """
    await ai_api.refresh(db)

    rows = (
        await db.execute(select(AIModelSetting))
    ).scalars().all()
    stamps = {r.key: r for r in rows}

    from app.ai.api import type_classifier, encoder

    loaded = {
        ai_api.KEY_ENCODER: encoder.status()["loaded_flag"],
        ai_api.KEY_TYPE_CLASSIFIER: type_classifier.status()["loaded_flag"],
        ai_api.KEY_PROGRESS: True,  # правила, в памяти не держатся
    }

    out: List[ModelOut] = []
    for item in ai_api.all_descriptions():
        stamp = stamps.get(item["key"])
        row = ModelOut(**item)
        row.loaded = bool(loaded.get(item["key"], False))
        if stamp is not None:
            row.updated_at = stamp.updated_at.isoformat() if stamp.updated_at else None
            if stamp.updated_by_id:
                author = (
                    await db.execute(select(User).where(User.id == stamp.updated_by_id))
                ).scalar_one_or_none()
                if author is not None:
                    row.updated_by = author.full_name or author.email
        out.append(row)

    return out


@router.patch("/models/{model_key}", response_model=ModelOut)
async def set_model_enabled(
    model_key: str,
    payload: ModelToggle,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """Включает или выключает модель."""
    _require_admin(current_user)

    if model_key not in ai_api.MODEL_KEYS:
        raise HTTPException(status_code=404, detail="Unknown model")

    # Кодировщик нельзя оставить включённым при выключенной модели,
    # от которой он зависит, — проверка в реестре симметрична.
    if payload.enabled and model_key == ai_api.KEY_TYPE_CLASSIFIER:
        if not ai_api.is_enabled(ai_api.KEY_ENCODER):
            raise HTTPException(
                status_code=400,
                detail="Классификатор типов работает поверх кодировщика: "
                       "сначала включите кодировщик",
            )

    await ai_api.set_enabled(db, model_key, payload.enabled, current_user.id)

    return await _single_model(db, model_key)


@router.post("/models/{model_key}/unload")
async def unload_model(
    model_key: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Dict[str, Any]:
    """Выгружает модель из памяти.

    Снимает веса раньше, чем они понадобятся снова: после выгрузки
    повторная загрузка в том же процессе ненадёжна — аллокатор torch
    удерживает освобождённый блок. В рабочем сценарии это не мешает,
    потому что страницы файла остаются в кеше ОС.
    """
    _require_admin(current_user)

    if model_key == ai_api.KEY_PROGRESS:
        raise HTTPException(
            status_code=400,
            detail="Оценка объёма не занимает память: её нельзя выгрузить",
        )

    from app.ai.api import type_classifier, encoder

    # Выгружаются обе: классификатор считает поверх эмбеддингов
    # кодировщика, поэтому оставить голову в памяти без него бессмысленно.
    if model_key == ai_api.KEY_TYPE_CLASSIFIER:
        before = type_classifier.status()["loaded_flag"]
        type_classifier.unload()
        after = type_classifier.status()["loaded_flag"]
    else:
        before = encoder.status()["loaded_flag"]
        encoder.unload()
        type_classifier.unload()
        after = encoder.status()["loaded_flag"]

    return {"status": "success", "model": model_key, "was_loaded": before,
            "now_loaded": after}


@router.post("/models/reload")
async def reload_models(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Dict[str, Any]:
    """Перечитывает настройки и прогревает включённые модели.

    Нужно после выгрузки: включение модели само по себе её не
    поднимает — прогрев происходит при старте или при первом
    обращении.
    """
    _require_admin(current_user)
    await ai_api.refresh(db)

    if not ai_api.is_enabled(ai_api.KEY_ENCODER):
        return {"status": "skipped", "reason": "encoder_disabled"}

    from app.ai.api import type_classifier, encoder

    import asyncio

    ok = await asyncio.to_thread(encoder.load)
    if ok and ai_api.is_enabled(ai_api.KEY_TYPE_CLASSIFIER):
        await asyncio.to_thread(type_classifier.load)
    return {"status": "success" if ok else "failed",
            "error": encoder.status().get("error")}


async def _single_model(db: AsyncSession, model_key: str) -> ModelOut:
    """Текущее состояние одной модели — тем же составом, что и список."""
    await ai_api.refresh(db)

    stamp = (
        await db.execute(select(AIModelSetting).where(AIModelSetting.key == model_key))
    ).scalar_one_or_none()

    from app.ai.api import type_classifier, encoder

    loaded = {
        ai_api.KEY_ENCODER: encoder.status()["loaded_flag"],
        ai_api.KEY_TYPE_CLASSIFIER: type_classifier.status()["loaded_flag"],
        ai_api.KEY_PROGRESS: True,
    }

    item = ai_api.describe(model_key)
    row = ModelOut(**item)
    row.loaded = bool(loaded.get(model_key, False))
    if stamp is not None:
        row.updated_at = stamp.updated_at.isoformat() if stamp.updated_at else None
    return row