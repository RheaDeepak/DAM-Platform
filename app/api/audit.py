from fastapi import APIRouter, HTTPException, Depends, status, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import SessionLocal
from app.models import AuditLog, Asset
from app.schemas.audit import AuditLogResponse, AuditLogListResponse
from app.api.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/audit-logs", tags=["audit"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/", response_model=AuditLogListResponse)
def list_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    asset_id: Optional[int] = None,
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List audit logs with filtering"""
    query = db.query(AuditLog)
    
    if asset_id:
        query = query.filter(AuditLog.asset_id == asset_id)
    
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    
    if action:
        query = query.filter(AuditLog.action == action)
    
    total = query.count()
    items = query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [AuditLogResponse.from_orm(item) for item in items]
    }


@router.get("/assets/{asset_id}", response_model=AuditLogListResponse)
def get_asset_audit_logs(
    asset_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get audit logs for a specific asset"""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    query = db.query(AuditLog).filter(AuditLog.asset_id == asset_id)
    total = query.count()
    items = query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [AuditLogResponse.from_orm(item) for item in items]
    }
