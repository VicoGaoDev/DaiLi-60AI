from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class VideoTaskCreate(BaseModel):
    model: str = ""
    source: Literal["web", "app", "api"] = "web"
    generation_mode: str = ""
    prompt: str
    duration_seconds: int = 5
    aspect_ratio: str = ""
    resolution: str = ""
    reference_images: list[str] = Field(default_factory=list)


class VideoTaskCreateResponse(BaseModel):
    task_id: str


class VideoResultOut(BaseModel):
    id: int
    video_url: str
    cover_url: str = ""
    video_format: str = ""
    video_size_bytes: int = 0
    duration_seconds: int | None = None
    status: str
    error_message: str = ""


class VideoTaskApiAttemptOut(BaseModel):
    id: int | None = None
    api_config_id: int | None = None
    api_config_name: str
    attempt_index: int
    is_fallback: bool
    status: str
    http_status: int | None = None
    error_message: str = ""
    duration_ms: int | None = None
    created_at: datetime | None = None


class VideoTaskOut(BaseModel):
    id: str
    model: str
    source: Literal["web", "app", "api"] = "web"
    generation_mode: Literal["text_to_video", "image_to_video", "first_last_frame"] = "text_to_video"
    prompt: str
    duration_seconds: int
    aspect_ratio: str = ""
    resolution: str
    reference_images: list[str] = Field(default_factory=list)
    credit_cost: int = 0
    credit_refunded: bool = False
    failure_refund_remaining_count: int | None = None
    used_fallback_api: bool = False
    task_is_deleted: bool = False
    status: str
    error_message: str = ""
    created_at: datetime | None = None
    enqueued_at: datetime | None = None
    request_started_at: datetime | None = None
    request_finished_at: datetime | None = None
    videos: list[VideoResultOut] = []
    api_attempts: list[VideoTaskApiAttemptOut] = []


class AdminVideoTaskOut(VideoTaskOut):
    user_id: str
    username: str = ""
    avatar_url: str = ""


class AdminVideoTaskListOut(BaseModel):
    total: int
    items: list[AdminVideoTaskOut]
