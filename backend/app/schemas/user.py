from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime

class GitAccountSchema(BaseModel):
    id: int
    provider: str
    username: Optional[str] = None
    created_at: datetime
    class Config: from_attributes = True
class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    language: Optional[str] = "en"
    is_active: Optional[bool] = True
    is_superuser: Optional[bool] = False
    can_create_projects: Optional[bool] = False
    role: Optional[str] = "developer"
    github_username: Optional[str] = None

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=72)

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    language: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8, max_length=72)
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    can_create_projects: Optional[bool] = None
    github_token: Optional[str] = None
    github_username: Optional[str] = None
    gitlab_token: Optional[str] = None
    bitbucket_token: Optional[str] = None
    gitea_token: Optional[str] = None

class User(UserBase):
    id: int
    git_accounts: List[GitAccountSchema] = []

    class Config:
        from_attributes = True

class ProjectMemberBase(BaseModel):
    project_id: int
    user_id: int
    role: str

class ProjectMember(ProjectMemberBase):
    class Config:
        from_attributes = True

class ProjectWithRole(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    role: str # Роль пользователя в этом проекте

    class Config:
        from_attributes = True
