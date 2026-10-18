"""Очистка корзины и осиротевших файлов.

Корзина — это вложения со статусом deleted и отметкой времени
удаления. Физические файлы при удалении не трогаются: строка
в базе помечается, а сам файл живёт, пока не истечёт срок.

Две разные операции, и их важно не путать:
  * purge_trash — безвозвратно удаляет то, что пролежало дольше
    срока хранения. То, что удалили недавно, не трогает.
  * empty_trash — удаляет всё содержимое корзины, независимо от
    срока. Это ручная кнопка «очистить корзину целиком».

Обе возвращают статистику и попутно приводят в порядок счётчик
storage_used_bytes проекта: он копится от загрузок, и без
пересчёта со временем расходится с реальностью.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.projects.models import Project
from app.storage import settings as st
from app.tasks.models import Attachment

logger = logging.getLogger(__name__)


def _physical_path(attachment: Attachment) -> str:
    return os.path.join("uploads", attachment.path)


def _remove_file(attachment: Attachment) -> bool:
    """Удаляет файл с диска. True, если файл был и удалён."""
    path = _physical_path(attachment)
    try:
        if os.path.exists(path):
            os.remove(path)
            return True
    except OSError as exc:
        # Файл занят другим процессом — строку из базы всё равно
        # убираем, иначе корзина будет расти бесконечно.
        logger.warning("Не удалось удалить файл %s: %s", path, exc)
    return False


async def _subtract_usage(db: AsyncSession, rows: List[Attachment]) -> None:
    """Снимает освобождённый объём со счётчиков проектов."""
    by_project: Dict[int, int] = {}
    for row in rows:
        if row.project_id:
            by_project[row.project_id] = (
                by_project.get(row.project_id, 0) + (row.size_bytes or 0)
            )

    for project_id, freed in by_project.items():
        project = (
            await db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        if project is not None:
            project.storage_used_bytes = max(
                0, (project.storage_used_bytes or 0) - freed
            )


async def purge_trash(
    db: AsyncSession, retention_days: Optional[int] = None
) -> Dict[str, object]:
    """Безвозвратно удаляет из корзины то, что старше срока хранения."""
    days = st.trash_retention_days() if retention_days is None else retention_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(0, days))

    rows = (
        await db.execute(
            select(Attachment).where(
                Attachment.status == "deleted",
                Attachment.deleted_at.is_not(None),
                Attachment.deleted_at < cutoff,
            )
        )
    ).scalars().all()

    files_removed = 0
    freed = 0
    for row in rows:
        if _remove_file(row):
            files_removed += 1
        freed += row.size_bytes or 0
        await db.delete(row)

    if rows:
        await _subtract_usage(db, rows)
    await db.commit()

    return {
        "removed": len(rows),
        "files_removed": files_removed,
        "freed_bytes": freed,
        "retention_days": days,
    }


async def empty_trash(db: AsyncSession) -> Dict[str, object]:
    """Удаляет всё содержимое корзины, независимо от срока хранения."""
    rows = (
        await db.execute(select(Attachment).where(Attachment.status == "deleted"))
    ).scalars().all()

    files_removed = 0
    freed = 0
    for row in rows:
        if _remove_file(row):
            files_removed += 1
        freed += row.size_bytes or 0
        await db.delete(row)

    if rows:
        await _subtract_usage(db, rows)
    await db.commit()

    return {
        "removed": len(rows),
        "files_removed": files_removed,
        "freed_bytes": freed,
    }


async def cleanup_orphans(db: AsyncSession, older_than_hours: int = 24) -> Dict[str, object]:
    """Убирает записи о файлах, которые так и не прикрепили к задаче.

    Файл при загрузке сначала попадает в корзину со статусом orphan
    и окончательно привязывается позже. Если привязки не случилось,
    запись живёт вечно, удерживая место в квоте.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
    rows = (
        await db.execute(
            select(Attachment).where(
                Attachment.status == "orphan", Attachment.created_at < cutoff
            )
        )
    ).scalars().all()

    files_removed = 0
    freed = 0
    for row in rows:
        if _remove_file(row):
            files_removed += 1
        freed += row.size_bytes or 0
        await db.delete(row)

    if rows:
        await _subtract_usage(db, rows)
    await db.commit()

    return {
        "removed": len(rows),
        "files_removed": files_removed,
        "freed_bytes": freed,
    }


async def storage_stats(db: AsyncSession) -> Dict[str, object]:
    """Сводка по хранилищу для панели администратора."""
    by_status = (
        await db.execute(
            select(Attachment.status, func.count(), func.coalesce(func.sum(Attachment.size_bytes), 0))
            .group_by(Attachment.status)
        )
    ).all()
    status_map = {
        status: {"count": int(count), "bytes": int(size)}
        for status, count, size in by_status
    }

    project_rows = (
        await db.execute(
            select(
                Project.id,
                Project.name,
                Project.storage_used_bytes,
                Project.storage_limit_bytes,
            ).order_by(Project.storage_used_bytes.desc())
        )
    ).all()

    # Проект без собственного лимита (null) берёт общий из настроек —
    # иначе в панели он выглядел бы как проект с нулём вместо лимита.
    default_limit = st.default_project_limit_bytes()

    projects = [
        {
            "id": pid,
            "name": name,
            "used_bytes": int(used or 0),
            "limit_bytes": int(limit or default_limit),
            "own_limit": bool(limit),
            "usage_percent": (
                round(100 * (used or 0) / limit, 1) if limit else
                round(100 * (used or 0) / default_limit, 1) if default_limit else 0.0
            ),
        }
        for pid, name, used, limit in project_rows
    ]

    active = status_map.get("active", {"count": 0, "bytes": 0})
    trash = status_map.get("deleted", {"count": 0, "bytes": 0})
    orphan = status_map.get("orphan", {"count": 0, "bytes": 0})

    return {
        "active": active,
        "trash": trash,
        "orphan": orphan,
        "total_bytes": active["bytes"] + trash["bytes"] + orphan["bytes"],
        "projects": projects,
        # Сколько в корзине уже перевалило через срок: именно столько
        # исчезнет при ближайшей автоочистке.
        "trash_expired": await count_expired(db),
    }


async def count_expired(db: AsyncSession) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=st.trash_retention_days())
    return (
        await db.execute(
            select(func.count(Attachment.id)).where(
                Attachment.status == "deleted",
                Attachment.deleted_at.is_not(None),
                Attachment.deleted_at < cutoff,
            )
        )
    ).scalar() or 0