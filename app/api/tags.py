from fastapi import APIRouter, HTTPException, Depends, status, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import SessionLocal
from app.models import Tag, Asset
from app.schemas.tag import TagCreate, TagResponse, TagWithAssetsResponse
from app.api.auth import require_roles
from app.models.user import User

router = APIRouter(prefix="/tags", tags=["tags"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
def create_tag(
    tag: TagCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "editor"))
):
    """Create a new tag"""
    existing_tag = db.query(Tag).filter(Tag.name == tag.name).first()
    if existing_tag:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tag already exists"
        )
    
    new_tag = Tag(name=tag.name, description=tag.description)
    db.add(new_tag)
    db.commit()
    db.refresh(new_tag)
    
    return TagResponse.from_orm(new_tag)


@router.get("/", response_model=list)
def list_tags(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "editor", "viewer"))
):
    """List all tags with asset counts"""
    tags = db.query(Tag).offset(skip).limit(limit).all()
    result = []
    
    for tag in tags:
        asset_count = len(tag.assets)
        result.append({
            "id": tag.id,
            "name": tag.name,
            "description": tag.description,
            "created_at": tag.created_at,
            "asset_count": asset_count
        })
    
    return result


@router.get("/{tag_id}", response_model=TagWithAssetsResponse)
def get_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "editor", "viewer"))
):
    """Get tag details with asset count"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    return {
        "id": tag.id,
        "name": tag.name,
        "description": tag.description,
        "created_at": tag.created_at,
        "asset_count": len(tag.assets)
    }


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "editor"))
):
    """Delete a tag"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    db.delete(tag)
    db.commit()
