import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, Boolean, BigInteger, Table
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from app.core.database import Base

# Many-to-Many relationship for task dependencies
task_dependencies = Table(
    "task_dependencies",
    Base.metadata,
    Column("task_id", Integer, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("depends_on_id", Integer, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
)

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    description = Column(Text)
    priority = Column(Integer, default=1) # 1: Low, 2: Medium, 3: High

    # Тип задачи: bug | feature | None. Выбирает человек при создании.
    # Строкой, а не enum: перечень короткий и расширяемый, и новое
    # значение не должно требовать миграции типа данных.
    task_type = Column(String, nullable=True)
    
    start_date = Column(DateTime(timezone=True), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    column_id = Column(Integer, ForeignKey("columns.id"))
    assignee_id = Column(Integer, ForeignKey("users.id"))
    
    parent_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="tasks")
    column = relationship("Column", back_populates="tasks")
    assignee = relationship("User", back_populates="tasks")
    
    # Hierarchical relationship
    parent = relationship("Task", remote_side=[id], backref="subtasks_hierarchical")
    
    # Task dependencies
    dependencies = relationship(
        "Task",
        secondary=task_dependencies,
        primaryjoin=id == task_dependencies.c.task_id,
        secondaryjoin=id == task_dependencies.c.depends_on_id,
        backref="dependent_tasks"
    )
    
    commits = relationship("Commit", secondary="task_commits", back_populates="tasks")
    branches = relationship("Branch", secondary="task_branches", back_populates="tasks")
    pull_requests = relationship("PullRequest", secondary="task_pull_requests", back_populates="tasks")
    subtasks = relationship("SubTask", back_populates="task", cascade="all, delete-orphan")
    comments = relationship("TaskComment", back_populates="task", cascade="all, delete-orphan")

class SubTask(Base):
    __tablename__ = "subtasks"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    is_completed = Column(Boolean, default=False)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    
    task = relationship("Task", back_populates="subtasks")

class TaskComment(Base):
    __tablename__ = "task_comments"
    
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("task_comments.id", ondelete="CASCADE"), nullable=True)
    
    task = relationship("Task", back_populates="comments")
    author = relationship("User")
    
    # Self-referential relationship for replies
    replies = relationship(
        "TaskComment", 
        backref=backref("parent", remote_side=[id]),
        cascade="all, delete-orphan"
    )
    
    reactions = relationship("CommentReaction", back_populates="comment", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="comment", cascade="all, delete-orphan")

class CommentReaction(Base):
    __tablename__ = "comment_reactions"
    
    id = Column(Integer, primary_key=True, index=True)
    comment_id = Column(Integer, ForeignKey("task_comments.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    emoji = Column(String(50), nullable=False) # e.g., "👍", "🚀"
    
    comment = relationship("TaskComment", back_populates="reactions")
    user = relationship("User")

class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String, nullable=False)
    path = Column(String, nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    mime_type = Column(String, nullable=True)
    
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    comment_id = Column(Integer, ForeignKey("task_comments.id", ondelete="CASCADE"), nullable=True)
    
    status = Column(String, default="active") # active, deleted, orphan
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    uploader = relationship("User")
    project = relationship("Project")
    task = relationship("Task")
    comment = relationship("TaskComment", back_populates="attachments")

class TaskActivity(Base):
    __tablename__ = "task_activities"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Тип события: status_change, assignee_change, priority_change, ai_suggestion, subtask_added, etc.
    activity_type = Column(String, nullable=False)
    
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    task = relationship("Task", backref=backref("activities", cascade="all, delete-orphan", order_by="desc(TaskActivity.created_at)"))
    user = relationship("User")
