import mimetypes
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends, status, Query, File, Form, UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from typing import Optional

from app.database import SessionLocal
from app.models import Asset, AssetVersion, AssetMetadata, AssetType, AuditLog, AuditAction, Tag
from app.schemas.asset import AssetCreate, AssetUpdate, AssetResponse, AssetDetailResponse, AssetListResponse
from app.api.auth import require_roles
from app.models.user import User

router = APIRouter(prefix="/assets", tags=["assets"])

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORAGE_DIRECTORY = PROJECT_ROOT / "storage"
MAX_UPLOAD_SIZE_BYTES = 100 * 1024 * 1024


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def infer_asset_type(mime_type: str) -> AssetType:
    """Map a MIME type to one of the asset types supported by this project."""
    if mime_type.startswith("image/"):
        return AssetType.IMAGE
    if mime_type.startswith("video/"):
        return AssetType.VIDEO
    if mime_type.startswith("audio/"):
        return AssetType.AUDIO
    if mime_type.startswith(("text/", "application/pdf", "application/msword")) or \
            "officedocument" in mime_type:
        return AssetType.DOCUMENT
    return AssetType.OTHER


@router.post("/", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
def create_asset(
    asset: AssetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "editor"))
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


@router.post("/upload", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    asset_type: Optional[AssetType] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "editor")),
):
    """Save an uploaded file locally and create its asset record."""
    original_filename = Path(file.filename or "").name
    if not original_filename:
        raise HTTPException(status_code=400, detail="A file with a filename is required")

    mime_type = file.content_type or mimetypes.guess_type(original_filename)[0] or "application/octet-stream"
    stored_filename = f"{uuid4().hex}{Path(original_filename).suffix.lower()}"
    STORAGE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    stored_path = STORAGE_DIRECTORY / stored_filename
    file_size = 0
    upload_succeeded = False

    try:
        with stored_path.open("xb") as destination:
            while chunk := await file.read(1024 * 1024):
                file_size += len(chunk)
                if file_size > MAX_UPLOAD_SIZE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="File is too large. The maximum upload size is 100 MB.",
                    )
                destination.write(chunk)

        new_asset = Asset(
            filename=title.strip() if title and title.strip() else original_filename,
            original_filename=original_filename,
            asset_type=asset_type or infer_asset_type(mime_type),
            file_path=stored_path.relative_to(PROJECT_ROOT).as_posix(),
            file_size=file_size,
            mime_type=mime_type,
            description=description,
            owner_id=current_user.id,
        )
        db.add(new_asset)
        db.flush()
        db.add(AuditLog(
            asset_id=new_asset.id,
            user_id=current_user.id,
            action=AuditAction.UPLOADED,
            details=f"Uploaded {original_filename}",
        ))
        db.commit()
        db.refresh(new_asset)
        upload_succeeded = True
        return AssetResponse.from_orm(new_asset)
    except HTTPException:
        db.rollback()
        raise
    except (OSError, SQLAlchemyError):
        db.rollback()
        raise HTTPException(status_code=500, detail="The upload could not be saved")
    finally:
        if not upload_succeeded and stored_path.exists():
            stored_path.unlink()
        await file.close()


@router.get("/", response_model=AssetListResponse)
def list_assets(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    asset_type: Optional[str] = None,
    status: Optional[str] = None,
    tag: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "editor", "viewer"))
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
    current_user: User = Depends(require_roles("admin", "editor", "viewer"))
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
    current_user: User = Depends(require_roles("admin", "editor"))
):
    """Update asset metadata"""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
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
    current_user: User = Depends(require_roles("admin"))
):
    """Delete an asset (soft delete by marking as deleted)"""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
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
    current_user: User = Depends(require_roles("admin", "editor"))
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
    current_user: User = Depends(require_roles("admin", "editor"))
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
