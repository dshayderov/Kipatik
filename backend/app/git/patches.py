"""Дозаполнение текстов изменений у коммитов.

Модели анализа кода обучались на представлении коммита, где кроме списка
файлов есть текст правок. В системе его не было: `commit_files` хранил
путь, статус и счётчики строк.

Получить правки можно только отдельным запросом на каждый коммит — списком
коммитов их не отдаёт ни один провайдер. Поэтому дозаполнение:

  * выключено по умолчанию (`GIT_FETCH_PATCHES=false`), иначе синхронизация
    проекта на сотню коммитов превратится в сотню запросов;
  * ограничено по числу коммитов за запуск;
  * делает паузу между запросами;
  * никогда не ходит за уже заполненными коммитами.

Права хранятся обрезанными: модель всё равно режет вход до 256 токенов,
а целые патчи у провайдеров бывают на сотни килобайт.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.git.factory import get_git_provider
from app.git.models import Commit, CommitFile, GitRepository

logger = logging.getLogger(__name__)


def truncate_patch(patch: Optional[str]) -> tuple:
    """Обрезает правку до GIT_MAX_PATCH_CHARS.

    Возвращает (текст, обрезан ли). Обрезка идёт по границе строки: обрыв
    посреди строки даёт модели мусор на входе.
    """
    if not patch:
        return None, False
    limit = settings.GIT_MAX_PATCH_CHARS
    if len(patch) <= limit:
        return patch, False

    cut = patch[:limit]
    newline = cut.rfind("\n")
    if newline > limit * 0.5:
        cut = cut[:newline]
    return cut, True


def count_changed_lines(patch: Optional[str]) -> tuple:
    """Сколько строк добавлено и удалено по тексту правки.

    Провайдеры неодинаковы: GitHub присылает additions/deletions, а GitLab
    в ответе на /diff отдаёт только сам diff. Без подсчёта объёмная
    составляющая прогресса была всегда нулевой — метрика упиралась в 50%
    и не двигалась независимо от размера работы.

    Строки заголовков файлов (+++ b/... и --- a/...) не считаются: они
    несут метаданные диффа, а не изменения.
    """
    if not patch:
        return 0, 0
    additions = deletions = 0
    for line in patch.split("\n"):
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions


async def repair_change_counts(db: AsyncSession, repository_id: Optional[int] = None) -> int:
    """Дозаполняет additions/deletions у файлов, где правка уже сохранена.

    Не ходит к провайдеру: текст правки лежит в базе, нужен только подсчёт.
    Так чинятся файлы, сохранённые до того, как числа строк начали считать.
    """
    stmt = select(CommitFile).where(
        CommitFile.patch.is_not(None),
        CommitFile.patch != "",
        or_(CommitFile.additions == 0, CommitFile.additions.is_(None)),
        or_(CommitFile.deletions == 0, CommitFile.deletions.is_(None)),
    )
    if repository_id is not None:
        stmt = stmt.join(Commit, Commit.id == CommitFile.commit_id).where(
            Commit.repository_id == repository_id
        )

    fixed = 0
    for f in (await db.execute(stmt)).scalars().all():
        a, d = count_changed_lines(f.patch)
        if a or d:
            f.additions = a
            f.deletions = d
            fixed += 1
    if fixed:
        await db.commit()
    return fixed


async def _commits_missing_patch(
    db: AsyncSession, repo: GitRepository, limit: int
) -> List[Commit]:
    """Коммиты репозитория, у которых ещё нет текстов изменений.

    Отбираем всё, где правок нет, — включая случай, когда строк в
    commit_files вообще не создано. Раньше здесь брались только
    коммиты, у которых файлы УЖЕ были записаны, и это создавало
    тупик: файлы заводятся тем же бэкфиллом, поэтому при первом
    запуске отбор был пуст и правки не подтягивались никогда.
    """
    filled = set(
        (
            await db.execute(
                select(CommitFile.commit_id).where(
                    CommitFile.commit_id.is_not(None),
                    CommitFile.patch.is_not(None),
                    CommitFile.patch != "",
                )
            )
        )
        .scalars()
        .all()
    )

    candidates = (
        await db.execute(
            select(Commit)
            .where(Commit.repository_id == repo.id)
            .order_by(Commit.timestamp.desc().nullslast())
        )
    ).scalars().all()

    out: List[Commit] = []
    for c in candidates:
        if c.id in filled:
            continue
        out.append(c)
        if len(out) >= limit:
            break
    return out


async def _already_filled(db: AsyncSession, commit_ids: List[int]) -> set:
    """Коммиты, у которых хотя бы один файл уже несёт правку."""
    if not commit_ids:
        return set()
    rows = (
        await db.execute(
            select(CommitFile.commit_id).where(
                CommitFile.commit_id.in_(commit_ids),
                CommitFile.patch != None,  # noqa: E711
            )
        )
    ).scalars().all()
    return set(rows)


async def backfill_commit_patches(
    db: AsyncSession,
    repo: GitRepository,
    limit: Optional[int] = None,
    delay: Optional[float] = None,
    token: Optional[str] = None,
) -> Dict:
    """Дозаполняет правки для коммитов репозитория.

    Возвращает статистику: что удалось, что не удалось и почему.
    """
    limit = settings.GIT_PATCH_BACKFILL_LIMIT if limit is None else limit
    delay = settings.GIT_PATCH_BACKFILL_DELAY if delay is None else delay

    stats = {
        "enabled": settings.GIT_FETCH_PATCHES,
        "examined": 0,
        "filled": 0,
        "skipped": 0,
        "failed": 0,
        "patches_saved": 0,
        "characters_saved": 0,
        "counts_repaired": 0,
        "errors": [],
    }

    if not repo.is_active:
        stats["errors"].append("repository_inactive")
        return stats

    # Сначала чиним уже сохранённые правки: это локальная операция,
    # провайдер не нужен. Иначе объёмная составляющая прогресса
    # оставалась бы нулевой у всех коммитов, прочитанных до этого.
    stats["counts_repaired"] = await repair_change_counts(db, repo.id)

    commits = await _commits_missing_patch(db, repo, limit)
    stats["examined"] = len(commits)
    if not commits:
        return stats

    already = await _already_filled(db, [c.id for c in commits])
    commits = [c for c in commits if c.id not in already]
    stats["skipped"] = len(already)
    if not commits:
        return stats

    if token is None:
        from app.git.token_resolver import resolve_user_token

        token = await resolve_user_token(db, repo.connected_by_id, repo.provider, repo.api_url)

    provider = get_git_provider(repo.provider, token=token, api_url=repo.api_url)

    for index, commit in enumerate(commits):
        try:
            files = await provider.get_commit_files(repo.id, commit.sha)
        except Exception as exc:  # noqa: BLE001 — один коммит не должен ронять всё
            stats["failed"] += 1
            if len(stats["errors"]) < 5:
                # Тип без сообщения бесполезен: «превышен лимит» и «репозиторий
                # не найден» требуют разных действий. Тело ответа провайдера
                # целиком сюда не пишем, чтобы не тащить его в интерфейс.
                stats["errors"].append(
                    f"{commit.sha[:7]}: {type(exc).__name__}: {str(exc)[:120]}"
                )
            logger.warning("Не удалось получить правки для %s: %s", commit.sha[:7], exc)
            continue

        if not files:
            stats["failed"] += 1
            continue

        saved = await _store_files(db, commit, files, stats)
        if saved:
            stats["filled"] += 1
        else:
            stats["failed"] += 1

        # Пауза между запросами: каждый вызов — это один лимит API
        if delay and index < len(commits) - 1:
            await asyncio.sleep(delay)

    await db.commit()
    return stats


async def _store_files(db: AsyncSession, commit: Commit, files: List, stats: Dict) -> bool:
    """Записывает файлы коммита вместе с правками.

    Существующие строки обновляются: раньше повторный вызов просто
    пропускал уже известные пути, и правка никогда бы не появилась.
    """
    existing = {
        f.path: f
        for f in (
            await db.execute(
                select(CommitFile).where(CommitFile.commit_id == commit.id)
            )
        ).scalars().all()
    }

    touched = False
    for dto in files:
        path = getattr(dto, "path", None) or (dto.get("path") if isinstance(dto, dict) else None)
        if not path:
            continue

        raw = getattr(dto, "patch", None) if not isinstance(dto, dict) else dto.get("patch")
        provider_truncated = (
            getattr(dto, "patch_truncated", False)
            if not isinstance(dto, dict)
            else dto.get("patch_truncated", False)
        )
        text, was_cut = truncate_patch(raw)

        current = existing.get(path)
        if current is not None:
            # Правку обновляем, только если её ещё не было: повторный
            # дозаполнительный заход не должен затирать уже сохранённую
            if current.patch is None and text is not None:
                current.patch = text
                current.patch_truncated = was_cut or provider_truncated
                stats["patches_saved"] += 1
                stats["characters_saved"] += len(text)
                touched = True

            # Правка могла сохраниться раньше, когда числа строк ещё
            # никто не считал. Дозаполняем, если провайдер их не дал.
            if text is not None and not current.additions and not current.deletions:
                a, d = count_changed_lines(text)
                if a or d:
                    current.additions = a
                    current.deletions = d
                    touched = True
            continue

        additions = getattr(dto, "additions", 0) or 0
        deletions = getattr(dto, "deletions", 0) or 0
        # Провайдер не прислал числа — считаем их по самой правке,
        # иначе объёмная составляющая прогресса остаётся нулевой.
        if not additions and not deletions:
            additions, deletions = count_changed_lines(text)
        db.add(
            CommitFile(
                commit_id=commit.id,
                path=path,
                previous_path=getattr(dto, "previous_path", None),
                status=getattr(dto, "status", "modified") or "modified",
                additions=additions,
                deletions=deletions,
                patch=text,
                patch_truncated=bool(was_cut or provider_truncated),
            )
        )
        if text:
            stats["patches_saved"] += 1
            stats["characters_saved"] += len(text)
        touched = True

    if touched:
        await db.flush()
    return touched


async def ensure_commit_patch(db: AsyncSession, commit: Commit, token: Optional[str] = None) -> bool:
    """Догружает правки одного коммита, если их ещё нет.

    Используется перед анализом коммита моделью: платить за запрос к API
    имеет смысл только тогда, когда модель действительно понадобилась.
    """
    existing = (
        await db.execute(
            select(CommitFile).where(
                CommitFile.commit_id == commit.id,
                CommitFile.patch != None,  # noqa: E711
            )
        )
    ).scalars().all()
    if existing:
        return True

    repo = (
        await db.execute(
            select(GitRepository).where(GitRepository.id == commit.repository_id)
        )
    ).scalar_one_or_none()
    if not repo:
        return False

    if token is None:
        from app.git.token_resolver import resolve_user_token

        token = await resolve_user_token(db, repo.connected_by_id, repo.provider, repo.api_url)

    provider = get_git_provider(repo.provider, token=token, api_url=repo.api_url)
    try:
        files = await provider.get_commit_files(repo.id, commit.sha)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Не удалось догрузить правки %s: %s", commit.sha[:7], exc)
        return False

    if not files:
        return False

    stats: Dict = {"patches_saved": 0, "characters_saved": 0}
    await _store_files(db, commit, files, stats)
    await db.commit()
    return True


def build_commit_diff(files: List[CommitFile]) -> str:
    """Собирает текст изменений в формате, который ждёт модель.

    Разделитель `File:` — часть формата обучения; extract_files_from_diff
    в модели на него опирается.
    """
    parts: List[str] = []
    for f in files:
        if not f.patch:
            continue
        parts.append(f"File: {f.path}\n{f.patch}")
    return "\n".join(parts)


def has_patches(files: List[CommitFile]) -> bool:
    return any(f.patch for f in files)