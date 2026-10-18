"""Оценка прогресса задачи по её Git-активности.

Использует модуль правил из лабораторной работы №2
(`app/ai/code_model/progress_estimator.py`) — нейросеть здесь не нужна,
поэтому оценка работает даже до установки torch.

Что этот слой добавляет к формуле из лабораторной:

* `expected_volume` считается по реальным данным системы, а не берётся
  константой 26. Та константа — размер одного коммита в стороннем
  датасете GitHub-issues, тогда как здесь на задачу суммируются все её
  коммиты, и при 26 прогресс упирался в 100 % после первых же правок.
* `files_touched` передаётся настоящими файлами связанных коммитов.
  В лабораторной работе в `calculate_progress_detailed` этот ключ не
  передавался вовсе, из-за чего семантическая составляющая всегда была
  нулевой — независимо от того, какие файлы коммиты меняли.
* Возвращается уверенность в оценке: из скольких составляющих сложился
  результат. Пользователь должен видеть, когда цифре доверять нельзя.
* Считается динамика по дням — по объёму, это единственная составляющая,
  у которой есть история во времени.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.code_model.progress_estimator import (
    calculate_progress_detailed,
    extract_checklist_items,
    extract_files_from_body,
    percentile,
)
from app.core.config import settings
from app.git.models import Commit, CommitFile, TaskGitLink
from app.tasks.models import SubTask, Task

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------- #
# Вспомогательное
# --------------------------------------------------------------------- #
def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """SQLite отдаёт naive datetime, PostgreSQL — aware с tz."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


# Раскладка весов новой формулы. Дублируется здесь только для отчёта:
# какие составляющие реально участвовали в расчёте.
def _weights_for(has_subtasks: bool, has_file_mentions: bool) -> Dict[str, float]:
    if has_subtasks:
        return {"structural": 0.6, "completion": 0.4}
    return {"structural": 0.0, "completion": 1.0}


def judge_confidence(
    has_commits: bool,
    has_subtasks: bool,
    has_file_mentions: bool,
    expected_source: str,
) -> tuple:
    """Возвращает (уровень, причины).

    Уровень зависит от числа составляющих, которые реально участвовали,
    и от качества калибровки ожидаемого объёма.
    """
    reasons: List[str] = []

    if not has_subtasks:
        reasons.append("no_subtasks")
    if not has_file_mentions:
        reasons.append("no_file_mentions")
    if not has_commits:
        reasons.append("no_commits")
    if expected_source == "default":
        reasons.append("expected_volume_is_default")

    parts = sum([has_subtasks, has_file_mentions, has_commits])

    if not has_commits:
        level = "low"
    elif parts == 3 and expected_source == "project":
        level = "high"
    elif parts >= 2:
        level = "medium"
    else:
        level = "low"

    return level, reasons


# --------------------------------------------------------------------- #
# Калибровка ожидаемого объёма
# --------------------------------------------------------------------- #
async def _per_task_totals(
    db: AsyncSession, project_id: Optional[int], exclude_task_id: Optional[int] = None
) -> List[int]:
    """Суммарный объём изменений по каждой задаче.

    Считаем по задачам, у которых есть привязанные коммиты: только такие
    задачи дают пригодное наблюдение. Единица измерения — «строк на задачу»,
    ровно та же, что используется в формуле, поэтому сравнение корректно.

    exclude_task_id исключает оцениваемую задачу. Без этого перцентиль по
    выборке из одной задачи равен её же объёму, и объёмная составляющая
    всегда даёт 1.0 — оценка перестаёт что-либо измерять.
    """
    stmt = (
        select(
            TaskGitLink.task_id.label("task_id"),
            func.coalesce(func.sum(CommitFile.additions + CommitFile.deletions), 0).label("volume"),
        )
        .join(Commit, Commit.id == TaskGitLink.target_id)
        .join(CommitFile, CommitFile.commit_id == Commit.id)
        .join(Task, Task.id == TaskGitLink.task_id)
        .where(TaskGitLink.link_type == "commit")
        .group_by(TaskGitLink.task_id)
    )
    if project_id is not None:
        stmt = stmt.where(Task.project_id == project_id)
    if exclude_task_id is not None:
        stmt = stmt.where(TaskGitLink.task_id != exclude_task_id)

    rows = (await db.execute(stmt)).all()
    return [int(r.volume) for r in rows if int(r.volume or 0) > 0]


def _shrunk_expected(observed: int, sample: int, prior: int, strength: int) -> tuple:
    """Оценка объёма, стянутая к априорному значению.

    Перцентиль по выборке из одной-двух задач — это не измерение, а
    отдельное наблюдение: посчитанный по нему объём почти всегда
    оказывается равным объёму соседней задачи, и прогресс уезжает
    к 100%. Классический приём — стягивание к априори: вес данных
    растёт с размером выборки, но при малой выборке оценка лишь
    частично опирается на неё.

        w = n / (n + K),   ожидаемый = w·наблюдение + (1 − w)·априор

    K — сила априора, по умолчанию равна минимальной выборке, при
    которой данным можно доверять. При n → ∞ стягивание исчезает.
    """
    if sample <= 0:
        return max(1, prior), 0.0
    w = sample / (sample + max(1, strength))
    blended = w * observed + (1 - w) * prior
    return max(1, int(round(blended))), round(w, 3)


async def resolve_expected_volume(
    db: AsyncSession, project_id: Optional[int], task_id: Optional[int] = None
) -> Dict:
    """75-й перцентиль объёма по задачам, стянутый к априорному значению.

    Каскад источников: проект → вся система → настройка. Чем ближе
    источник к текущему проекту, тем больше ему вес; при малой выборке
    вес уменьшается см. _shrunk_expected.

    Оцениваемая задача из выборки исключена (см. _per_task_totals).
    """
    prior = settings.PROGRESS_DEFAULT_EXPECTED_VOLUME
    minimum = settings.PROGRESS_MIN_TASKS_FOR_CALIBRATION
    strength = settings.PROGRESS_CALIBRATION_PRIOR_STRENGTH

    async def build(totals: List[int], source: str) -> Dict:
        raw = int(percentile(totals, 75))
        value, weight = _shrunk_expected(raw, len(totals), prior, strength)
        return {
            "expected_volume": value,
            "source": source,
            "sample": len(totals),
            "expected_volume_raw": raw,
            "expected_volume_weight": weight,
        }

    if project_id is not None:
        totals = await _per_task_totals(db, project_id, exclude_task_id=task_id)
        if totals:
            return await build(
                totals, "project" if len(totals) >= minimum else "project_small"
            )

    totals = await _per_task_totals(db, None, exclude_task_id=task_id)
    if totals:
        return await build(totals, "global" if len(totals) >= minimum else "global_small")

    return {
        "expected_volume": max(1, prior),
        "source": "default",
        "sample": 0,
        "expected_volume_raw": None,
        "expected_volume_weight": 0.0,
    }


# --------------------------------------------------------------------- #
# Основная оценка
# --------------------------------------------------------------------- #
async def get_task_progress(db: AsyncSession, task: Task) -> Dict:
    """Считает прогресс задачи и всё, что нужно для объяснения результата."""
    if not settings.PROGRESS_ENABLED:
        return {"available": False, "reason": "disabled"}

    # --- привязанные коммиты ---
    # Только подтверждённые связи. Предложения модели ждут решения
    # человека и в прогресс не идут: иначе метрика росла бы от того,
    # что модель что-то предположила, а человек ещё не согласился.
    # Отклонённые связи — тоже не работа: человек сказал, что это
    # не та задача.
    link_rows = (
        await db.execute(
            select(TaskGitLink).where(
                TaskGitLink.task_id == task.id,
                TaskGitLink.link_type == "commit",
                TaskGitLink.status.notin_(("proposed", "rejected")),
            )
        )
    ).scalars().all()
    commit_ids = [l.target_id for l in link_rows]

    commits: List[Commit] = []
    files_by_commit: Dict[int, List[CommitFile]] = {}
    if commit_ids:
        commits = list(
            (
                await db.execute(select(Commit).where(Commit.id.in_(commit_ids)))
            ).scalars().all()
        )
        for f in (
            await db.execute(select(CommitFile).where(CommitFile.commit_id.in_(commit_ids)))
        ).scalars().all():
            files_by_commit.setdefault(f.commit_id, []).append(f)

    # Связь может остаться на удалённый коммит: target_id у task_git_links
    # не внешний ключ, поэтому при удалении репозитория она переживает
    # коммит. Такие id выбрасываем, иначе счётчик коммитов врал бы.
    alive_ids = {c.id for c in commits}
    dropped = len(commit_ids) - len(alive_ids)
    commit_ids = [cid for cid in commit_ids if cid in alive_ids]

    # --- объём ---
    # volume_progress в модуле считает строки, начинающиеся с + и -,
    # в тексте диффа. Текста диффа в базе нет, но additions/deletions
    # в commit_files — это ровно те же строки, посчитанные провайдером.
    per_commit_volume: Dict[int, int] = {}
    for cid in commit_ids:
        per_commit_volume[cid] = sum(
            (f.additions or 0) + (f.deletions or 0) for f in files_by_commit.get(cid, [])
        )
    total_volume = sum(per_commit_volume.values())

    # --- файлы ---
    files_touched = sorted(
        {f.path for cid in commit_ids for f in files_by_commit.get(cid, []) if f.path}
    )
    # files_mentioned берём из текста задачи: это исходное определение
    # в исследовании. Подставлять сюда же файлы связанных коммитов нельзя —
    # тогда обе стороны совпадут и составляющая всегда станет 1.0.
    files_mentioned = extract_files_from_body(f"{task.title}\n{task.description or ''}")

    # --- подзадачи ---
    subtasks: List[SubTask] = list(
        (
            await db.execute(select(SubTask).where(SubTask.task_id == task.id))
        ).scalars().all()
    )
    subtasks_payload = [{"text": s.title, "done": bool(s.is_completed)} for s in subtasks]

    # Чеклист из описания берём, только если подзадач нет: иначе два
    # источника описывают одно и то же, и структурная составляющая
    # была бы посчитана дважды.
    if not subtasks_payload:
        subtasks_payload = extract_checklist_items(task.description or "")

    subtasks_done = sum(1 for s in subtasks_payload if s["done"])

    # --- калибровка ---
    calibration = await resolve_expected_volume(db, task.project_id, task.id)
    expected_volume = calibration["expected_volume"]

    # --- формула ---
    result = calculate_progress_detailed(
        task={
            "files_mentioned": files_mentioned,
            "files_touched": files_touched,
            "expected_volume": expected_volume,
        },
        # Модуль ждёт тексты диффов; передаём по одной изменённой строке
        # на каждую посчитанную строку — итог совпадает с additions+deletions.
        commits_diffs=["\n".join(["+"] * n) for n in per_commit_volume.values() if n > 0],
        subtasks=subtasks_payload or None,
    )

    has_commits = bool(commit_ids)
    has_subtasks = bool(subtasks_payload)
    has_mentions = bool(files_mentioned)
    weights = _weights_for(has_subtasks, has_mentions)
    confidence, reasons = judge_confidence(
        has_commits, has_subtasks, has_mentions, calibration["source"]
    )

    # --- время ---
    timestamps_by_id = _map_timestamps(commits)
    last_commit = max(timestamps_by_id.values()) if timestamps_by_id else None
    days_since = None
    if last_commit:
        days_since = (datetime.now(timezone.utc) - last_commit).days

    # --- динамика по дням ---
    history = _build_history(per_commit_volume, timestamps_by_id, expected_volume)

    return {
        "available": True,
        "task_id": task.id,
        "percent": result["progress_percent"],
        "confidence": confidence,
        "confidence_reasons": reasons,
        "components": {
            "structural": result["structural_component"],
            "volume": result["volume_component"],
            "semantic": result["semantic_component"],
            "targeting": result["targeting_component"],
            "completion": result["completion_component"],
        },
        "weights": weights,
        "inputs": {
            "commits": len(commit_ids),
            "dropped_links": dropped,
            "additions": sum(
                f.additions or 0
                for cid in commit_ids
                for f in files_by_commit.get(cid, [])
            ),
            "deletions": sum(
                f.deletions or 0
                for cid in commit_ids
                for f in files_by_commit.get(cid, [])
            ),
            "lines_changed": total_volume,
            "expected_volume": expected_volume,
            "expected_volume_source": calibration["source"],
            "expected_volume_sample": calibration["sample"],
            "expected_volume_raw": calibration.get("expected_volume_raw"),
            "expected_volume_weight": calibration.get("expected_volume_weight", 0.0),
            "subtasks_total": len(subtasks_payload),
            "subtasks_done": subtasks_done,
            "files_touched": len(files_touched),
            "files_mentioned": len(files_mentioned),
            "files_matched": len(
                {f.split("/")[-1] for f in files_touched}
                & {f.split("/")[-1] for f in files_mentioned}
            ),
        },
        "last_commit_at": last_commit.isoformat() if last_commit else None,
        "days_since_last_commit": days_since,
        "history": history,
    }


def _map_timestamps(commits: List[Commit]) -> Dict[int, datetime]:
    out: Dict[int, datetime] = {}
    for c in commits:
        ts = _as_utc(c.timestamp)
        if ts:
            out[c.id] = ts
    return out


def _build_history(
    per_commit_volume: Dict[int, int],
    timestamps: Dict[int, datetime],
    expected_volume: int,
) -> List[Dict]:
    """Накопительный объём по дням.

    Это динамика объёмной составляющей, а не всего прогресса:
    структурную и семантическую нельзя восстановить задним числом —
    неизвестно, какие подзадачи и файлы были отмечены в тот день.
    """
    if not per_commit_volume or not timestamps or expected_volume <= 0:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.PROGRESS_HISTORY_DAYS)

    daily: Dict[str, int] = {}
    for cid, volume in per_commit_volume.items():
        ts = timestamps.get(cid)
        if ts is None or ts < cutoff or volume <= 0:
            continue
        daily[ts.date().isoformat()] = daily.get(ts.date().isoformat(), 0) + volume

    cumulative = 0
    out: List[Dict] = []
    for day in sorted(daily):
        cumulative += daily[day]
        out.append(
            {
                "date": day,
                "lines": cumulative,
                "volume_ratio": round(min(cumulative / expected_volume, 1.0), 4),
            }
        )
    return out