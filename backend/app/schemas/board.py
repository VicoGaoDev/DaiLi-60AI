from datetime import datetime

from pydantic import BaseModel, Field


class BoardCreate(BaseModel):
    name: str = Field(default="新看板", max_length=100)


class BoardUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class BoardSummary(BaseModel):
    id: int | None = None
    name: str
    is_default: bool = False
    asset_count: int = 0
    updated_at: datetime | None = None
    preview_urls: list[str] = []


class BoardListResponse(BaseModel):
    items: list[BoardSummary]
