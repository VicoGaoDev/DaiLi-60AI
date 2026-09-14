from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


UpdateLogTagType = Literal["notice", "feature", "optimization", "bugfix", "other"]


class UpdateLogBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=10000)
    tag_type: UpdateLogTagType
    effective_at: datetime | None = None


class UpdateLogCreateRequest(UpdateLogBase):
    pass


class UpdateLogUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=10000)
    tag_type: UpdateLogTagType
    effective_at: datetime | None = None


class UpdateLogOut(BaseModel):
    log_id: str
    title: str
    content: str
    tag_type: UpdateLogTagType
    effective_at: datetime
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UpdateLogListResponse(BaseModel):
    total: int
    items: list[UpdateLogOut]
