from typing import List, Optional
from pydantic import BaseModel

class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None
    permissions: str # JSON string of list of strings
    is_system: bool = False

class RoleCreate(RoleBase):
    pass

class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[str] = None
    is_system: Optional[bool] = None

class Role(RoleBase):
    id: int

    class Config:
        from_attributes = True
