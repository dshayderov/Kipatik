"""Сопоставление Git-авторов с пользователями системы.

Здесь ломается большинство Git-интеграций: у разработчика личный почтовый
адрес в коммитах, другой логин на self-hosted GitLab, анонимные коммиты или
удалённый аккаунт. Поэтому сопоставление решено как явный процесс:

  1. нормализация строки автора в устойчивый ключ;
  2. цепочка автосопоставления (ручное правило -> email -> логин провайдера);
  3. экран, где видно всех неопознанных авторов и можно сопоставить вручную;
  4. переатрибуция уже сохранённых коммитов после ручного правила.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.git.models import Commit, GitAuthorMapping, GitRepository

logger = logging.getLogger(__name__)

# "Name <mail@host>" -> ("Name", "mail@host")
_NAME_MAIL_RE = re.compile(r"^\s*(?P<name>.*?)\s*<(?P<mail>[^>]+)>\s*$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# «Пустые» значения, которые провайдеры подставляют вместо автора
_PLACEHOLDER_AUTHORS = {"", "unknown", "none", "null", "n/a"}


def normalize_author(
    author_raw: Optional[str], email: Optional[str] = None
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Разбирает автора в (author_key, author_name, author_email).

    author_key — стабильный ключ для сопоставления: email в нижнем регистре,
    иначе нормализованное имя/логин.
    """
    name = (author_raw or "").strip()
    if name in _PLACEHOLDER_AUTHORS:
        name = ""
    mail = (email or "").strip()

    m = _NAME_MAIL_RE.match(name)
    if m:
        name = (m.group("name") or "").strip().strip('"')
        mail = m.group("mail").strip()

    if not _EMAIL_RE.match(mail):
        mail = None

    # Ключ: почта предпочтительнее — она устойчивее к переименованию логина
    if mail:
        key = mail.lower()
    elif name:
        key = name.lower()
    else:
        return None, None, None

    return key, (name or None), (mail.lower() if mail else None)


class AuthorMappingService:
    """Сопоставление и переатрибуция авторов коммитов."""

    # ------------------------------------------------------------------ #
    # Цепочка автосопоставления
    # ------------------------------------------------------------------ #
    @staticmethod
    async def resolve(
        db: AsyncSession,
        repository_id: Optional[int],
        author_raw: Optional[str],
        author_email: Optional[str] = None,
    ) -> Tuple[Optional[int], str]:
        """Возвращает (user_id, способ). user_id=None — автор не опознан.

        Порядок:
          1) явное правило (ручное или автосохранённое) — главный приоритет,
             оно должно перебивать догадки;
          2) почта -> users.email;
          3) логин -> user_git_accounts.username.
        """
        key, name, mail = normalize_author(author_raw, author_email)
        if not key:
            return None, "empty"

        # 1) Явное правило: сначала для репозитория, затем глобальное
        rules = await db.execute(
            select(GitAuthorMapping).where(
                GitAuthorMapping.author_key == key,
                (GitAuthorMapping.repository_id == repository_id)
                | (GitAuthorMapping.repository_id.is_(None)),
            )
        )
        # Приоритет у правила конкретного репозитория
        found = rules.scalars().all()
        scoped = [r for r in found if r.repository_id == repository_id]
        chosen = (scoped or found)
        if chosen:
            return chosen[0].user_id, chosen[0].source or "manual"

        from app.models import User
        from app.git.models import GitAccount

        # 2) Почта
        if mail:
            res = await db.execute(
                select(User).filter(func.lower(User.email) == mail)
            )
            user = res.scalars().first()
            if user:
                return user.id, "auto_email"

        # 3) Логин провайдера
        if name:
            res = await db.execute(
                select(GitAccount).filter(func.lower(GitAccount.username) == name.lower())
            )
            account = res.scalars().first()
            if account:
                return account.user_id, "auto_username"

        return None, "unmatched"

    # ------------------------------------------------------------------ #
    # Анализ: кто не опознан
    # ------------------------------------------------------------------ #
    @staticmethod
    async def analyze(db: AsyncSession, repository_id: int) -> Dict:
        """Собирает статистику по авторам репозитория.

        Возвращает список авторов с числом коммитов, признаком распознавания
        и (для распознанных) именем пользователя системы.
        """
        from app.models import User

        # Собираем сырые авторы напрямую из коммитов
        rows = (
            await db.execute(
                select(
                    Commit.author,
                    Commit.author_email,
                    Commit.author_id,
                    func.count(Commit.id).label("commits"),
                    func.min(Commit.timestamp).label("first_seen"),
                    func.max(Commit.timestamp).label("last_seen"),
                )
                .where(Commit.repository_id == repository_id)
                .group_by(Commit.author, Commit.author_email, Commit.author_id)
                .order_by(func.count(Commit.id).desc())
            )
        ).all()

        authors: List[Dict] = []
        total_commits = 0
        matched_commits = 0

        for row in rows:
            total_commits += row.commits or 0
            key, name, mail = normalize_author(row.author, row.author_email)
            if not key:
                continue

            entry = {
                "author_key": key,
                "author_name": row.author,
                "author_email": row.author_email,
                "commits": row.commits or 0,
                "first_seen": row.first_seen,
                "last_seen": row.last_seen,
                "user_id": row.author_id,
                "user_name": None,
                "source": None,
            }

            if row.author_id:
                user = (
                    await db.execute(select(User).filter(User.id == row.author_id))
                ).scalars().first()
                entry["user_name"] = (user.full_name or user.email) if user else None
                entry["source"] = "stored"
                matched_commits += row.commits or 0
            else:
                # Пробуем определить автоматически (без записи)
                user_id, source = await AuthorMappingService.resolve(
                    db, repository_id, row.author, row.author_email
                )
                entry["source"] = source
                if user_id:
                    user = (
                        await db.execute(select(User).filter(User.id == user_id))
                    ).scalars().first()
                    entry["user_name"] = (user.full_name or user.email) if user else None
                    # Автоматика, но ещё не применена к коммитам
                    matched_commits += 0
                else:
                    entry["suggested"] = None

            authors.append(entry)

        unmatched = [a for a in authors if not a["user_id"] and a["source"] == "unmatched"]
        auto_matched = [a for a in authors if not a["user_id"] and a["source"].startswith("auto_")]

        return {
            "repository_id": repository_id,
            "authors": authors,
            "stats": {
                "total_commits": total_commits,
                "attributed_commits": matched_commits,
                "distinct_authors": len(authors),
                "unmatched_authors": len(unmatched),
                "auto_matched_authors": len(auto_matched),
            },
        }

    # ------------------------------------------------------------------ #
    # Ручное сопоставление
    # ------------------------------------------------------------------ #
    @staticmethod
    async def set_mapping(
        db: AsyncSession,
        repository_id: Optional[int],
        author_key: str,
        user_id: int,
        source: str = "manual",
        apply_to_existing: bool = True,
    ) -> Dict:
        """Сохраняет правило и (по умолчанию) переатрибутирует коммиты."""
        from app.models import User

        author_key = (author_key or "").strip().lower()
        if not author_key:
            raise ValueError("author_key is required")

        user = (
            await db.execute(select(User).filter(User.id == user_id))
        ).scalars().first()
        if not user:
            raise ValueError("User not found")

        existing = (
            await db.execute(
                select(GitAuthorMapping).where(
                    GitAuthorMapping.author_key == author_key,
                    GitAuthorMapping.repository_id == repository_id
                    if repository_id is not None
                    else GitAuthorMapping.repository_id.is_(None),
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.user_id = user_id
            existing.source = source
        else:
            db.add(
                GitAuthorMapping(
                    repository_id=repository_id,
                    author_key=author_key,
                    author_name=user.full_name or user.email,
                    author_email=author_key if "@" in author_key else None,
                    user_id=user_id,
                    source=source,
                )
            )
        await db.commit()

        updated = 0
        if apply_to_existing and repository_id is not None:
            updated = await AuthorMappingService.backfill(db, repository_id, author_key, user_id)

        return {"status": "ok", "updated_commits": updated, "author_key": author_key}

    @staticmethod
    async def backfill(
        db: AsyncSession,
        repository_id: int,
        author_key: str,
        user_id: int,
    ) -> int:
        """Проставляет author_id ранее сохранённым коммитам этого автора."""
        res = await db.execute(
            select(Commit).where(
                Commit.repository_id == repository_id,
                Commit.author_id.is_(None),
            )
        )
        commits = res.scalars().all()

        updated = 0
        for c in commits:
            key, _, _ = normalize_author(c.author, c.author_email)
            if key == author_key:
                c.author_id = user_id
                updated += 1

        if updated:
            await db.commit()
        return updated

    @staticmethod
    async def rematch_all(db: AsyncSession, repository_id: int) -> Dict:
        """Полная переатрибуция: прогоняет все коммиты через текущие правила."""
        res = await db.execute(
            select(Commit).where(
                Commit.repository_id == repository_id,
                Commit.author_id.is_(None),
            )
        )
        commits = res.scalars().all()

        updated = 0
        for c in commits:
            user_id, _ = await AuthorMappingService.resolve(
                db, repository_id, c.author, c.author_email
            )
            if user_id:
                c.author_id = user_id
                updated += 1

        if updated:
            await db.commit()
        return {"status": "ok", "updated_commits": updated, "scanned_commits": len(commits)}

    @staticmethod
    async def delete_mapping(db: AsyncSession, mapping_id: int) -> None:
        mapping = (
            await db.execute(
                select(GitAuthorMapping).filter(GitAuthorMapping.id == mapping_id)
            )
        ).scalar_one_or_none()
        if mapping:
            await db.delete(mapping)
            await db.commit()
