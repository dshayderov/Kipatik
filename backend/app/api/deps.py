from typing import Generator, Optional, Callable
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.database import get_db
from app.core import security
from app.models import User
from app.projects.models import ProjectMember, Role
from app.core.roles import Permission, ROLE_PERMISSIONS, ProjectRole
import json
from app.schemas.auth import TokenPayload

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)

async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(reusable_oauth2)
) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    
    result = await db.execute(select(User).where(User.id == int(token_data.sub)))
    user = result.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user

async def get_current_active_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user

async def get_project_member(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectMember:
    # Superusers have access even if not members
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, 
            ProjectMember.user_id == current_user.id
        )
    )
    member = result.scalar_one_or_none()
    
    if not member:
        if current_user.is_superuser:
             # Return a dummy ProjectMember for superuser to satisfy dependencies
             return ProjectMember(project_id=project_id, user_id=current_user.id, role="project_manager")
        raise HTTPException(
            status_code=403, detail="User is not a member of this project"
        )
    return member

def check_permission(permission: Permission):
    async def permission_checker(
        project_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ) -> ProjectMember:
        if current_user.is_superuser:
            return ProjectMember(project_id=project_id, user_id=current_user.id, role="project_manager")

        result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id, 
                ProjectMember.user_id == current_user.id
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            raise HTTPException(
                status_code=403, detail="User is not a member of this project"
            )
            
        # Load role from DB
        role_res = await db.execute(select(Role).where(Role.name == member.role))
        db_role = role_res.scalar_one_or_none()
        
        if not db_role:
            # Fallback for safety
            allowed_permissions = ROLE_PERMISSIONS.get(member.role, set())
            if permission not in allowed_permissions:
                raise HTTPException(
                    status_code=403, detail=f"Permission denied: {permission}"
                )
        else:
            role_permissions = json.loads(db_role.permissions)
            if permission.value not in role_permissions:
                raise HTTPException(
                    status_code=403, detail=f"Permission denied: {permission}"
                )
        
        return member
    return permission_checker
