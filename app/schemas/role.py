from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.models.role import PermissionType


class PermissionResponse(BaseModel):
    id: int
    permission_type: PermissionType
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    permission_ids: Optional[List[int]] = []


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permission_ids: Optional[List[int]] = None


class RoleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RoleDetailResponse(RoleResponse):
    permissions: List[PermissionResponse]
