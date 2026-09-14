from datetime import datetime

from pydantic import BaseModel, Field


class UserAssetCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class UserAssetCategoryUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class UserAssetCategorySummary(BaseModel):
    id: int
    name: str
    sort_order: int = 0
    asset_count: int = 0
    preview_urls: list[str] = []
    updated_at: datetime | None = None


class UserAssetCategoryListResponse(BaseModel):
    items: list[UserAssetCategorySummary]
    uncategorized_count: int = 0


class UserAssetQuota(BaseModel):
    used: int = 0
    limit: int = 100
    remaining: int = 100


class UserAssetSummary(BaseModel):
    id: int
    category_id: int | None = None
    category_name: str = ""
    file_name: str
    image_url: str = ""
    thumb_url: str = ""
    mime_type: str = ""
    file_size: int = 0
    width: int | None = None
    height: int | None = None
    status: str = "pending"
    created_at: datetime | None = None
    completed_at: datetime | None = None


class UserAssetListResponse(BaseModel):
    items: list[UserAssetSummary]
    total: int = 0
    quota: UserAssetQuota


class UserAssetUploadSessionRequest(BaseModel):
    file_name: str
    file_size: int
    content_type: str
    category_id: int | None = None


class UploadCredentialPayload(BaseModel):
    bucket: str
    region: str
    key: str
    upload_domain: str
    url: str
    tmp_secret_id: str
    tmp_secret_key: str
    session_token: str
    start_time: int | None = None
    expired_time: int


class UserAssetUploadSessionResponse(BaseModel):
    asset: UserAssetSummary
    quota: UserAssetQuota
    credential: UploadCredentialPayload


class UserAssetImportResponse(BaseModel):
    asset: UserAssetSummary
    quota: UserAssetQuota


class UserAssetCompleteRequest(BaseModel):
    width: int | None = None
    height: int | None = None


class UserAssetImportRequest(BaseModel):
    image_url: str
    file_name: str = Field(..., min_length=1, max_length=255)
    category_id: int | None = None
    width: int | None = None
    height: int | None = None


class UserAssetUpdateRequest(BaseModel):
    category_id: int | None = None
    file_name: str | None = Field(default=None, min_length=1, max_length=255)


class UserAssetDeleteResponse(BaseModel):
    quota: UserAssetQuota
