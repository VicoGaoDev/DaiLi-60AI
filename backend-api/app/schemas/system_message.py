from datetime import datetime
from pydantic import BaseModel, Field


class SystemMessageSender(BaseModel):
    user_id: str
    username: str = ""


class SystemMessageRecipientOut(BaseModel):
    user_id: str
    username: str = ""
    email: str | None = None
    is_read: bool = False
    read_at: datetime | None = None


class SystemMessageListItem(BaseModel):
    message_id: str
    subject: str
    content_text: str = ""
    sender: SystemMessageSender
    recipient_scope: str
    recipient_count: int = 0
    is_read: bool = False
    read_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SystemMessageDetail(SystemMessageListItem):
    content_html: str = ""
    recipients: list[SystemMessageRecipientOut] = []


class SystemMessageListResponse(BaseModel):
    total: int
    items: list[SystemMessageListItem]


class SystemMessageReadCountResponse(BaseModel):
    count: int


class SystemMessageCreateRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200)
    content_html: str = Field(..., min_length=1)
    recipient_scope: str = Field("selected", pattern="^(selected|all)$")
    recipient_user_ids: list[str] = []
