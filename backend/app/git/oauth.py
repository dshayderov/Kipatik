"""OAuth-авторизация у провайдеров Git.

Personal Access Token остаётся рабочим, но OAuth даёт три вещи, которых у PAT нет:
  * права выдаются конкретному пользователю и только на время его работы;
  * токен можно отозвать на стороне провайдера без смены секретов у нас;
  * для self-hosted GitLab (важно для российских команд) не нужно раздавать
    токены с широкими правами каждому разработчику.

Защита от подделки: state — подписанный JWT (HMAC-SECRET_KEY) с user_id,
провайдером и сроком жизни. Провайдер возвращает его как есть, поэтому
только наш сервер может его выпустить и только он может его проверить.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

import httpx
from jose import JWTError, jwt

from app.core.config import settings
from app.git.models import GitProviderType

logger = logging.getLogger(__name__)

# Права: минимум, которого хватает для привязки и чтения
DEFAULT_SCOPES = {
    "github": "repo:read repo:status read:user",
    "gitlab": "api read_user",
    "gitea": "repo read:user",
    "bitbucket": "repository:read account:read",
}


class OAuthError(Exception):
    """Ошибка OAuth-обмена (неверный код, отказ пользователя и т.п.)."""


class OAuthNotConfigured(Exception):
    """OAuth-приложение для провайдера не зарегистрировано."""


def _host_for(provider: str, server_url: str | None) -> str:
    """Адрес инстанса провайдера с учётом self-hosted."""
    if provider == "gitlab":
        return (server_url or settings.GITLAB_HOST or "https://gitlab.com").rstrip("/")
    if provider == "gitea":
        return (server_url or settings.GITEA_HOST or "https://gitea.com").rstrip("/")
    if provider == "github":
        return server_url or "https://github.com"
    if provider == "bitbucket":
        return server_url or "https://bitbucket.org"
    return server_url or ""


def get_credentials(provider: str, server_url: str | None = None) -> Tuple[str, str]:
    """Возвращает (client_id, client_secret) провайдера."""
    key = (provider or "").lower()
    if key == "github":
        cid, secret = settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET
    elif key == "gitlab":
        cid, secret = settings.GITLAB_CLIENT_ID, settings.GITLAB_CLIENT_SECRET
    elif key == "gitea":
        cid, secret = settings.GITEA_CLIENT_ID, settings.GITEA_CLIENT_SECRET
    elif key == "bitbucket":
        cid, secret = settings.BITBUCKET_CLIENT_ID, settings.BITBUCKET_CLIENT_SECRET
    else:
        raise OAuthError(f"Unknown provider: {provider}")

    if not cid or not secret:
        raise OAuthNotConfigured(provider)
    return cid, secret


def is_oauth_available(provider: str) -> bool:
    try:
        get_credentials(provider)
        return True
    except (OAuthNotConfigured, OAuthError):
        return False


# --------------------------------------------------------------------- #
# state
# --------------------------------------------------------------------- #
def build_state(user_id: int, provider: str, server_url: str | None = None) -> str:
    payload = {
        "uid": user_id,
        "prov": provider,
        "srv": server_url,
        "exp": datetime.now(timezone.utc)
        + timedelta(seconds=settings.OAUTH_STATE_TTL_SECONDS),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def read_state(state: str) -> Dict:
    try:
        return jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise OAuthError("Некорректное или просроченное состояние авторизации") from exc


# --------------------------------------------------------------------- #
# адреса провайдеров
# --------------------------------------------------------------------- #
def callback_url(provider: str) -> str:
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    return f"{base}{settings.API_V1_STR}/auth/oauth/{provider}/callback"


def authorize_url(
    provider: str,
    user_id: int,
    server_url: str | None = None,
) -> str:
    """Строит URL, на который нужно увести пользователя для выдачи прав."""
    key = (provider or "").lower()
    client_id, _ = get_credentials(key, server_url)
    state = build_state(user_id, key, server_url)
    redirect = callback_url(key)
    scopes = DEFAULT_SCOPES.get(key, "")

    if key == "github":
        return (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={client_id}&redirect_uri={redirect}&state={state}"
            f"&scope={scopes.replace(' ', ',')}"
        )

    if key == "gitlab":
        host = _host_for(key, server_url)
        return (
            f"{host}/oauth/authorize"
            f"?client_id={client_id}&redirect_uri={redirect}&state={state}"
            f"&response_type=code&scope={scopes}"
        )

    if key == "gitea":
        host = _host_for(key, server_url)
        return (
            f"{host}/login/oauth/authorize"
            f"?client_id={client_id}&redirect_uri={redirect}&state={state}"
            f"&response_type=code&scope={scopes}"
        )

    if key == "bitbucket":
        return (
            f"https://bitbucket.org/site/oauth2/authorize"
            f"?client_id={client_id}&redirect_uri={redirect}&state={state}"
            f"&response_type=code&scope={scopes.replace(' ', '+')}"
        )

    raise OAuthError(f"Unknown provider: {provider}")


# --------------------------------------------------------------------- #
# обмен кода на токен
# --------------------------------------------------------------------- #
async def exchange_code(
    provider: str,
    code: str,
    server_url: str | None = None,
) -> Dict:
    """Меняет код на токен и возвращает данные аккаунта."""
    key = (provider or "").lower()
    client_id, client_secret = get_credentials(key, server_url)
    redirect = callback_url(key)
    host = _host_for(key, server_url)

    data: Dict = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect,
    }
    headers = {"Accept": "application/json"}

    if key == "github":
        token_url = "https://github.com/login/oauth/access_token"
    elif key == "gitlab":
        token_url = f"{host}/oauth/token"
    elif key == "gitea":
        token_url = f"{host}/login/oauth/access_token"
    elif key == "bitbucket":
        token_url = "https://bitbucket.org/site/oauth2/access_token"
        data = {"grant_type": "authorization_code", **data}
    else:
        raise OAuthError(f"Unknown provider: {provider}")

    try:
        async with httpx.AsyncClient(timeout=settings.GIT_HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.post(token_url, data=data, headers=headers)
    except httpx.HTTPError as exc:
        raise OAuthError(f"Провайдер недоступен: {exc}") from exc

    if resp.status_code >= 400:
        raise OAuthError(f"Провайдер отклонил обмен кода ({resp.status_code}): {resp.text[:200]}")

    try:
        payload = resp.json()
    except Exception as exc:
        raise OAuthError("Провайдер вернул не-JSON ответ") from exc

    if payload.get("error"):
        raise OAuthError(str(payload.get("error_description") or payload["error"]))

    access_token = payload.get("access_token")
    if not access_token:
        raise OAuthError("В ответе провайдера нет access_token")

    expires_in = payload.get("expires_in")
    expires_at = None
    if expires_in:
        # GitHub возвращает 0 (токен бессрочный) — тогда срок не храним
        if int(expires_in) > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    profile = await fetch_profile(key, access_token, host)

    return {
        "access_token": access_token,
        "refresh_token": payload.get("refresh_token"),
        "expires_at": expires_at,
        "username": profile.get("username"),
        "provider_user_id": profile.get("id"),
        "avatar_url": profile.get("avatar_url"),
    }


async def fetch_profile(provider: str, access_token: str, host: str) -> Dict:
    """Читает профиль пользователя, чтобы показать, кто подключён."""
    try:
        async with httpx.AsyncClient(timeout=settings.GIT_HTTP_TIMEOUT_SECONDS) as client:
            if provider == "github":
                r = await client.get(
                    "https://api.github.com/user",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                d = r.json()
                return {"id": str(d.get("id")), "username": d.get("login"), "avatar_url": d.get("avatar_url")}

            if provider == "gitlab":
                r = await client.get(
                    f"{host}/api/v4/user",
                    headers={"PRIVATE-TOKEN": access_token},
                )
                d = r.json()
                return {"id": str(d.get("id")), "username": d.get("username"), "avatar_url": d.get("avatar_url")}

            if provider == "gitea":
                r = await client.get(
                    f"{host}/api/v1/user",
                    headers={"Authorization": f"token {access_token}"},
                )
                d = r.json()
                return {"id": str(d.get("id")), "username": d.get("login"), "avatar_url": d.get("avatar_url")}

            if provider == "bitbucket":
                r = await client.get(
                    "https://api.bitbucket.org/2.0/user",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                d = r.json()
                return {"id": d.get("uuid") or d.get("username"), "username": d.get("username")}
    except Exception as exc:  # профиль не обязателен для успеха авторизации
        logger.warning("Не удалось получить профиль %s: %s", provider, exc)
    return {"id": None, "username": None}


async def refresh_access_token(
    provider: str,
    refresh_token: str,
    server_url: str | None = None,
) -> Optional[Dict]:
    """Обновляет истёкший токен (GitLab и Gitea выдают их на 2 часа)."""
    key = (provider or "").lower()
    client_id, client_secret = get_credentials(key, server_url)
    host = _host_for(key, server_url)

    if key == "gitlab":
        token_url = f"{host}/oauth/token"
    elif key == "gitea":
        token_url = f"{host}/login/oauth/access_token"
    else:
        # GitHub и Bitbucket по умолчанию выдают бессрочные токены
        return None

    try:
        async with httpx.AsyncClient(timeout=settings.GIT_HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                token_url,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={"Accept": "application/json"},
            )
        if resp.status_code >= 400:
            logger.warning("Не удалось обновить токен %s: %s", key, resp.text[:200])
            return None

        payload = resp.json()
        access_token = payload.get("access_token")
        if not access_token:
            return None

        expires_in = payload.get("expires_in")
        expires_at = None
        if expires_in and int(expires_in) > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

        return {
            "access_token": access_token,
            "refresh_token": payload.get("refresh_token") or refresh_token,
            "expires_at": expires_at,
        }
    except Exception as exc:
        logger.warning("Ошибка обновления токена %s: %s", key, exc)
        return None


def provider_from_type(provider_type: GitProviderType) -> str:
    """GitProviderType.GITLAB_CUSTOM -> 'gitlab' с сохранением server_url."""
    value = getattr(provider_type, "value", provider_type)
    return "gitlab" if value == "gitlab_custom" else str(value)
