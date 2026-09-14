from datetime import datetime
from pydantic import BaseModel, Field

from app.schemas.task import ImageOut


class FeedbackTaskSummary(BaseModel):
    task_id: str = ""
    model: str = ""
    mode: str = "generate"
    task_type: str = "text_generate"
    source: str = "web"
    prompt: str = ""
    status: str = ""
    error_message: str = ""
    credit_refunded: bool = False
    created_at: datetime | None = None
    reference_images: list[str] = []
    reference_image_thumbs: list[str] = []
    images: list[ImageOut] = []


class FeedbackListItem(BaseModel):
    feedback_id: str
    user_id: str
    username: str = ""
    task_id: str = ""
    feedback_type: str = "general"
    attachments: list[str] = []
    status: str
    is_read: bool = False
    content: str
    process_note: str = ""
    result_note: str = ""
    handler_id: str | None = None
    handler_name: str = ""
    handled_at: datetime | None = None
    last_message_at: datetime | None = None
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


class FeedbackMessageOut(BaseModel):
    message_id: str
    feedback_id: str
    sender_role: str
    sender_id: str | None = None
    sender_name: str = ""
    content: str = ""
    attachments: list[str] = []
    created_at: datetime | None = None


class FeedbackMessageListResponse(BaseModel):
    items: list[FeedbackMessageOut]


class FeedbackMessageCreateRequest(BaseModel):
    content: str = ""
    attachments: list[str] = Field(default_factory=list)


class FeedbackCreateRequest(BaseModel):
    task_id: str | None = None
    feedback_type: str | None = None
    attachments: list[str] = Field(default_factory=list)
    content: str


class FeedbackUpdateRequest(BaseModel):
    status: str | None = None
    process_note: str | None = None
    result_note: str | None = None
