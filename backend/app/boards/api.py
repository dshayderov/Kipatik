from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import joinedload
from typing import List, Optional
from pydantic import BaseModel
from app.core.database import get_db
from app.boards.models import Board, Column
from app.projects.models import Project
from app.models import User
from app.api import deps
from app.core.roles import Permission, ProjectRole, ROLE_PERMISSIONS
from app.projects.models import ProjectMember

router = APIRouter()

class ColumnSchema(BaseModel):
    id: int
    name: str
    state_category: str
    position: int
    color: Optional[str] = None
    class Config: from_attributes = True

class ColumnCreate(BaseModel):
    name: str
    state_category: str
    board_id: int
    position: Optional[int] = 0
    color: Optional[str] = None

class ColumnUpdate(BaseModel):
    name: Optional[str] = None
    state_category: Optional[str] = None
    position: Optional[int] = None
    color: Optional[str] = None

class BoardSchema(BaseModel):
    id: int
    project_id: int
    columns: List[ColumnSchema]
    class Config: from_attributes = True

@router.get("/{project_id}", response_model=BoardSchema)
async def get_board(
    project_id: int, 
    db: AsyncSession = Depends(get_db),
    member: ProjectMember = Depends(deps.check_permission(Permission.BOARD_VIEW))
):
    result = await db.execute(
        select(Board)
        .options(joinedload(Board.columns))
        .filter(Board.project_id == project_id)
    )
    board = result.unique().scalar_one_or_none()
    
    if not board:
        # Если доски нет, создаем её (только если есть права на управление колонками)
        allowed_permissions = ROLE_PERMISSIONS.get(member.role, set())
        if Permission.BOARD_MANAGE_COLUMNS not in allowed_permissions:
             raise HTTPException(status_code=403, detail="Only managers can initialize the board")

        board = Board(project_id=project_id)
        db.add(board)
        await db.commit()
        
        # Дефолтные колонки с категориями
        default_cols = [
            {"name": "Backlog", "cat": "TODO", "pos": 0},
            {"name": "Todo", "cat": "TODO", "pos": 1},
            {"name": "In Progress", "cat": "IN_PROGRESS", "pos": 2},
            {"name": "Review", "cat": "IN_PROGRESS", "pos": 3},
            {"name": "Done", "cat": "DONE", "pos": 4},
        ]
        
        for col_data in default_cols:
            col = Column(
                board_id=board.id, 
                name=col_data["name"], 
                state_category=col_data["cat"],
                position=col_data["pos"]
            )
            db.add(col)
        await db.commit()
        
        # Перечитываем доску с колонками
        result = await db.execute(
            select(Board)
            .options(joinedload(Board.columns))
            .filter(Board.project_id == project_id)
        )
        board = result.unique().scalar_one_or_none()
        
    return board

@router.post("/columns", response_model=ColumnSchema)
async def create_column(
    col_in: ColumnCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    # Находим project_id для проверки прав
    board_res = await db.execute(select(Board).where(Board.id == col_in.board_id))
    board = board_res.scalar_one_or_none()
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")
    
    # Проверяем права вручную, так как project_id в теле запроса
    member_res = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == board.project_id, 
            ProjectMember.user_id == current_user.id
        )
    )
    member = member_res.scalar_one_or_none()
    if not member or Permission.BOARD_MANAGE_COLUMNS not in ROLE_PERMISSIONS.get(member.role, set()):
        raise HTTPException(status_code=403, detail="Permission denied")
        
    db_col = Column(**col_in.model_dump())
    db.add(db_col)
    await db.commit()
    await db.refresh(db_col)
    return db_col

@router.patch("/columns/{column_id}", response_model=ColumnSchema)
async def update_column(
    column_id: int,
    col_in: ColumnUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    # Проверка доступа через проект
    col_res = await db.execute(
        select(Column).options(joinedload(Column.board)).where(Column.id == column_id)
    )
    db_col = col_res.scalar_one_or_none()
    if not db_col:
        raise HTTPException(status_code=404, detail="Column not found")
        
    member_res = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == db_col.board.project_id, 
            ProjectMember.user_id == current_user.id
        )
    )
    member = member_res.scalar_one_or_none()
    if not member or Permission.BOARD_MANAGE_COLUMNS not in ROLE_PERMISSIONS.get(member.role, set()):
        raise HTTPException(status_code=403, detail="Permission denied")
        
    update_data = col_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_col, key, value)
        
    await db.commit()
    await db.refresh(db_col)
    return db_col

@router.delete("/columns/{column_id}")
async def delete_column(
    column_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user)
):
    # Проверка доступа
    col_res = await db.execute(
        select(Column).options(joinedload(Column.board)).where(Column.id == column_id)
    )
    db_col = col_res.scalar_one_or_none()
    if not db_col:
        raise HTTPException(status_code=404, detail="Column not found")
        
    member_res = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == db_col.board.project_id, 
            ProjectMember.user_id == current_user.id
        )
    )
    member = member_res.scalar_one_or_none()
    if not member or Permission.BOARD_MANAGE_COLUMNS not in ROLE_PERMISSIONS.get(member.role, set()):
        raise HTTPException(status_code=403, detail="Permission denied")
        
    await db.delete(db_col)
    await db.commit()
    return {"status": "success"}
