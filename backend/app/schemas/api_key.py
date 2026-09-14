from pydantic import BaseModel
from datetime import datetime


class AdminConfigOut(BaseModel):
    id: int
    contact_qr_image: str = ""
    announcement_enabled: bool = False
    announcement_content: str = ""
    announcement_updated_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class AdminConfigUpdate(BaseModel):
    contact_qr_image: str = ""
    announcement_enabled: bool = False
    announcement_content: str = ""


class ExternalApiSecretConfigOut(BaseModel):
    id: int
    key: str = ""
    tongyi_key: str = ""
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ExternalApiSecretConfigUpdate(BaseModel):
    key: str = ""
    tongyi_key: str = ""


class AnnouncementConfigOut(BaseModel):
    announcement_enabled: bool = False
    announcement_content: str = ""
    announcement_updated_at: datetime | None = None


class CosConfigOut(BaseModel):
    id: int
    cos_secret_id: str = ""
    cos_secret_key: str = ""
    cos_bucket: str = ""
    cos_region: str = ""
    cos_upload_domain: str = ""
    cos_public_base_url: str = ""
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class CosConfigUpdate(BaseModel):
    cos_secret_id: str = ""
    cos_secret_key: str = ""
    cos_bucket: str = ""
    cos_region: str = ""
    cos_upload_domain: str = ""
    cos_public_base_url: str = ""
