from typing import Any, List
import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api import deps
from app.users.models import User
from app.schemas.user import User as UserSchema, UserUpdate
from app.core.security import get_password_hash

from app.git.models import GitAccount, GitProviderType
from sqlalchemy.orm import selectinload

router = APIRouter()

# Аватар хранится рядом с остальными файлами и раздаётся через /uploads.
# 5 МБ — с запасом для фотографии с телефона.
AVATAR_MAX_BYTES = 5 * 1024 * 1024
AVATAR_DIR = os.path.join("uploads", "avatars")

# По расширению не судим: файл с именем avatar.png может оказаться чем угодно,
# а аватар показывается через <img> во всех интерфейсах. Смотрим сигнатуру.
AVATAR_SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": ".png",
    b"\xff\xd8\xff": ".jpg",
    b"GIF87a": ".gif",
    b"GIF89a": ".gif",
}


def _avatar_dir() -> str:
    os.makedirs(AVATAR_DIR, exist_ok=True)
    return AVATAR_DIR


def _avatar_path(user_id: int, ext: str) -> str:
    return os.path.join(AVATAR_DIR, f"user_{user_id}{ext}")


def _delete_stored_avatar(user_id: int) -> None:
    """Убирает прежний файл аватара, чтобы они не копились в uploads."""
    try:
        for name in os.listdir(AVATAR_DIR):
            if name.startswith(f"user_{user_id}."):
                os.remove(os.path.join(AVATAR_DIR, name))
    except FileNotFoundError:
        pass


def _avatar_url(user_id: int, ext: str) -> str:
    """Публичный адрес аватара с меткой времени.

    Метка нужна, потому что имя файла не меняется при замене фотографии:
    без неё браузер покажет картинку из кэша.
    """
    file_name = f"user_{user_id}{ext}"
    path = os.path.join(AVATAR_DIR, file_name)
    try:
        stamp = int(os.path.getmtime(path))
    except OSError:
        stamp = 0
    return f"/uploads/avatars/{file_name}" + (f"?v={stamp}" if stamp else "")


@router.post("/me/avatar")
async def upload_avatar(
    *,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Загрузка аватара. Возвращает публичный адрес файла."""
    data = await file.read()

    if not data:
        raise HTTPException(status_code=400, detail="Файл пуст")

    if len(data) > AVATAR_MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail="Файл больше 5 МБ. Выберите изображение поменьше.",
        )

    ext = None
    for signature, sig_ext in AVATAR_SIGNATURES.items():
        if data.startswith(signature):
            ext = sig_ext
            break
    else:
        # WebP начинается с RIFF, а тип хранится в байтах 8..12
        if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            ext = ".webp"

    if ext is None:
        raise HTTPException(
            status_code=400,
            detail="Поддерживаются только PNG, JPEG, GIF и WebP",
        )

    _avatar_dir()
    _delete_stored_avatar(current_user.id)
    with open(_avatar_path(current_user.id, ext), "wb") as buffer:
        buffer.write(data)

    current_user.avatar_url = _avatar_url(current_user.id, ext)
    db.add(current_user)
    await db.commit()

    return {"url": current_user.avatar_url, "size": len(data)}


@router.delete("/me/avatar")
async def delete_avatar(
    *,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Удалить загруженный аватар и снять ссылку с профиля."""
    _delete_stored_avatar(current_user.id)

    # Ссылка могла прийти со стороны GitLab/GitHub — тогда файл не наш,
    # просто очищаем поле, чтобы в шапке не осталось битой картинки
    if current_user.avatar_url and "/uploads/avatars/" in current_user.avatar_url:
        current_user.avatar_url = None
        db.add(current_user)
        await db.commit()

    return {"status": "success"}

@router.get("/me", response_model=UserSchema)
async def read_user_me(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get current user.
    """
    # Load git accounts
    result = await db.execute(
        select(User)
        .where(User.id == current_user.id)
        .options(selectinload(User.git_accounts))
    )
    return result.scalar_one()

@router.patch("/me", response_model=UserSchema)
async def update_user_me(
    *,
    db: AsyncSession = Depends(deps.get_db),
    user_in: UserUpdate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Update current user.
    """
    if user_in.email:
        # Check if email is already taken
        query = select(User).where(User.email == user_in.email, User.id != current_user.id)
        result = await db.execute(query)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail="The user with this email already exists in the system.",
            )
        current_user.email = user_in.email
    
    if user_in.full_name is not None:
        current_user.full_name = user_in.full_name
    
    if user_in.avatar_url is not None:
        current_user.avatar_url = user_in.avatar_url
        
    if user_in.language is not None:
        current_user.language = user_in.language
        
    if user_in.password is not None:
        current_user.hashed_password = get_password_hash(user_in.password)
        
    # Helper to sync with user_git_accounts table
    async def sync_git_account(provider: GitProviderType, token: str | None, username: str | None = None):
        if token is None:
            return
        
        # Find existing
        res = await db.execute(
            select(GitAccount).where(GitAccount.user_id == current_user.id, GitAccount.provider == provider)
        )
        account = res.scalar_one_or_none()
        
        if token == "": # Interpretation for disconnect
            if account:
                await db.delete(account)
            return

        if not account:
            account = GitAccount(user_id=current_user.id, provider=provider, access_token=token, username=username)
            db.add(account)
        else:
            account.access_token = token
            if username:
                account.username = username

    if user_in.github_token is not None:
        current_user.github_token = user_in.github_token
        await sync_git_account(GitProviderType.GITHUB, user_in.github_token, user_in.github_username)
    
    if user_in.github_username is not None:
        current_user.github_username = user_in.github_username

    if user_in.gitlab_token is not None:
        current_user.gitlab_token = user_in.gitlab_token
        await sync_git_account(GitProviderType.GITLAB, user_in.gitlab_token)

    if user_in.bitbucket_token is not None:
        current_user.bitbucket_token = user_in.bitbucket_token
        await sync_git_account(GitProviderType.BITBUCKET, user_in.bitbucket_token)
        
    if user_in.gitea_token is not None:
        current_user.gitea_token = user_in.gitea_token
        await sync_git_account(GitProviderType.GITEA, user_in.gitea_token)
    
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    
    # Reload with relationships
    result = await db.execute(
        select(User)
        .where(User.id == current_user.id)
        .options(selectinload(User.git_accounts))
    )
    return result.scalar_one()

@router.get("/", response_model=List[UserSchema])
async def search_users(
    query: str = "",
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Search users by name or email.
    """
    if not query:
        return []
        
    # git_accounts подгружается обязательно: схема ответа читает это
    # поле у каждого пользователя, а неподгруженная связь читается
    # уже при сериализации ответа, то есть вне greenlet, и поиск
    # падал с MissingGreenlet на 500. На пустом запросе список пуст и
    # сериализации нет — поэтому поломка была не видна: окно
    # приглашений показывало пустоту, а в консоли лежала ошибка.
    stmt = select(User).where(
        (User.is_active == True) &
        ((User.full_name.ilike(f"%{query}%")) | (User.email.ilike(f"%{query}%")))
    ).options(selectinload(User.git_accounts)).limit(20)
    
    result = await db.execute(stmt)
    users = result.scalars().all()
    return users
