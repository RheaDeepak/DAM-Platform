from fastapi import APIRouter, HTTPException, Depends, status, Query
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Role, Permission, User
from app.schemas.role import RoleCreate, RoleUpdate, RoleResponse, RoleDetailResponse
from app.api.auth import require_roles

router = APIRouter(prefix="/roles", tags=["roles"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(
    role: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin"))
):
    """Create a new role"""
    existing_role = db.query(Role).filter(Role.name == role.name).first()
    if existing_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role already exists"
        )
    
    new_role = Role(name=role.name, description=role.description)
    
    if role.permission_ids:
        permissions = db.query(Permission).filter(Permission.id.in_(role.permission_ids)).all()
        new_role.permissions = permissions
    
    db.add(new_role)
    db.commit()
    db.refresh(new_role)
    
    return RoleResponse.from_orm(new_role)


@router.get("/", response_model=list)
def list_roles(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin"))
):
    """List all roles"""
    roles = db.query(Role).offset(skip).limit(limit).all()
    return [RoleResponse.from_orm(role) for role in roles]


@router.get("/{role_id}", response_model=RoleDetailResponse)
def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin"))
):
    """Get role details with permissions"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    return RoleDetailResponse.from_orm(role)


@router.patch("/{role_id}", response_model=RoleDetailResponse)
def update_role(
    role_id: int,
    role_update: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin"))
):
    """Update role details"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    if role_update.name:
        existing = db.query(Role).filter(Role.name == role_update.name).first()
        if existing and existing.id != role_id:
            raise HTTPException(status_code=400, detail="Role name already exists")
        role.name = role_update.name
    
    if role_update.description is not None:
        role.description = role_update.description
    
    if role_update.permission_ids is not None:
        permissions = db.query(Permission).filter(Permission.id.in_(role_update.permission_ids)).all()
        role.permissions = permissions
    
    db.commit()
    db.refresh(role)
    
    return RoleDetailResponse.from_orm(role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin"))
):
    """Delete a role"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    db.delete(role)
    db.commit()
