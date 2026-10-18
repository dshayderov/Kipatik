import os
import shutil
from datetime import datetime, timedelta
from sqlalchemy import select, delete, update
from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.tasks.models import Attachment
from app.projects.models import Project

@celery_app.task
async def cleanup_orphan_files():
    """Удаляет осиротевшие файлы старше 24 часов"""
    threshold = datetime.utcnow() - timedelta(hours=24)
    
    async with SessionLocal() as db:
        result = await db.execute(
            select(Attachment).where(
                Attachment.status == "orphan",
                Attachment.created_at < threshold
            )
        )
        orphans = result.scalars().all()
        
        for attachment in orphans:
            # Физическое удаление
            full_path = os.path.join("uploads", attachment.path)
            if os.path.exists(full_path):
                os.remove(full_path)
            
            # Обновление квоты проекта
            project_res = await db.execute(select(Project).where(Project.id == attachment.project_id))
            project = project_res.scalar_one_or_none()
            if project:
                project.storage_used_bytes = max(0, project.storage_used_bytes - attachment.size_bytes)
            
            attachment.status = "deleted"
            attachment.deleted_at = datetime.utcnow()
        
        await db.commit()
        return len(orphans)

@celery_app.task
async def cleanup_deleted_files():
    """Физически удаляет файлы, помеченные как deleted > 7 дней назад"""
    threshold = datetime.utcnow() - timedelta(days=7)
    
    async with SessionLocal() as db:
        result = await db.execute(
            select(Attachment).where(
                Attachment.status == "deleted",
                Attachment.deleted_at < threshold
            )
        )
        deleted_files = result.scalars().all()
        
        for attachment in deleted_files:
            # Физическое удаление
            full_path = os.path.join("uploads", attachment.path)
            if os.path.exists(full_path):
                os.remove(full_path)
            
            # Удаление записи из БД
            await db.delete(attachment)
        
        await db.commit()
        return len(deleted_files)
