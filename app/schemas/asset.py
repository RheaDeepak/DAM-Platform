from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.models.asset import AssetType, AssetStatus
from app.schemas.tag import TagResponse
from app.schemas.user import UserResponse


class AssetMetadataCreate(BaseModel):
    key: str
    value: str


class AssetMetadataResponse(BaseModel):
    id: int
    key: str
    value: str
    created_at: datetime

    class Config:
        from_attributes = True


class AssetVersionResponse(BaseModel):
    id: int
    version_number: int
    file_size: int
    created_at: datetime
    change_description: Optional[str]

    class Config:
        from_attributes = True


class AssetCreate(BaseModel):
    filename: str
    original_filename: str
    asset_type: AssetType
    mime_type: str
    file_size: int
    description: Optional[str] = None
    file_path: str  # temp path or cloud storage path


class AssetUpdate(BaseModel):
    # "filename" is retained for existing clients; "title" is the clearer API name.
    title: Optional[str] = Field(default=None, min_length=1)
    filename: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None
    tag_ids: Optional[List[int]] = None
    status: Optional[AssetStatus] = None


class AssetResponse(BaseModel):
    id: int
    title: str
    filename: str
    original_filename: str
    asset_type: AssetType
    mime_type: str = Field(description="MIME type supplied by the upload or inferred from the filename")
    file_size: int = Field(description="Uploaded file size in bytes")
    file_extension: Optional[str] = Field(
        default=None,
        description="Lowercase file extension without the leading dot",
    )
    checksum: Optional[str] = Field(
        default=None,
        description="SHA-256 checksum of the uploaded file",
    )
    status: AssetStatus
    description: Optional[str]
    file_path: str
    owner_id: int
    owner: UserResponse
    tags: List[TagResponse]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AssetDetailResponse(AssetResponse):
    asset_metadata: List[AssetMetadataResponse]
    versions: List[AssetVersionResponse]


class AssetListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    page: int
    pages: int
    items: List[AssetResponse]
