from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import relationship
from app.core.crypto import EncryptedString
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    avatar_url = Column(String, nullable=True)
    language = Column(String, default="en")
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    can_create_projects = Column(Boolean, default=False)
    role = Column(String, default="developer")
    
    # Git Integration (VCS)
    github_token = Column(EncryptedString, nullable=True) # PAT или OAuth Access Token
    github_username = Column(String, nullable=True)
    gitlab_token = Column(EncryptedString, nullable=True)
    bitbucket_token = Column(EncryptedString, nullable=True)
    gitea_token = Column(EncryptedString, nullable=True)

    projects = relationship("Project", back_populates="owner")
    tasks = relationship("Task", back_populates="assignee")

