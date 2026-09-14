from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any


class HistoryImageOut(BaseModel):
    id: int
    image_url: str
    preview_url: str = ""
    thumb_url: str = ""
    status: str
    error_message: str = ""
    image_format: str = ""
    image_size_bytes: int = 0
    is_deleted: bool = False

    model_config = {"from_attributes": True}


class TaskApiRequestPreviewOut(BaseModel):
    request_url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    payload: Any = None


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
    response_preview: str = ""
    created_at: datetime | None = None
    request_preview: TaskApiRequestPreviewOut | None = None


class HistoryItem(BaseModel):
    item_type: str = "task"
    task_id: str | None = None
    canvas_id: int | None = None
    canvas_project_id: str = ""
    history_id: int | None = None
    style_id: int | None = None
    style_name: str = ""
    display_id: str = ""
    user_id: str = ""
    username: str = ""
    avatar_url: str = ""
    task_type: str = "text_generate"
    model: str = ""
    source: str = "web"
    mode: str = "generate"
    prompt: str = ""
    reference_images: list[str] = []
    num_images: int = 1
    size: str
    resolution: str = ""
    custom_size: str = ""
    credit_cost: int = 0
    credit_refunded: bool = False
    used_fallback_api: bool = False
    status: str
    error_message: str = ""
    provider_error_message: str = ""
    task_is_deleted: bool = False
    is_soft_deleted: bool = False
    soft_deleted_count: int = 0
    created_at: datetime | None = None
    images: list[HistoryImageOut] = []
    api_attempts: list[TaskApiAttemptOut] = []


class HistoryResponse(BaseModel):
    total: int
    total_credit_cost: int = 0
    items: list[HistoryItem]


class UserHistoryCardItem(BaseModel):
    history_id: int | None = None
    item_type: str = "task"
    style_id: int | None = None
    style_name: str = ""
    display_id: str = ""
    task_id: str | None = None
    canvas_id: int | None = None
    canvas_project_id: str = ""
    image_id: int | None = None
    user_id: str = ""
    username: str = ""
    avatar_url: str = ""
    is_pinned: bool = False
    pinned_at: datetime | None = None
    image_url: str = ""
    preview_url: str = ""
    thumb_url: str = ""
    status: str
    image_format: str = ""
    image_size_bytes: int = 0
    task_is_deleted: bool = False
    is_soft_deleted: bool = False
    task_type: str = "text_generate"
    model: str = ""
    source: str = "web"
    mode: str = "generate"
    prompt: str = ""
    reference_images: list[str] = []
    reference_image_thumbs: list[str] = []
    source_image: str = ""
    source_image_thumb: str = ""
    mask_image: str = ""
    mask_image_thumb: str = ""
    num_images: int = 1
    size: str
    resolution: str = ""
    custom_size: str = ""
    credit_cost: int = 0
    credit_refunded: bool = False
    used_fallback_api: bool = False
    created_at: datetime | None = None
    request_started_at: datetime | None = None
    request_finished_at: datetime | None = None
    run_time: int | None = None
    error_message: str = ""
    provider_error_message: str = ""
    images: list[HistoryImageOut] = []
    api_attempts: list[TaskApiAttemptOut] = []


class UserHistoryResponse(BaseModel):
    total: int
    items: list[UserHistoryCardItem]


class HistoryPinToggleRequest(BaseModel):
    item_type: str
    image_id: int | None = None
    history_id: int | None = None


class HistoryPinToggleResponse(BaseModel):
    is_pinned: bool
    pinned_at: datetime | None = None
