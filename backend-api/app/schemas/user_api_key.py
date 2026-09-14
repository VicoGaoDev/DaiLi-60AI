from datetime import datetime

from pydantic import BaseModel, Field


class UserApiKeyOut(BaseModel):
    id: int
    subs_type: str = ""
    expire_time: datetime | None = None
    api_key: str
    key_name: str = ""
    status: str = "enabled"
    is_delete: bool = False
    key_prefix: str = ""
    key_last4: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class UserApiKeyListResponse(BaseModel):
    items: list[UserApiKeyOut]


class UserApiKeyCreateRequest(BaseModel):
    key_name: str = Field(default="", max_length=100)
    expire_time: datetime | None = None


class UserApiKeyUpdateRequest(BaseModel):
    key_name: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, pattern="^(enabled|disabled)$")
    expire_time: datetime | None = None


class UserApiKeyResetResponse(BaseModel):
    item: UserApiKeyOut
