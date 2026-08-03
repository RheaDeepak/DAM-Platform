import hashlib
import mimetypes
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends, status, Query, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, selectinload
from typing import Literal, Optional

from app.database import SessionLocal
from app.models import Asset, AssetVersion, AssetMetadata, AssetType, AssetStatus, AuditLog, AuditAction, Tag
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


def asset_query(db: Session, include_details: bool = False):
    """Load an asset with the relationships exposed by the response schemas."""
    options = [joinedload(Asset.owner), selectinload(Asset.tags)]
    if include_details:
        options.extend([
            selectinload(Asset.asset_metadata),
            selectinload(Asset.versions),
        ])
    return db.query(Asset).options(*options)


def get_asset_or_404(db: Session, asset_id: int, include_details: bool = False) -> Asset:
    """Return a non-deleted asset or the consistent API 404 response."""
    asset = asset_query(db, include_details).filter(
        Asset.id == asset_id,
        Asset.status != AssetStatus.DELETED,
    ).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


def local_storage_path(file_path: str) -> Optional[Path]:
    """Resolve a stored path only when it is safely inside storage/."""
    candidate = (PROJECT_ROOT / file_path).resolve()
    try:
        candidate.relative_to(STORAGE_DIRECTORY.resolve())
    except ValueError:
        return None
    return candidate


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

    # MIME type comes from the multipart upload, with a filename-based fallback.
    mime_type = file.content_type or mimetypes.guess_type(original_filename)[0] or "application/octet-stream"
    # Generated from the submitted filename; users do not provide this separately.
    file_extension = Path(original_filename).suffix.lower().lstrip(".") or None
    stored_filename = f"{uuid4().hex}{Path(original_filename).suffix.lower()}"
    STORAGE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    stored_path = STORAGE_DIRECTORY / stored_filename
    # File size is counted from the actual upload chunks, not supplied by the user.
    file_size = 0
    # Updated as each chunk is written, avoiding a second read of the saved file.
    checksum_hasher = hashlib.sha256()
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
                checksum_hasher.update(chunk)
                destination.write(chunk)

        # The final SHA-256 hex digest identifies this exact file content.
        checksum = checksum_hasher.hexdigest()

        new_asset = Asset(
            filename=title.strip() if title and title.strip() else original_filename,
            original_filename=original_filename,
            asset_type=asset_type or infer_asset_type(mime_type),
            file_path=stored_path.relative_to(PROJECT_ROOT).as_posix(),
            file_size=file_size,
            mime_type=mime_type,
            file_extension=file_extension,
            checksum=checksum,
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


@router.get(
    "/",
    response_model=AssetListResponse,
    summary="List assets",
    responses={401: {"description": "Authentication required"}},
)
def list_assets(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    asset_type: Optional[AssetType] = None,
    status: Optional[AssetStatus] = None,
    tag: Optional[str] = None,
    sort_by: Literal["created_at", "updated_at", "filename", "file_size"] = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "editor", "viewer"))
):
    """List visible assets with filters, pagination, and a safe sort field."""
    query = asset_query(db).filter(Asset.status != AssetStatus.DELETED)
    
    if asset_type:
        query = query.filter(Asset.asset_type == asset_type)
    
    if status:
        query = query.filter(Asset.status == status)
    
    if tag:
        query = query.join(Tag, Asset.tags).filter(Tag.name == tag)

    total = query.count()
    sort_column = getattr(Asset, sort_by)
    order_by = sort_column.asc() if sort_order == "asc" else sort_column.desc()
    items = query.order_by(order_by, Asset.id.desc()).offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "page": (skip // limit) + 1,
        "pages": (total + limit - 1) // limit,
        "items": [AssetResponse.from_orm(item) for item in items]
    }


@router.get(
    "/{asset_id}/download",
    summary="Download an asset file",
    responses={404: {"description": "Asset or local file not found"}},
)
def download_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "editor", "viewer")),
):
    """Download the locally stored file for an asset without exposing arbitrary paths."""
    asset = get_asset_or_404(db, asset_id)
    stored_path = local_storage_path(asset.file_path)
    if not stored_path or not stored_path.is_file():
        raise HTTPException(status_code=404, detail="Asset file not found")

    db.add(AuditLog(
        asset_id=asset.id,
        user_id=current_user.id,
        action=AuditAction.DOWNLOADED,
        details=f"Downloaded {asset.filename}",
    ))
    db.commit()
    return FileResponse(
        path=stored_path,
        media_type=asset.mime_type,
        filename=asset.original_filename,
    )


@router.get(
    "/{asset_id}",
    response_model=AssetDetailResponse,
    summary="Get one asset",
    responses={404: {"description": "Asset not found"}},
)
def get_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "editor", "viewer"))
):
    """Return an asset with its owner, tags, metadata, and versions."""
    asset = get_asset_or_404(db, asset_id, include_details=True)
    
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


@router.put(
    "/{asset_id}",
    response_model=AssetDetailResponse,
    summary="Update asset metadata",
    responses={404: {"description": "Asset not found"}},
)
@router.patch(
    "/{asset_id}",
    response_model=AssetDetailResponse,
    summary="Partially update asset metadata",
    responses={404: {"description": "Asset not found"}},
)
def update_asset(
    asset_id: int,
    asset_update: AssetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "editor"))
):
    """Update title, description, tags, or status without changing the uploaded file."""
    if not asset_update.model_fields_set:
        raise HTTPException(status_code=422, detail="Provide at least one field to update")

    asset = get_asset_or_404(db, asset_id, include_details=True)
    
    if asset_update.title is not None:
        asset.filename = asset_update.title
    elif asset_update.filename is not None:
        asset.filename = asset_update.filename
    if asset_update.description is not None:
        asset.description = asset_update.description
    if asset_update.tag_ids is not None:
        unique_tag_ids = list(dict.fromkeys(asset_update.tag_ids))
        tags = db.query(Tag).filter(Tag.id.in_(unique_tag_ids)).all()
        if len(tags) != len(unique_tag_ids):
            raise HTTPException(status_code=422, detail="One or more tag IDs are invalid")
        asset.tags = tags
    if asset_update.status:
        if asset_update.status.value == "deleted":
            raise HTTPException(status_code=422, detail="Use DELETE to remove an asset")
        asset.status = asset_update.status

    db.add(AuditLog(
        asset_id=asset.id,
        user_id=current_user.id,
        action=AuditAction.MODIFIED,
        details="Updated asset metadata"
    ))
    db.commit()
    db.refresh(asset)
    return AssetDetailResponse.from_orm(asset)


@router.delete(
    "/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an asset and its local file",
    responses={404: {"description": "Asset not found"}},
)
def delete_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin"))
):
    """Hard-delete the database asset and its primary local file when present."""
    asset = get_asset_or_404(db, asset_id)
    stored_path = local_storage_path(asset.file_path)

    if stored_path and stored_path.exists():
        try:
            stored_path.unlink()
        except OSError:
            raise HTTPException(status_code=500, detail="Asset file could not be deleted")

    try:
        db.delete(asset)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Asset record could not be deleted")


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
