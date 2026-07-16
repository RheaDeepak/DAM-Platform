from fastapi import APIRouter, HTTPException, Depends, status, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import SessionLocal
from app.models import Asset, AssetVersion, AssetMetadata, AuditLog, AuditAction, Tag
from app.schemas.asset import AssetCreate, AssetUpdate, AssetResponse, AssetDetailResponse, AssetListResponse
from app.api.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/assets", tags=["assets"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
def create_asset(
    asset: AssetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload a new asset"""
    new_asset = Asset(
        filename=asset.filename,
        original_filename=asset.original_filename,
        asset_type=asset.asset_type,
        file_path=asset.file_path,
        file_size=asset.file_size,
        mime_type=asset.mime_type,
        description=asset.description,
        owner_id=current_user.id
    )
    db.add(new_asset)
    db.commit()
    db.refresh(new_asset)
    
    # Log the upload action
    audit_log = AuditLog(
        asset_id=new_asset.id,
        user_id=current_user.id,
        action=AuditAction.UPLOADED,
        details=f"Uploaded {asset.filename}"
    )
    db.add(audit_log)
    db.commit()
    
    return AssetResponse.from_orm(new_asset)


@router.get("/", response_model=AssetListResponse)
def list_assets(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    asset_type: Optional[str] = None,
    status: Optional[str] = None,
    tag: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List assets with pagination and filtering"""
    query = db.query(Asset).filter(Asset.status != "deleted")
    
    if asset_type:
        query = query.filter(Asset.asset_type == asset_type)
    
    if status:
        query = query.filter(Asset.status == status)
    
    if tag:
        query = query.join(Tag, Asset.tags).filter(Tag.name == tag)
    
    total = query.count()
    items = query.offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [AssetResponse.from_orm(item) for item in items]
    }


@router.get("/{asset_id}", response_model=AssetDetailResponse)
def get_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get asset details with metadata and versions"""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Log the view action
    audit_log = AuditLog(
        asset_id=asset.id,
        user_id=current_user.id,
        action=AuditAction.VIEWED,
        details=f"Viewed {asset.filename}"
    )
    db.add(audit_log)
    db.commit()
    
    return AssetDetailResponse.from_orm(asset)


@router.patch("/{asset_id}", response_model=AssetResponse)
def update_asset(
    asset_id: int,
    asset_update: AssetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update asset metadata"""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if asset.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this asset")
    
    if asset_update.filename:
        asset.filename = asset_update.filename
    if asset_update.description is not None:
        asset.description = asset_update.description
    if asset_update.status:
        asset.status = asset_update.status
    
    db.commit()
    db.refresh(asset)
    
    # Log the modification
    audit_log = AuditLog(
        asset_id=asset.id,
        user_id=current_user.id,
        action=AuditAction.MODIFIED,
        details="Updated asset metadata"
    )
    db.add(audit_log)
    db.commit()
    
    return AssetResponse.from_orm(asset)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an asset (soft delete by marking as deleted)"""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    if asset.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this asset")
    
    asset.status = "deleted"
    db.commit()
    
    # Log the deletion
    audit_log = AuditLog(
        asset_id=asset.id,
        user_id=current_user.id,
        action=AuditAction.DELETED,
        details="Deleted asset"
    )
    db.add(audit_log)
    db.commit()


@router.post("/{asset_id}/tags/{tag_id}", status_code=status.HTTP_200_OK)
def add_tag_to_asset(
    asset_id: int,
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add a tag to an asset"""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    if tag not in asset.tags:
        asset.tags.append(tag)
        db.commit()
    
    audit_log = AuditLog(
        asset_id=asset.id,
        user_id=current_user.id,
        action=AuditAction.TAGGED,
        details=f"Added tag: {tag.name}"
    )
    db.add(audit_log)
    db.commit()
    
    return {"message": "Tag added successfully"}


@router.delete("/{asset_id}/tags/{tag_id}", status_code=status.HTTP_200_OK)
def remove_tag_from_asset(
    asset_id: int,
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Remove a tag from an asset"""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    if tag in asset.tags:
        asset.tags.remove(tag)
        db.commit()
    
    audit_log = AuditLog(
        asset_id=asset.id,
        user_id=current_user.id,
        action=AuditAction.UNTAGGED,
        details=f"Removed tag: {tag.name}"
    )
    db.add(audit_log)
    db.commit()
    
    return {"message": "Tag removed successfully"}