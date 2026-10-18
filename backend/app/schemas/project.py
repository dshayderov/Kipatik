from pydantic import BaseModel
from typing import Optional, List, Any

class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    git_url: Optional[str] = None
    rules: Optional[Any] = None

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(ProjectBase):
    name: Optional[str] = None
    rules: Optional[Any] = None

class Project(ProjectBase):
    id: int
    owner_id: int
    user_role: Optional[str] = None # Added for convenience in frontend

    class Config:
        from_attributes = True
