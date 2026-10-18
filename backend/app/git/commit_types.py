"""Определение типа коммита моделью (ЛР №3).

Тип считается один раз — когда коммит привязывается к задаче — и
хранится в самом коммите. В карточке он только читается.

Почему не считать на лету: классификация на CPU занимает сотни
миллисекунд, и карточка с пятью коммитами грузилась бы на секунды
дольше.

Ограничение, о котором нужно помнить: на синтетических примерах
классификатор уверенно различает только bugfix и feature, остальные
классы он склонен сводить к feature и chore. Поэтому тип показывается
вместе с уверенностью, а не как установленный факт.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.git.models import Commit, CommitFile, TaskGitLink

logger = logging.getLogger(__name__)

# Классы, для которых классификатор проверен на осмысленных примерах.
# Для остальных тип пока ориентировочный, и это видно по уверенности.
RELIABLE_TYPES = {"bugfix", "feature"}


async def classify_and_store(db: AsyncSession, commit: Commit) -> Optional[str]:
    """Определяет тип коммита и сохраняет его. Возвращает тип или None."""
    if not settings.CODE_MODEL_ENABLED or not settings.CODE_MODEL_CLASSIFY:
        return None
    if commit.commit_type:
        return commit.commit_type

    from app.ai.api import (
        ModelUnavailable,
        build_commit_representation,
        type_classifier,
    )
    from app.git.patches import build_commit_diff

    if not type_classifier.load():
        return None

    files = (
        await db.execute(select(CommitFile).where(CommitFile.commit_id == commit.id))
    ).scalars().all()

    diff_text = build_commit_diff(files)
    try:
        result = type_classifier.classify_commit(
            build_commit_representation(diff_text, commit.message or "")
        )
    except ModelUnavailable as exc:
        logger.warning("Тип коммита %s не определён: %s", commit.sha[:7], exc)
        return None

    commit.commit_type = result["commit_type"]
    commit.commit_type_confidence = result["confidence"]
    commit.commit_type_at = datetime.now(timezone.utc)
    return commit.commit_type


async def classify_linked_commits(
    db: AsyncSession, commit_ids: List[int], flush: bool = True
) -> Dict:
    """Определяет тип для набора коммитов.

    Ошибка на одном коммите не отменяет остальные: тип — украшение,
    а не основание для отказа в привязке.
    """
    stats = {"examined": 0, "classified": 0, "skipped": 0, "failed": 0}

    if not commit_ids or not settings.CODE_MODEL_ENABLED:
        return stats
    if not settings.CODE_MODEL_CLASSIFY:
        return stats

    commits = (
        await db.execute(select(Commit).where(Commit.id.in_(commit_ids)))
    ).scalars().all()

    for commit in commits:
        stats["examined"] += 1
        if commit.commit_type:
            stats["skipped"] += 1
            continue
        try:
            kind = await classify_and_store(db, commit)
        except Exception as exc:  # noqa: BLE001
            stats["failed"] += 1
            logger.warning(
                "Не удалось определить тип коммита %s: %s", commit.sha[:7], exc
            )
            continue
        if kind:
            stats["classified"] += 1
        else:
            stats["failed"] += 1

    if flush and stats["classified"]:
        await db.flush()

    return stats


async def backfill_commit_types(
    db: AsyncSession, repo_id: Optional[int] = None, limit: int = 50
) -> Dict:
    """Определяет тип для уже привязанных коммитов без него.

    Заполняет то, что было привязано до включения классификации, и
    подтягивает коммиты, чей тип не удалось посчитать в момент привязки
    (модель тогда ещё не прогревалась).
    """
    stats = {"examined": 0, "classified": 0, "failed": 0}

    if not settings.CODE_MODEL_ENABLED or not settings.CODE_MODEL_CLASSIFY:
        return stats

    linked_ids = (
        (
            await db.execute(
                select(TaskGitLink.target_id).where(
                    TaskGitLink.link_type == "commit",
                    TaskGitLink.status != "proposed",
                )
            )
        )
        .scalars()
        .all()
    )

    query = select(Commit).where(
        Commit.commit_type.is_(None), Commit.id.in_(linked_ids or {0})
    )
    if repo_id is not None:
        query = query.where(Commit.repository_id == repo_id)
    query = query.order_by(Commit.timestamp.desc().nullslast()).limit(limit)

    commits = (await db.execute(query)).scalars().all()
    stats["examined"] = len(commits)

    for commit in commits:
        try:
            if await classify_and_store(db, commit):
                stats["classified"] += 1
            else:
                stats["failed"] += 1
        except Exception as exc:  # noqa: BLE001
            stats["failed"] += 1
            logger.warning("Тип %s не определён: %s", commit.sha[:7], exc)

    await db.commit()
    return stats


def describe(commit: Commit, t) -> Dict:
    """Данные для карточки: тип, уверенность и насколько ему верить."""
    kind = commit.commit_type
    confidence = commit.commit_type_confidence
    return {
        "type": kind,
        "confidence": confidence,
        # Уверенность модели сама по себе не показатель качества:
        # для bugfix и feature она обычно выше 0.8, для остальных
        # классов занижена и завышена одновременно.
        "reliable": bool(kind in RELIABLE_TYPES and (confidence or 0) >= 0.5),
        "at": commit.commit_type_at.isoformat() if commit.commit_type_at else None,
    }