from datetime import datetime

from pydantic import BaseModel, Field


class UserPromptCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class UserPromptCategoryUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class UserPromptCategorySummary(BaseModel):
    id: int
    name: str
    sort_order: int = 0
    prompt_count: int = 0
    updated_at: datetime | None = None


class UserPromptCategoryListResponse(BaseModel):
    items: list[UserPromptCategorySummary]
    uncategorized_count: int = 0


class UserPromptSummary(BaseModel):
    id: int
    category_id: int | None = None
    category_name: str = ""
    title: str
    content: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserPromptListResponse(BaseModel):
    items: list[UserPromptSummary]
    total: int = 0


class UserPromptCreateRequest(BaseModel):
    category_id: int | None = None
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1, max_length=10000)


class UserPromptUpdateRequest(BaseModel):
    category_id: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1, max_length=10000)


class UserPromptDeleteResponse(BaseModel):
    ok: bool = True
