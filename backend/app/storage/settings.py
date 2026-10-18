"""Чтение и запись настроек хранилища с кешем в памяти.

Настройки читаются на каждой загрузке файла, поэтому из базы по
запросу ходить нельзя — как и в реестре моделей, здесь кеш со
словарём, который перезаписывается целиком.

Пока строки в базе нет (первый запуск, миграция только что
применена), действуют значения по умолчанию: приложение обязано
работать без ручной настройки.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.models import StorageSettings

logger = logging.getLogger(__name__)

DEFAULTS: Dict[str, object] = {
    "max_file_size_mb": 25,
    "allowed_extensions": ".png,.jpg,.jpeg,.gif,.pdf,.doc,.docx,.txt,.zip,.log",
    "default_project_limit_mb": 500,
    "trash_retention_days": 7,
    "auto_purge_enabled": True,
    "purge_interval_hours": 6,
}

# Поля, которые администратор может менять из панели.
EDITABLE = tuple(DEFAULTS.keys())

# Разумные границы. Без проверок администратор мог бы выставить
# нулевой лимит (загрузка невозможна) или срок в сто лет (корзина
# растёт бесконечно) — и панель потом пришлось бы чинить руками.
LIMITS = {
    "max_file_size_mb": (1, 1024),
    "default_project_limit_mb": (1, 102400),
    "trash_retention_days": (0, 365),
    "purge_interval_hours": (1, 168),
}

_cache: Optional[Dict[str, object]] = None


def _from_row(row: Optional[StorageSettings]) -> Dict[str, object]:
    if row is None:
        return dict(DEFAULTS)
    return {key: getattr(row, key) for key in DEFAULTS}


def get() -> Dict[str, object]:
    """Текущие настройки. Синхронная: зовётся на пути загрузки файла."""
    return dict(_cache) if _cache is not None else dict(DEFAULTS)


def extensions() -> Tuple[str, ...]:
    raw = str(get()["allowed_extensions"])
    return tuple(
        e.strip().lower()
        for e in raw.split(",")
        if e.strip() and e.strip().startswith(".")
    )


def max_file_size_bytes() -> int:
    return int(get()["max_file_size_mb"]) * 1024 * 1024


def default_project_limit_bytes() -> int:
    return int(get()["default_project_limit_mb"]) * 1024 * 1024


def trash_retention_days() -> int:
    return int(get()["trash_retention_days"])


def auto_purge_enabled() -> bool:
    return bool(get()["auto_purge_enabled"])


def purge_interval_hours() -> int:
    return int(get()["purge_interval_hours"])


async def refresh(db: AsyncSession) -> Dict[str, object]:
    """Перечитывает настройки. Ошибку не поднимает."""
    global _cache
    try:
        row = (
            await db.execute(select(StorageSettings).where(StorageSettings.id == 1))
        ).scalar_one_or_none()
        _cache = _from_row(row)
    except Exception as exc:  # noqa: BLE001 — деградация вместо падения
        logger.warning("Не удалось прочитать настройки хранилища: %s", exc)
        _cache = dict(DEFAULTS)
    return get()


def validate(values: Dict[str, object]) -> Tuple[Dict[str, object], List[str]]:
    """Проверяет и нормализует значения.

    Возвращает (готово к записи, список ошибок). Ошибок может быть
    несколько — показываем все сразу, а не по одной.
    """
    clean: Dict[str, object] = {}
    errors: List[str] = []

    for key, value in values.items():
        if key not in DEFAULTS:
            errors.append(f"Неизвестный параметр: {key}")
            continue

        if isinstance(DEFAULTS[key], bool):
            clean[key] = bool(value)
            continue

        if key == "allowed_extensions":
            exts = [e.strip().lower() for e in str(value).split(",") if e.strip()]
            exts = [e if e.startswith(".") else f".{e}" for e in exts]
            # Нормализация: без точки расширение никогда не совпадёт
            # при проверке загрузки, поэтому пустым результат быть не может.
            exts = sorted(set(exts))
            if not exts:
                errors.append("Список расширений не может быть пустым")
                continue
            clean[key] = ",".join(exts)
            continue

        try:
            number = int(value)
        except (TypeError, ValueError):
            errors.append(f"{key}: ожидалось целое число")
            continue

        low, high = LIMITS.get(key, (1, 10**9))
        if not low <= number <= high:
            errors.append(f"{key}: допустимо от {low} до {high}")
            continue
        clean[key] = number

    return clean, errors


async def update(
    db: AsyncSession, values: Dict[str, object], user_id: int
) -> Dict[str, object]:
    """Записывает настройки и обновляет кеш."""
    global _cache

    clean, errors = validate(values)
    if errors:
        raise ValueError("; ".join(errors))

    row = (
        await db.execute(select(StorageSettings).where(StorageSettings.id == 1))
    ).scalar_one_or_none()
    if row is None:
        row = StorageSettings(id=1, **clean)
        db.add(row)
    else:
        for key, value in clean.items():
            setattr(row, key, value)
        row.updated_by_id = user_id

    await db.commit()
    _cache = _from_row(row)
    return get()