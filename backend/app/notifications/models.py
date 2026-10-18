from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.core.database import Base

class NotificationType(str, enum.Enum):
    INFO = "info"
    PROJECT_INVITE = "project_invite"
    TASK_ASSIGNED = "task_assigned"
    TASK_UPDATED = "task_updated"
    PR_REVIEW_REQUESTED = "pr_review_requested"

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    type = Column(SQLEnum(NotificationType), default=NotificationType.INFO)
    
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Ссылки на связанные сущности (опционально)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    invite_id = Column(Integer, ForeignKey("project_invites.id", ondelete="CASCADE"), nullable=True)

    user = relationship("User", backref="notifications")
    project = relationship("Project", backref="notifications")
    task = relationship("Task", backref="notifications")
    invite = relationship("ProjectInvite", backref="notifications")
