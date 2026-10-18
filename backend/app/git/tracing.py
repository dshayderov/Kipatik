"""Трассировка коммита к задаче по смыслу изменений — второй эшелон.

Порядок работы при обработке коммита:

  1. Регулярки: `#123`, `PROJ-123`, ключ из настроек проекта.
     Они точны, бесплатны и объяснимы человеку.
  2. Модель — только если регулярки не нашли ничего.

Модель не перебивает найденное регулярками и не заменяет их: она лишь
предлагает, а решение остаётся за человеком. Предложение хранится как
связь с `status='proposed'`, пока пользователь её не подтвердил.

Без модели поведение прежний: `unlinked=True` означает «не нашли
правилами», а не «не нашли вообще».
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.git.models import (
    Commit,
    CommitFile,
    GitRepository,
    TaskGitLink,
    task_commits,
)
from app.tasks.models import Task

# Импорт на уровне модуля, чтобы объект модели можно было подменить в
# тестах. Само по себе это безопасно: сервис кодировщика не импортирует
# torch на верхнем уровне, torch грузится только внутри load().
from app.ai.api import (  # noqa: E402
    ModelUnavailable,
    build_commit_representation,
    encoder,
)
from app.git.patches import build_commit_diff, ensure_commit_patch  # noqa: E402

logger = logging.getLogger(__name__)


def proposed_columns_present(db) -> bool:
    """Проверяет, применена ли миграция с полями status/reason.

    Без проверки падение было бы на любом запросе трассировки после
    обновления кода, но до `alembic upgrade`.
    """
    from sqlalchemy import inspect

    try:
        return {"status", "reason"}.issubset(
            set(inspect(db.bind).get_columns("task_git_links")[0].keys())
        )
    except Exception:  # noqa: BLE001 — при любой проблеме считаем, что миграция есть
        return True


def _is_open_task(task: Task) -> bool:
    """Задача считается открытой, пока она не в архиве.

    Признак «в архиве» у нас один — колонка доски: у завершённых
    досок column_id остаётся, но помечается категорией. Поэтому
    проверяем сам факт наличия колонки у задачи, а не её значение.
    """
    if task.column_id is None:
        return False
    return True


async def collect_candidates(
    db: AsyncSession, repo: GitRepository, commit_id: int, limit: int
) -> List[Dict]:
    """Задачи проекта, среди которых ищем совпадение.

    Уже привязанные к этому коммиту исключены: повторно предлагать
    существующую связь незачем.
    """
    linked = set(
        (
            await db.execute(
                select(TaskGitLink.target_id).where(
                    TaskGitLink.link_type == "commit",
                    TaskGitLink.target_id == commit_id,
                )
            )
        ).scalars().all()
    )

    tasks = (
        await db.execute(
            select(Task)
            .where(Task.project_id == repo.project_id)
            .order_by(Task.updated_at.desc().nullslast())
            .limit(limit * 3)  # часть отсеется по фильтру ниже
        )
    ).scalars().all()

    out: List[Dict] = []
    for t in tasks:
        if t.id in linked:
            continue
        if not _is_open_task(t):
            continue
        text = f"{t.title}. {t.description or ''}".strip()
        if not text:
            continue
        out.append({"id": t.id, "description": text[:1500]})
        if len(out) >= limit:
            break
    return out


async def _commit_context(db: AsyncSession, commit: Commit) -> Dict:
    """Готовит текст коммита в том виде, в каком его ждёт модель."""
    files = (
        await db.execute(select(CommitFile).where(CommitFile.commit_id == commit.id))
    ).scalars().all()

    # Правки догружаем только по явному разрешению. Это запрос к API
    # провайдера на каждый коммит, и делать его молча при трассировке
    # означало бы незаметно съедать лимиты. Обычно правки заполняются
    # заранее через POST /git/{id}/patches/backfill.
    if settings.GIT_TRACE_FETCH_PATCHES and not any(f.patch for f in files):
        try:
            await ensure_commit_patch(db, commit)
            files = (
                await db.execute(select(CommitFile).where(CommitFile.commit_id == commit.id))
            ).scalars().all()
        except Exception as exc:  # noqa: BLE001 — без правок модель отработает хуже, но не упадёт
            logger.warning("Не удалось догрузить правки %s: %s", commit.sha[:7], exc)

    diff_text = build_commit_diff(files)
    return {
        "repr": build_commit_representation(diff_text, commit.message or ""),
        "files": [f.path for f in files],
        "has_patches": any(f.patch for f in files),
    }


async def trace_commit(
    db: AsyncSession,
    repo: GitRepository,
    commit: Commit,
    deadline_seconds: Optional[float] = None,
) -> Dict:
    """Предлагает задачу для коммита.

    Ничего не записывает: вызывающий код сам решает, сохранять ли
    предложение. Это позволяет прогонять трассировку вручную из API
    без побочных эффектов.
    """
    started = time.monotonic()

    result: Dict = {
        "commit_id": commit.id,
        "sha": commit.sha,
        "enabled": settings.CODE_MODEL_ENABLED,
        "reason": None,
        "task_id": None,
        "confidence": None,
        "threshold": settings.CODE_MODEL_TRACE_THRESHOLD,
        "candidates": 0,
        "has_patches": False,
        "elapsed_ms": 0,
    }

    if not settings.CODE_MODEL_ENABLED:
        result["reason"] = "disabled"
        return result

    candidates = await collect_candidates(
        db, repo, commit.id, settings.CODE_MODEL_TRACE_LIMIT
    )
    result["candidates"] = len(candidates)
    if not candidates:
        result["reason"] = "no_candidates"
        return result

    if deadline_seconds is not None and time.monotonic() - started > deadline_seconds:
        result["reason"] = "out_of_time"
        return result

    if not encoder.load():
        result["reason"] = encoder.status()["reason"] or "unavailable"
        return result

    context = await _commit_context(db, commit)
    result["has_patches"] = context["has_patches"]

    try:
        match = encoder.link_commit_to_task(
            commit_repr=context["repr"],
            commit_files=context["files"],
            candidates=candidates,
        )
    except ModelUnavailable as exc:
        result["reason"] = str(exc)
        return result

    result["confidence"] = match["confidence"]
    result["semantic"] = match["semantic"]
    result["all_scores"] = match["all_scores"]
    result["task_id"] = match["task_id"]
    if match["task_id"] is None:
        result["reason"] = "below_threshold"

    result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    return result


async def propose_link(
    db: AsyncSession,
    commit: Commit,
    task_id: int,
    confidence: float,
    semantic: Optional[float] = None,
    create_m2m: bool = True,
) -> Optional[TaskGitLink]:
    """Сохраняет предложение связи.

    Статус `proposed` отличает предложение модели от подтверждённой
    связи: показывать «Коммиты (7)» пользователю нужно только по
    подтверждённым.
    """
    if not proposed_columns_present(db):
        return None

    existing = (
        await db.execute(
            select(TaskGitLink).where(
                TaskGitLink.task_id == task_id,
                TaskGitLink.link_type == "commit",
                TaskGitLink.target_id == commit.id,
            )
        )
    ).scalar_one_or_none()

    if existing:
        # Отклонённое предложение не предлагается заново. Раньше связь
        # при отклонении удалялась целиком, и модель через пять минут
        # предлагала тот же коммит в ту же задачу снова — по кругу.
        if existing.status == "rejected":
            return existing

        # Уже связан — доводим провенанс, но не перебиваем решение человека.
        # Уверенность обновляем только у ещё не подтверждённых предложений:
        # раз человек подтвердил связь, новая оценка модели уже ничего
        # не решает.
        if existing.status == "proposed" and existing.created_by_id is None:
            existing.confidence = confidence
        return existing

    link = TaskGitLink(
        task_id=task_id,
        link_type="commit",
        target_id=commit.id,
        source="model",
        confidence=confidence,
        status="proposed",
        reason=f"Предложено по смыслу изменений (уверенность {confidence:.2f})",
    )
    db.add(link)

    if create_m2m:
        # Через ассоциативную таблицу, а не через task.commits.
        #
        # task.commits — ленивая связь, и после commit сессия сбрасывает
        # её состояние: обращение к ней здесь требовало бы IO вне
        # greenlet и падало с MissingGreenlet. Раньше это работало
        # только потому, что трассировка запускалась вручную из
        # свежего запроса; в фоновой задаче сессия успевает истечь.
        exists = (
            await db.execute(
                select(task_commits.c.task_id).where(
                    task_commits.c.task_id == task_id,
                    task_commits.c.commit_id == commit.id,
                )
            )
        ).scalar()
        if exists is None:
            await db.execute(
                task_commits.insert().values(task_id=task_id, commit_id=commit.id)
            )

    await db.flush()
    return link


async def suggest_for_unlinked_commits(
    db: AsyncSession, repo: GitRepository, limit: int, token: Optional[str] = None
) -> Dict:
    """Прогоняет трассировку по коммитам репозитория без привязок.

    Точка входа для фоновой задачи и для ручного запуска из API.
    """
    linked = set(
        (
            await db.execute(
                select(TaskGitLink.target_id).where(TaskGitLink.link_type == "commit")
            )
        ).scalars().all()
    )

    commits = (
        await db.execute(
            select(Commit)
            .where(Commit.repository_id == repo.id)
            .order_by(Commit.timestamp.desc().nullslast())
            .limit(limit * 2)
        )
    ).scalars().all()

    candidates_pool = [c for c in commits if c.id not in linked][:limit]

    stats = {
        "examined": len(candidates_pool),
        "proposed": 0,
        "already_linked": 0,
        "below_threshold": 0,
        "skipped": 0,
        "no_patches": 0,
        "reasons": [],
    }

    for commit in candidates_pool:
        deadline = settings.CODE_MODEL_TRACE_BUDGET_SECONDS
        res = await trace_commit(db, repo, commit, deadline_seconds=deadline)
        reason = res.get("reason")

        if reason == "disabled" or reason == "unavailable" or reason == "tokenizer_missing" \
                or reason == "tracer_missing" or reason == "classifier_missing":
            stats["skipped"] += 1
            if reason and reason not in stats["reasons"]:
                stats["reasons"].append(reason)
            break

        if reason == "below_threshold":
            stats["below_threshold"] += 1
            continue
        if reason == "no_candidates":
            stats["skipped"] += 1
            continue
        if reason == "out_of_time":
            stats["skipped"] += 1
            continue

        if not res["has_patches"]:
            stats["no_patches"] += 1

        task_id = res.get("task_id")
        if not task_id:
            stats["below_threshold"] += 1
            continue

        link = await propose_link(
            db, commit, task_id, res["confidence"], res.get("semantic")
        )
        if link:
            stats["proposed"] += 1

    await db.commit()
    return stats