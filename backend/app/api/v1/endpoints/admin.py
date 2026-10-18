from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.api import deps
from app.models import User, Project, Task
from app.projects.models import Role, ProjectMember
from app.schemas.user import User as UserSchema, UserUpdate, UserCreate
from app.schemas.role import Role as RoleSchema, RoleCreate, RoleUpdate
from app.core.security import get_password_hash

router = APIRouter()

@router.get("/users", response_model=List[UserSchema])
async def read_users(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    query: str = Query(None),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Retrieve users (Admin only).
    """
    # git_accounts подгружаем заранее: поле есть в схеме ответа, а ленивая
    # загрузка связи в асинхронном режиме падает с MissingGreenlet уже на
    # сериализации ответа.
    stmt = select(User).options(selectinload(User.git_accounts))
    if query:
        stmt = stmt.where((User.email.ilike(f"%{query}%")) | (User.full_name.ilike(f"%{query}%")))
    
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/users", response_model=UserSchema)
async def create_user(
    *,
    db: AsyncSession = Depends(deps.get_db),
    user_in: UserCreate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Create a new user (Admin only).
    """
    result = await db.execute(
        select(User)
        .where(User.email == user_in.email)
        .options(selectinload(User.git_accounts))
    )
    user = result.scalar_one_or_none()
    if user:
        raise HTTPException(status_code=400, detail="The user with this email already exists in the system.")
    
    db_obj = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        is_superuser=getattr(user_in, 'is_superuser', False),
        can_create_projects=getattr(user_in, 'can_create_projects', False)
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)

    # Перечитываем с предзагруженной связью: у нового объекта
    # git_accounts не загружены, и сериализация ответа упала бы
    # с MissingGreenlet. То же, что в auth.register.
    result = await db.execute(
        select(User)
        .where(User.id == db_obj.id)
        .options(selectinload(User.git_accounts))
    )
    return result.scalar_one()

@router.patch("/users/{user_id}", response_model=UserSchema)
async def update_user(
    *,
    db: AsyncSession = Depends(deps.get_db),
    user_id: int,
    user_in: UserUpdate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Update a user (Admin only).
    """
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.git_accounts))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user_in.email:
        user.email = user_in.email
    if user_in.full_name:
        user.full_name = user_in.full_name
    if user_in.password:
        user.hashed_password = get_password_hash(user_in.password)
    
    # Дополнительные поля для админа
    if hasattr(user_in, 'is_superuser') and user_in.is_superuser is not None:
        if user_id == current_user.id and user_in.is_superuser is False:
            raise HTTPException(status_code=400, detail="You cannot remove your own superuser status")
        user.is_superuser = user_in.is_superuser
    if hasattr(user_in, 'can_create_projects') and user_in.can_create_projects is not None:
        user.can_create_projects = user_in.can_create_projects
    if hasattr(user_in, 'is_active') and user_in.is_active is not None:
        user.is_active = user_in.is_active
        
    db.add(user)
    await db.commit()

    # После commit атрибуты сессии сброшены, а db.refresh() связи не
    # подтягивает — сериализация ответа упала бы с MissingGreenlet.
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.git_accounts))
    )
    return result.scalar_one()

@router.delete("/users/{user_id}")
async def delete_user(
    *,
    db: AsyncSession = Depends(deps.get_db),
    user_id: int,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Delete a user (Admin only).
    """
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete yourself")
        
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    await db.delete(user)
    await db.commit()
    return {"status": "ok"}

# Roles Management
@router.get("/roles", response_model=List[RoleSchema])
async def read_roles(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Retrieve roles (Admin only).
    """
    result = await db.execute(select(Role))
    return result.scalars().all()

@router.post("/roles", response_model=RoleSchema)
async def create_role(
    *,
    db: AsyncSession = Depends(deps.get_db),
    role_in: RoleCreate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Create a new role (Admin only).
    """
    db_obj = Role(**role_in.dict())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj

@router.patch("/roles/{role_id}", response_model=RoleSchema)
async def update_role(
    *,
    db: AsyncSession = Depends(deps.get_db),
    role_id: int,
    role_in: RoleUpdate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Update a role (Admin only).
    """
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    update_data = role_in.dict(exclude_unset=True)
    for field in update_data:
        setattr(role, field, update_data[field])
    
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role

@router.delete("/roles/{role_id}")
async def delete_role(
    *,
    db: AsyncSession = Depends(deps.get_db),
    role_id: int,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Delete a role (Admin only).
    """
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete system roles")
    
    await db.delete(role)
    await db.commit()
    return {"status": "ok"}

# Projects Management
@router.get("/projects")
async def read_projects(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Retrieve all projects with owner info (Admin only).
    """
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.owner))
        .offset(skip)
        .limit(limit)
    )
    projects = result.scalars().all()
    
    # Map to include owner details
    projects_data = []
    for p in projects:
        projects_data.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "owner_id": p.owner_id,
            "owner_name": p.owner.full_name if p.owner else "Unknown",
            "owner_email": p.owner.email if p.owner else "Unknown"
        })
    return projects_data

@router.get("/projects/{project_id}/members")
async def read_project_members(
    *,
    db: AsyncSession = Depends(deps.get_db),
    project_id: int,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Get project members for admin.
    """
    # Get all roles for mapping fallback
    roles_result = await db.execute(select(Role))
    all_roles = roles_result.scalars().all()
    role_name_to_id = {r.name: r.id for r in all_roles}

    result = await db.execute(
        select(ProjectMember, User, Role)
        .join(User, ProjectMember.user_id == User.id)
        .outerjoin(Role, ProjectMember.role_id == Role.id)
        .where(ProjectMember.project_id == project_id)
    )
    members = []
    for pm, user, role in result:
        role_id = pm.role_id
        # Fallback to mapping if role_id is NULL
        if role_id is None and pm.role in role_name_to_id:
            role_id = role_name_to_id[pm.role]
            
        members.append({
            "user_id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "role_id": role_id,
            "role_name": role.name if role else pm.role
        })
    return members

@router.post("/projects/{project_id}/members")
async def update_project_member(
    *,
    db: AsyncSession = Depends(deps.get_db),
    project_id: int,
    user_id: int,
    role_id: int,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Add or update project member role.
    """
    result = await db.execute(
        select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
    )
    pm = result.scalar_one_or_none()
    if pm:
        pm.role_id = role_id
        # Also update the string role for backward compatibility
        role_result = await db.execute(select(Role).where(Role.id == role_id))
        role = role_result.scalar_one_or_none()
        if role:
            pm.role = role.name
    else:
        role_result = await db.execute(select(Role).where(Role.id == role_id))
        role = role_result.scalar_one_or_none()
        pm = ProjectMember(project_id=project_id, user_id=user_id, role_id=role_id, role=role.name if role else "developer")
        db.add(pm)
    
    await db.commit()
    return {"status": "ok"}

@router.delete("/projects/{project_id}/members/{user_id}")
async def remove_project_member(
    *,
    db: AsyncSession = Depends(deps.get_db),
    project_id: int,
    user_id: int,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Remove member from project.
    """
    result = await db.execute(
        select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
    )
    pm = result.scalar_one_or_none()
    if not pm:
        raise HTTPException(status_code=404, detail="Member not found")
    
    await db.delete(pm)
    await db.commit()
    return {"status": "ok"}

@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Get system statistics (Admin only).
    """
    users_count = await db.scalar(select(func.count(User.id)))
    projects_count = await db.scalar(select(func.count(Project.id)))
    tasks_count = await db.scalar(select(func.count(Task.id)))
    
    return {
        "users_total": users_count,
        "projects_total": projects_count,
        "tasks_total": tasks_count
    }
