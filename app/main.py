from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
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
from app.api import auth, assets, tags, roles, users, audit

# Initialize database
Base.metadata.create_all(bind=engine)

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


@app.on_event("startup")
async def startup_event():
    """Initialize default roles and permissions on startup"""
    db = SessionLocal()
    try:
        # Check if roles already exist
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        if not admin_role:
            # Create default permissions
            from app.models.role import PermissionType
            
            permissions_map = {}
            for perm_type in PermissionType:
                existing = db.query(Permission).filter(
                    Permission.permission_type == perm_type
                ).first()
                if not existing:
                    perm = Permission(
                        permission_type=perm_type,
                        description=f"{perm_type.value} permission"
                    )
                    db.add(perm)
                    db.flush()
                    permissions_map[perm_type] = perm
                else:
                    permissions_map[perm_type] = existing
            
            # Create default roles
            admin_role = Role(name="admin", description="Administrator with full access")
            admin_role.permissions = list(permissions_map.values())
            
            editor_role = Role(name="editor", description="Editor can upload and modify assets")
            editor_role.permissions = [
                permissions_map[PermissionType.VIEW],
                permissions_map[PermissionType.EDIT],
                permissions_map[PermissionType.UPLOAD],
                permissions_map[PermissionType.DOWNLOAD],
            ]
            
            viewer_role = Role(name="viewer", description="Viewer can only view and download assets")
            viewer_role.permissions = [
                permissions_map[PermissionType.VIEW],
                permissions_map[PermissionType.DOWNLOAD],
            ]
            
            db.add(admin_role)
            db.add(editor_role)
            db.add(viewer_role)
            db.commit()
    finally:
        db.close()