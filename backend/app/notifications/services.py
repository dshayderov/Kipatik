from sqlalchemy.ext.asyncio import AsyncSession
from app.notifications.models import Notification, NotificationType
from app.models import User
from app.core.ws_manager import manager

class NotificationService:
    @staticmethod
    async def create_notification(
        db: AsyncSession,
        user_id: int,
        title: str,
        message: str,
        notification_type: NotificationType = NotificationType.INFO,
        project_id: int = None,
        task_id: int = None,
        invite_id: int = None
    ):
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            type=notification_type,
            project_id=project_id,
            task_id=task_id,
            invite_id=invite_id
        )
        db.add(notification)
        await db.flush() # To get the ID
        
        # Send WebSocket notification
        await manager.send_personal_message({
            "type": "notification",
            "data": {
                "id": notification.id,
                "title": notification.title,
                "message": notification.message,
                "type": notification.type,
                "created_at": notification.created_at.isoformat() if notification.created_at else None,
                "is_read": False,
                "project_id": notification.project_id,
                "task_id": notification.task_id,
                "invite_id": notification.invite_id
            }
        }, user_id)
        
        return notification
    @staticmethod
    async def process_mentions(
        db: AsyncSession,
        text: str,
        project_id: int,
        task_id: int,
        author: User
    ):
        import re
        from sqlalchemy import select, func
        from app.projects.models import ProjectMember
        from app.models import User
        
        # 1. Находим всех участников проекта
        stmt = select(User).join(ProjectMember).where(ProjectMember.project_id == project_id)
        result = await db.execute(stmt)
        project_users = result.scalars().all()
        
        mentioned_user_ids = set()

        for user in project_users:
            if user.id == author.id:
                continue
            
            # Проверяем email
            if f"@{user.email.lower()}" in text.lower():
                mentioned_user_ids.add(user.id)
                continue
                
            # Проверяем полное имя (заменяем пробелы на допустимые в упоминании символы или просто ищем с собачкой)
            # Например, "@Иванов Алексей" или "@ИвановАлексей"
            if user.full_name:
                name_clean = user.full_name.lower()
                name_no_spaces = name_clean.replace(" ", "")
                if f"@{name_clean}" in text.lower() or f"@{name_no_spaces}" in text.lower():
                    mentioned_user_ids.add(user.id)

        for user_id in mentioned_user_ids:
            await NotificationService.create_notification(
                db=db,
                user_id=user_id,
                title="Вас упомянули в комментарии",
                message=f"{author.full_name or author.email} упомянул вас в задаче #{task_id}",
                notification_type=NotificationType.INFO,
                project_id=project_id,
                task_id=task_id
            )
