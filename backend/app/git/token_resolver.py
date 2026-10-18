"""Получение токена провайдера для пользователя.

Приоритет:
  1) OAuth-токен из user_git_accounts (с автоматическим обновлением
     истёкшего — GitLab и Gitea выдают их на пару часов);
  2) Personal Access Token из старых колонок users.*_token.

Старые PAT продолжают работать: OAuth — улучшение, а не требование.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.git.models import GitAccount, GitProviderType

logger = logging.getLogger(__name__)

# Обновляем токен заранее, чтобы он не истёк в середине запроса
REFRESH_MARGIN = timedelta(minutes=5)


async def resolve_user_token(
    db: AsyncSession,
    user_id: int,
    provider_type: GitProviderType,
    server_url: str | None = None,
) -> Optional[str]:
    """Возвращает рабочий токен провайдера для пользователя.

    Для self-hosted учитывается server_url: у self-hosted GitLab свой
    OAuth-приложение и свой аккаунт.
    """
    # --- 1. OAuth ---
    query = select(GitAccount).filter(
        GitAccount.user_id == user_id,
        GitAccount.provider == provider_type,
    )
    accounts = (await db.execute(query)).scalars().all()

    account = None
    if server_url:
        # Сначала аккаунт именно этого инстанса
        for a in accounts:
            if a.server_url and a.server_url.rstrip("/") == server_url.rstrip("/"):
                account = a
                break
    if account is None:
        # Затем глобальный, затем первый попавшийся
        for a in accounts:
            if not a.server_url:
                account = a
                break
        if account is None and accounts:
            account = accounts[0]

    if account is not None:
        if _is_expired(account) and account.refresh_token:
            refreshed = await _refresh(db, account)
            if refreshed:
                return refreshed
            # Обновиться не вышло — токен всё равно попробуем использовать
        if account.access_token:
            return account.access_token

    # --- 2. Личный токен (legacy PAT) ---
    from app.users.models import User

    user = (await db.execute(select(User).filter(User.id == user_id))).scalar_one_or_none()
    if not user:
        return None

    if provider_type == GitProviderType.GITHUB:
        return user.github_token
    if provider_type in (GitProviderType.GITLAB, GitProviderType.GITLAB_CUSTOM):
        return user.gitlab_token
    if provider_type == GitProviderType.BITBUCKET:
        return user.bitbucket_token
    if provider_type == GitProviderType.GITEA:
        return user.gitea_token
    return None


def _is_expired(account: GitAccount) -> bool:
    if not account.token_expires_at:
        return False
    expires = account.token_expires_at
    # SQLite отдаёт naive datetime, приводим к UTC
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires <= datetime.now(timezone.utc) + REFRESH_MARGIN


async def _refresh(db: AsyncSession, account: GitAccount) -> Optional[str]:
    from app.git.oauth import OAuthError, OAuthNotConfigured, refresh_access_token

    provider = getattr(account.provider, "value", account.provider)
    try:
        result = await refresh_access_token(
            provider, account.refresh_token, account.server_url
        )
    except (OAuthError, OAuthNotConfigured) as exc:
        logger.warning("Не удалось обновить токен %s: %s", provider, exc)
        return None

    if not result:
        return None

    account.access_token = result["access_token"]
    account.refresh_token = result.get("refresh_token") or account.refresh_token
    account.token_expires_at = result.get("expires_at")
    await db.commit()
    logger.info("Токен %s обновлён для пользователя %s", provider, account.user_id)
    return result["access_token"]
