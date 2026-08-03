from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import Base, engine, SessionLocal
from app.models import (
    User,
    Asset,
    AssetVersion,
    AssetMetadata,
    Tag,
    Role,
    Permission,
    AuditLog,
)
from app.models.role import PermissionType
from app.api import auth, assets, tags, roles, users, audit

# Initialize database
Base.metadata.create_all(bind=engine)


def ensure_asset_metadata_columns() -> None:
    """Upgrade existing development databases with newly added asset metadata columns."""
    with engine.begin() as connection:
        connection.execute(text(
            "ALTER TABLE assets ADD COLUMN IF NOT EXISTS file_extension VARCHAR"
        ))
        connection.execute(text(
            "ALTER TABLE assets ADD COLUMN IF NOT EXISTS checksum VARCHAR(64)"
        ))


ensure_asset_metadata_columns()

# Create FastAPI app
app = FastAPI(
    title="DAM Platform API",
    description="Digital Asset Management Platform API",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(assets.router)
app.include_router(tags.router)
app.include_router(roles.router)
app.include_router(users.router)
app.include_router(audit.router)


@app.get("/")
def home():
    """Health check endpoint"""
    return {
        "message": "DAM Platform API Running",
        "version": "1.0.0",
        "status": "operational"
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


def seed_default_roles(db: Session) -> None:
    """Create or update the built-in roles and their existing permissions."""
    permissions_map = {}
    for permission_type in PermissionType:
        permission = db.query(Permission).filter(
            Permission.permission_type == permission_type
        ).first()
        if not permission:
            permission = Permission(
                permission_type=permission_type,
                description=f"{permission_type.value} permission",
            )
            db.add(permission)
            db.flush()
        permissions_map[permission_type] = permission

    default_roles = {
        "admin": (
            "Administrator with full access",
            list(PermissionType),
        ),
        "editor": (
            "Editor can upload and modify assets",
            [
                PermissionType.VIEW,
                PermissionType.EDIT,
                PermissionType.UPLOAD,
                PermissionType.DOWNLOAD,
            ],
        ),
        "viewer": (
            "Viewer can only view and download assets",
            [PermissionType.VIEW, PermissionType.DOWNLOAD],
        ),
    }

    for role_name, (description, permission_types) in default_roles.items():
        role = db.query(Role).filter(Role.name == role_name).first()
        if not role:
            role = Role(name=role_name)
            db.add(role)
        role.description = description
        role.permissions = [permissions_map[item] for item in permission_types]

    db.commit()


@app.on_event("startup")
async def startup_event():
    """Initialize the built-in RBAC roles and permissions on startup."""
    db = SessionLocal()
    try:
        seed_default_roles(db)
    finally:
        db.close()
