from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.canvas import CanvasSummary


ExampleCanvasStatus = Literal["draft", "published", "disabled"]


class ExampleCanvasProjectBase(BaseModel):
    title: str = Field(default="", max_length=100)
    subtitle: str = Field(default="", max_length=255)
    cover_url: str = Field(default="", max_length=1000)
    sort_order: int = 0
    status: ExampleCanvasStatus = "draft"


class ExampleCanvasProjectCreate(ExampleCanvasProjectBase):
    project_id: str = Field(min_length=16, max_length=16)


class ExampleCanvasProjectUpdate(BaseModel):
    project_id: str | None = Field(default=None, min_length=16, max_length=16)
    title: str | None = Field(default=None, max_length=100)
    subtitle: str | None = Field(default=None, max_length=255)
    cover_url: str | None = Field(default=None, max_length=1000)
    sort_order: int | None = None
    status: ExampleCanvasStatus | None = None
    refresh_snapshot: bool = False


class ExampleCanvasProjectOut(BaseModel):
    id: int
    source_canvas_id: int
    source_project_id: str
    source_canvas_name: str = ""
    title: str
    subtitle: str
    cover_url: str
    status: ExampleCanvasStatus
    sort_order: int
    preview_urls: list[str] = []
    created_by: str = ""
    updated_by: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ExampleCanvasProjectListResponse(BaseModel):
    items: list[ExampleCanvasProjectOut]


class ExampleCanvasCopyResponse(BaseModel):
    canvas: CanvasSummary
