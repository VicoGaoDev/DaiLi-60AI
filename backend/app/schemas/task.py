from typing import Literal
from pydantic import BaseModel, Field
from datetime import datetime


class TaskCreate(BaseModel):
    mode: str = "generate"
    model: str = ""
    source: Literal["web", "app", "api"] = "web"
    prompt: str
    num_images: int = Field(default=4, ge=1, le=8)
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


class TaskApiAttemptOut(BaseModel):
    id: int | None = None
    image_id: int | None = None
    image_index: int | None = None
    api_config_id: int | None = None
    api_config_name: str = ""
    attempt_index: int = 1
    is_fallback: bool = False
    status: str = "failed"
    http_status: int | None = None
    error_message: str = ""
    duration_ms: int | None = None
    external_http_ms: int | None = None
    result_download_ms: int | None = None
    cos_upload_ms: int | None = None
    created_at: datetime | None = None
    request_preview: dict | None = None


class TaskOut(BaseModel):
    id: str
    canvas_id: int | None = None
    mode: str = "generate"
    model: str = ""
    source: Literal["web", "app", "api"] = "web"
    prompt: str = ""
    num_images: int = 4
    size: str
    resolution: str = ""
    custom_size: str = ""
    reference_images: list[str] = []
    reference_image_thumbs: list[str] = []
    source_image: str = ""
    source_image_thumb: str = ""
    mask_image: str = ""
    mask_image_thumb: str = ""
    credit_cost: int = 0
    credit_refunded: bool = False
    failure_refund_remaining_count: int | None = None
    used_fallback_api: bool = False
    status: str
    error_message: str = ""
    provider_error_message: str = ""
    created_at: datetime | None = None
    enqueued_at: datetime | None = None
    request_started_at: datetime | None = None
    request_finished_at: datetime | None = None
    images: list[ImageOut] = []
    api_attempts: list[TaskApiAttemptOut] = []

    model_config = {"from_attributes": True}
