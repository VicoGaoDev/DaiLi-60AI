from pydantic import BaseModel
from datetime import datetime


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


class HistoryItem(BaseModel):
    item_type: str = "task"
    task_id: str | None = None
    history_id: int | None = None
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
    status: str
    error_message: str = ""
    task_is_deleted: bool = False
    is_soft_deleted: bool = False
    soft_deleted_count: int = 0
    created_at: datetime | None = None
    images: list[HistoryImageOut] = []


class HistoryResponse(BaseModel):
    total: int
    total_credit_cost: int = 0
    items: list[HistoryItem]


class UserHistoryCardItem(BaseModel):
    history_id: int | None = None
    item_type: str = "task"
    display_id: str = ""
    task_id: str | None = None
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
    created_at: datetime | None = None
    request_started_at: datetime | None = None
    request_finished_at: datetime | None = None
    run_time: int | None = None
    error_message: str = ""
    images: list[HistoryImageOut] = []


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
