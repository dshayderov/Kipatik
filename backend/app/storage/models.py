"""Настройки хранения файлов: лимиты и правила корзины."""
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class StorageSettings(Base):
    """Настройки хранилища. Всегда одна строка с id = 1.

    Отдельная строка на каждый параметр здесь не нужна: параметры
    образуют один связный набор и читаются всегда вместе.
    """

    __tablename__ = "storage_settings"

    id = Column(Integer, primary_key=True, default=1)

    # --- лимиты вложений ---
    # Предельный размер одного файла, МБ
    max_file_size_mb = Column(Integer, nullable=False, default=25)
    # Разрешённые расширения через запятую
    allowed_extensions = Column(
        String,
        nullable=False,
        default=".png,.jpg,.jpeg,.gif,.pdf,.doc,.docx,.txt,.zip,.log",
    )
    # Лимит хранилища нового проекта, МБ
    default_project_limit_mb = Column(Integer, nullable=False, default=500)

    # --- корзина ---
    # Через сколько дней удалённые файлы удаляются безвозвратно
    trash_retention_days = Column(Integer, nullable=False, default=7)
    # Запускать ли автоочистку по расписанию
    auto_purge_enabled = Column(Boolean, nullable=False, default=True)
    # Как часто проверять корзину, часов
    purge_interval_hours = Column(Integer, nullable=False, default=6)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())
    updated_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    updated_by = relationship("User")