from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


StatusType = Literal["enabled", "disabled"]


class PromptOptimizeStyleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=255)
    style_prompt: str = Field(..., min_length=1, max_length=10000)
    sort_order: int = Field(default=100, ge=0, le=999999)
    status: StatusType = "enabled"
    is_default: bool = False

    @field_validator("name", "description", "style_prompt")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return (value or "").strip()


class PromptOptimizeStyleCreate(PromptOptimizeStyleBase):
    pass


class PromptOptimizeStyleUpdate(PromptOptimizeStyleBase):
    pass


class PromptOptimizeStyleStatusUpdate(BaseModel):
    status: StatusType


class PromptOptimizeStyleOut(BaseModel):
    id: int
    name: str
    description: str = ""
    style_prompt: str
    sort_order: int
    status: StatusType
    is_default: bool
    is_deleted: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    usage_count: int = 0


class PublicPromptOptimizeStyleOut(BaseModel):
    id: int
    name: str
    description: str = ""
    style_prompt: str
    is_default: bool = False
    sort_order: int = 100
