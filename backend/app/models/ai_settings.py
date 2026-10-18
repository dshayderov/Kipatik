"""Настройка включения нейросетевых моделей.

Это не модель данных, а переключатель «включена/выключена».
Сами артефакты (веса) лежат на диске в CODE_MODEL_DIR, а здесь
хранится решение администратора, действующее поверх значений
из окружения.

Хранить решение в базе, а не в .env, нужно по трём причинам:
  * переключение применяется без перезапуска приложения;
  * оно не теряется при выкатывании и не зависит от того, как запущен
    процесс;
  * видно, кто и когда изменил настройку.
"""
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class AIModelSetting(Base):
    """Включение или выключение одной модели силами администратора."""

    __tablename__ = "ai_model_settings"

    # Ключ из app/ai/api.py: encoder | type_classifier | progress_estimator
    key = Column(String, primary_key=True)
    enabled = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())
    updated_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    updated_by = relationship("User")