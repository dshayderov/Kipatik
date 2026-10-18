from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.api import deps
from app.core import security
from app.core.config import settings
from app.core.database import get_db
from app.models import User
from app.schemas.auth import Token
from app.schemas.user import User as UserSchema, UserCreate

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/login", response_model=Token)
async def login(
    db: AsyncSession = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalars().first()
    
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    elif not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return {
        "access_token": security.create_access_token(
            user.id, expires_delta=access_token_expires
        ),
        "token_type": "bearer",
    }

@router.post("/register", response_model=UserSchema)
async def register(
    *,
    db: AsyncSession = Depends(get_db),
    user_in: UserCreate
) -> Any:
    """
    Create new user.
    """
# Связь git_accounts есть в схеме ответа. Без предзагрузки Pydantic
# обращается к ней уже после выхода из async-контекста и получает
# MissingGreenlet — ответ падал с 500, хотя пользователь был создан.
    result = await db.execute(
        select(User)
            .where(User.email == user_in.email)
            .options(selectinload(User.git_accounts))
    )
    user = result.scalars().first()
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )
    
    db_obj = User(
        email=user_in.email,
        hashed_password=security.get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role=user_in.role,
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)

    # Перечитываем объект с предзагруженной связью: у только что
    # созданного пользователя git_accounts ещё не загружены, и Pydantic
    # обратится к ним уже после выхода из async-контекста и получит
    # MissingGreenlet. db.refresh() связи не подтягивает.
    result = await db.execute(
        select(User)
        .where(User.id == db_obj.id)
        .options(selectinload(User.git_accounts))
    )
    return result.scalar_one()


# --------------------------------------------------------------------- #
# OAuth провайдеров Git
# --------------------------------------------------------------------- #
class OAuthProviderInfo(BaseModel):
    provider: str
    available: bool          # OAuth-приложение зарегистрировано?
    connected: bool          # есть ли у пользователя токен
    username: Optional[str] = None
    server_url: Optional[str] = None
    expires_at: Optional[datetime] = None


class OAuthStartResponse(BaseModel):
    url: str
    provider: str


@router.get("/oauth/providers", response_model=List[OAuthProviderInfo])
async def list_oauth_providers(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Что доступно для подключения по каждому провайдеру.

    Фронтенд по этому ответу решает: показывать кнопку OAuth,
    предлагать вставить PAT вручную или ничего не предлагать.
    """
    from app.git.models import GitAccount, GitProviderType
    from app.git.oauth import is_oauth_available

    accounts = (
        await db.execute(select(GitAccount).filter(GitAccount.user_id == current_user.id))
    ).scalars().all()
    by_provider = {a.provider.value: a for a in accounts}

    result: List[OAuthProviderInfo] = []
    for provider in ("github", "gitlab", "gitea", "bitbucket"):
        account = by_provider.get(provider)
        result.append(
            OAuthProviderInfo(
                provider=provider,
                available=is_oauth_available(provider),
                connected=account is not None,
                username=account.username if account else None,
                server_url=account.server_url if account else None,
                expires_at=account.token_expires_at if account else None,
            )
        )
    return result


@router.get("/oauth/{provider}/start", response_model=OAuthStartResponse)
async def oauth_start(
    provider: str,
    server_url: Optional[str] = None,
    current_user: User = Depends(deps.get_current_user),
):
    """Возвращает URL для перехода к согласию провайдера."""
    from app.git.oauth import (
        OAuthError, OAuthNotConfigured, authorize_url,
    )

    try:
        url = authorize_url(provider, current_user.id, server_url)
    except OAuthNotConfigured:
        raise HTTPException(
            status_code=503,
            detail=(
                f"OAuth для {provider} не настроен на сервере. "
                "Используйте Personal Access Token."
            ),
        )
    except OAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return OAuthStartResponse(url=url, provider=provider)


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: AsyncSession = Depends(deps.get_db),
):
    """Точка возврата от провайдера.

    Пользователь здесь ещё не аутентифицирован в API (он пришёл от
    внешнего сайта), поэтому личность восстанавливается из подписанного state.
    """
    from urllib.parse import urlencode
    from app.core.config import settings
    from app.git.models import GitAccount, GitProviderType
    from app.git.oauth import OAuthError, exchange_code, read_state

    redirect_base = settings.OAUTH_FRONTEND_REDIRECT.rstrip("/")

    def _redirect(params: Dict[str, str]) -> RedirectResponse:
        return RedirectResponse(
            url=f"{redirect_base}?{urlencode(params)}", status_code=302
        )

    if error:
        logger.info("Провайдер %s отклонил авторизацию: %s", provider, error)
        return _redirect({"oauth": provider, "oauth_error": "access_denied"})

    if not code or not state:
        return _redirect({"oauth": provider, "oauth_error": "missing_code"})

    try:
        payload = read_state(state)
    except OAuthError as exc:
        logger.warning("OAuth %s: некорректный state: %s", provider, exc)
        return _redirect({"oauth": provider, "oauth_error": "invalid_state"})

    # Провайдер в state должен совпадать с тем, к кому мы обращались
    if payload.get("prov") != provider.lower():
        return _redirect({"oauth": provider, "oauth_error": "provider_mismatch"})

    user_id = int(payload["uid"])
    server_url = payload.get("srv")

    try:
        result = await exchange_code(provider, code, server_url)
    except OAuthError as exc:
        logger.warning("OAuth %s: обмен кода не удался: %s", provider, exc)
        return _redirect({"oauth": provider, "oauth_error": "exchange_failed"})

    # Сохраняем/обновляем GitAccount
    prov_type = {
        "github": GitProviderType.GITHUB,
        "gitlab": GitProviderType.GITLAB,
        "gitea": GitProviderType.GITEA,
        "bitbucket": GitProviderType.BITBUCKET,
    }.get(provider.lower(), GitProviderType.GITHUB)

    existing = (
        await db.execute(
            select(GitAccount).filter(
                GitAccount.user_id == user_id,
                GitAccount.provider == prov_type,
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.access_token = result["access_token"]
        existing.refresh_token = result.get("refresh_token")
        existing.token_expires_at = result.get("expires_at")
        existing.username = result.get("username")
        existing.provider_user_id = result.get("provider_user_id")
    else:
        db.add(
            GitAccount(
                user_id=user_id,
                provider=prov_type,
                server_url=server_url,
                access_token=result["access_token"],
                refresh_token=result.get("refresh_token"),
                token_expires_at=result.get("expires_at"),
                username=result.get("username"),
                provider_user_id=result.get("provider_user_id"),
            )
        )

    await db.commit()
    logger.info("OAuth %s подключён для пользователя %s", provider, user_id)

    return _redirect(
        {
            "oauth": provider,
            "oauth_ok": "1",
            "username": result.get("username") or "",
        }
    )


@router.delete("/oauth/{provider}")
async def oauth_disconnect(
    provider: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """Отключить провайдера: удаляем OAuth-токен."""
    from app.git.models import GitAccount, GitProviderType

    prov_type = {
        "github": GitProviderType.GITHUB,
        "gitlab": GitProviderType.GITLAB,
        "gitea": GitProviderType.GITEA,
        "bitbucket": GitProviderType.BITBUCKET,
    }.get(provider.lower())

    if prov_type is None:
        raise HTTPException(status_code=400, detail="Unknown provider")

    account = (
        await db.execute(
            select(GitAccount).filter(
                GitAccount.user_id == current_user.id,
                GitAccount.provider == prov_type,
            )
        )
    ).scalar_one_or_none()

    if account:
        await db.delete(account)
        await db.commit()

    return {"status": "success"}
