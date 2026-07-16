from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.models.asset import AssetType, AssetStatus


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
    filename: Optional[str] = None
    description: Optional[str] = None
    status: Optional[AssetStatus] = None


class AssetResponse(BaseModel):
    id: int
    filename: str
    original_filename: str
    asset_type: AssetType
    mime_type: str
    file_size: int
    status: AssetStatus
    description: Optional[str]
    owner_id: int
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
    items: List[AssetResponse]
