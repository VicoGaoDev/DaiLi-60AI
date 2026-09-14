from datetime import datetime
from pydantic import BaseModel

from app.schemas.task import ImageOut


class FeedbackTaskSummary(BaseModel):
    task_id: str = ""
    model: str = ""
    mode: str = "generate"
    task_type: str = "text_generate"
    source: str = "web"
    prompt: str = ""
    status: str = ""
    created_at: datetime | None = None
    reference_images: list[str] = []
    reference_image_thumbs: list[str] = []
    images: list[ImageOut] = []


class FeedbackListItem(BaseModel):
    feedback_id: str
    user_id: str
    username: str = ""
    task_id: str = ""
    status: str
    is_read: bool = False
    content: str
    process_note: str = ""
    result_note: str = ""
    handler_id: str | None = None
    handler_name: str = ""
    handled_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    task: FeedbackTaskSummary


class FeedbackDetail(FeedbackListItem):
    task_user_id: str = ""


class FeedbackListResponse(BaseModel):
    total: int
    items: list[FeedbackListItem]


class FeedbackUnresolvedCountResponse(BaseModel):
    count: int


class FeedbackReadCountResponse(BaseModel):
    count: int


class FeedbackCreateRequest(BaseModel):
    task_id: str | None = None
    content: str


class FeedbackUpdateRequest(BaseModel):
    status: str | None = None
    process_note: str | None = None
    result_note: str | None = None
