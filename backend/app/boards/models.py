from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base

class Board(Base):
    __tablename__ = "boards"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), unique=True)
    
    project = relationship("Project", back_populates="board")
    columns = relationship("Column", back_populates="board", cascade="all, delete-orphan")

class Column(Base):
    __tablename__ = "columns"

    id = Column(Integer, primary_key=True, index=True)
    board_id = Column(Integer, ForeignKey("boards.id", ondelete="CASCADE"))
    name = Column(String, nullable=False) # Backlog, To Do, In Progress, Review, Done
    state_category = Column(String, default="TODO") # TODO, IN_PROGRESS, DONE
    position = Column(Integer, default=0) # Порядок отображения
    color = Column(String, nullable=True) # Дополнительный цвет для колонки
    
    board = relationship("Board", back_populates="columns")
    tasks = relationship("Task", back_populates="column")
