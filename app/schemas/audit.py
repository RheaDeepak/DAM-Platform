from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.models.audit import AuditAction


class AuditLogResponse(BaseModel):
    id: int
    asset_id: int
    user_id: int
    action: AuditAction
    details: Optional[str]
    ip_address: Optional[str]
    timestamp: datetime

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: List[AuditLogResponse]
