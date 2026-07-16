from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum, BigInteger, Table
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database import Base


# Association table for many-to-many relationship between assets and tags
asset_tags = Table(
    "asset_tags",
    Base.metadata,
    Column("asset_id", Integer, ForeignKey("assets.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
)


class AssetType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    AUDIO = "audio"
    OTHER = "other"


class AssetStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    original_filename = Column(String)
    asset_type = Column(Enum(AssetType), index=True)
    file_path = Column(String, unique=True, index=True)
    file_size = Column(BigInteger)  # in bytes
    mime_type = Column(String)
    status = Column(Enum(AssetStatus), default=AssetStatus.ACTIVE, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner = relationship("User", back_populates="assets")
    versions = relationship("AssetVersion", back_populates="asset", cascade="all, delete-orphan")
    asset_metadata = relationship("AssetMetadata", back_populates="asset", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary="asset_tags", back_populates="assets")
    audit_logs = relationship("AuditLog", back_populates="asset", cascade="all, delete-orphan")


class AssetVersion(Base):
    __tablename__ = "asset_versions"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), index=True)
    version_number = Column(Integer, index=True)
    file_path = Column(String)
    file_size = Column(BigInteger)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    created_by_id = Column(Integer, ForeignKey("users.id"))
    change_description = Column(Text, nullable=True)

    # Relationships
    asset = relationship("Asset", back_populates="versions")
    created_by = relationship("User", foreign_keys=[created_by_id])


class AssetMetadata(Base):
    __tablename__ = "asset_metadata"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), index=True)
    key = Column(String, index=True)
    value = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    asset = relationship("Asset", back_populates="metadata")
