from typing import Literal
from pydantic import BaseModel, Field
from datetime import datetime


class TaskCreate(BaseModel):
    mode: str = "generate"
    model: str = ""
    source: Literal["web", "app", "api"] = "api"
    prompt: str
    size: str = "3:4"
    resolution: str = "4K"
    custom_size: str = ""
    reference_images: list[str] | None = None
    source_image: str = ""
    mask_image: str = ""
    board_id: int | None = None


class TaskCreateResponse(BaseModel):
    task_id: str | None = None
    task_ids: list[str] = Field(default_factory=list)


class ImageOut(BaseModel):
    id: int
    image_url: str
    preview_url: str = ""
    thumb_url: str = ""
    status: str
    error_message: str = ""
    image_format: str = ""
    image_size_bytes: int = 0

    model_config = {"from_attributes": True}


class TaskOut(BaseModel):
    id: str
    mode: str = "generate"
    model: str = ""
    source: Literal["web", "app", "api"] = "web"
    prompt: str = ""
    size: str
    resolution: str = ""
    credit_cost: int = 0
    credit_refunded: bool = False
    status: str
    error_message: str = ""
    created_at: datetime | None = None
    enqueued_at: datetime | None = None
    request_started_at: datetime | None = None
    request_finished_at: datetime | None = None
    images: list[ImageOut] = []

    model_config = {"from_attributes": True}
