from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.system_message import (
    SystemMessageCreateRequest,
    SystemMessageDetail,
    SystemMessageListResponse,
    SystemMessageReadCountResponse,
)
from app.services.system_message_service import (
    count_my_unread_system_messages,
    create_system_message,
    get_admin_system_message_detail,
    get_my_system_message_detail,
    list_admin_system_messages,
    list_my_system_messages,
    mark_all_my_system_messages_as_read,
)

router = APIRouter(prefix="/api/system-messages", tags=["系统消息"])
admin_router = APIRouter(prefix="/api/admin/system-messages", tags=["管理员系统消息"])


@router.get("", response_model=SystemMessageListResponse)
def list_my_messages(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_my_system_messages(db, user_id=user.id, page=page, page_size=page_size)


@router.get("/unread-count", response_model=SystemMessageReadCountResponse)
def get_my_unread_message_count(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"count": count_my_unread_system_messages(db, user_id=user.id)}


@router.post("/read-all", response_model=SystemMessageReadCountResponse)
def mark_my_messages_read_all(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"count": mark_all_my_system_messages_as_read(db, user_id=user.id)}


@router.get("/{message_id}", response_model=SystemMessageDetail)
def get_my_message_detail(
    message_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_my_system_message_detail(db, message_id, user_id=user.id)


@admin_router.post("", response_model=SystemMessageDetail)
def admin_create_message(
    body: SystemMessageCreateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return create_system_message(
        db,
        admin=admin,
        subject=body.subject,
        content_html=body.content_html,
        recipient_scope=body.recipient_scope,
        recipient_user_ids=body.recipient_user_ids,
    )


@admin_router.get("", response_model=SystemMessageListResponse)
def admin_list_messages(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_admin_system_messages(db, page=page, page_size=page_size)


@admin_router.get("/{message_id}", response_model=SystemMessageDetail)
def admin_get_message_detail(
    message_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_admin_system_message_detail(db, message_id)
