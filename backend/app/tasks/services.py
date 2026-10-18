from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.tasks.models import Task
from app.boards.models import Column, Board
from typing import Optional

class TaskStatusService:
    @staticmethod
    async def move_task_to_status(db: AsyncSession, task_id: int, status_type: str) -> bool:
        """
        Универсальный метод перемещения задачи.
        status_type может быть: 'IN_PROGRESS', 'REVIEW', 'DONE', 'TODO'
        """
        # 1. Получаем задачу
        result = await db.execute(select(Task).filter(Task.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            return False

        # 2. Получаем доску проекта
        board_stmt = select(Board).filter(Board.project_id == task.project_id)
        res_board = await db.execute(board_stmt)
        board = res_board.scalar_one_or_none()
        if not board:
            return False

        # 3. Ищем подходящую колонку
        # Сначала ищем по категории (для DONE, TODO, IN_PROGRESS)
        # Если это REVIEW, ищем колонку с именем "Review" или категорией IN_PROGRESS (как fallback)
        
        query = select(Column).where(Column.board_id == board.id)
        
        if status_type == "REVIEW":
            # Ищем колонку с именем Review или категорию REVIEW (если вдруг она есть)
            query = query.where(or_(Column.name.ilike("%Review%"), Column.state_category == "REVIEW"))
        else:
            query = query.where(Column.state_category == status_type)
            
        query = query.order_by(Column.position)
        
        res_col = await db.execute(query)
        column = res_col.scalars().first()
        
        # Если для REVIEW не нашли специальную колонку, ищем IN_PROGRESS
        if not column and status_type == "REVIEW":
            query_fallback = select(Column).where(
                Column.board_id == board.id, 
                Column.state_category == "IN_PROGRESS"
            ).order_by(Column.position)
            res_fallback = await db.execute(query_fallback)
            column = res_fallback.scalars().first()

        if column and task.column_id != column.id:
            task.column_id = column.id
            await db.commit()
            print(f"Auto-moved task #{task_id} to '{column.name}'")
            return True
            
        return False

    @staticmethod
    async def move_task_by_category(db: AsyncSession, task_id: int, state_category: str) -> bool:
        # Для обратной совместимости
        return await TaskStatusService.move_task_to_status(db, task_id, state_category)
