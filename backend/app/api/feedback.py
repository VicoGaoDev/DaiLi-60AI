from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.feedback import (
    FeedbackCreateRequest,
    FeedbackDetail,
    FeedbackListResponse,
    FeedbackMessageCreateRequest,
    FeedbackMessageListResponse,
    FeedbackMessageOut,
    FeedbackReadCountResponse,
)
from app.services.feedback_service import (
    count_user_unread_feedbacks,
    create_feedback,
    create_feedback_message,
    get_feedback_detail,
    list_feedback_messages,
    list_feedbacks,
    mark_all_feedbacks_as_read,
    mark_feedback_as_read,
)

router = APIRouter(prefix="/api/feedback", tags=["反馈"])


@router.post("", response_model=FeedbackDetail)
def create_feedback_item(
    body: FeedbackCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_feedback(
        db,
        user,
        body.task_id,
        body.content,
        body.feedback_type,
        body.attachments,
    )


@router.get("", response_model=FeedbackListResponse)
def list_my_feedback(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    task_id: str | None = Query(None),
    status: str | None = Query(None, pattern="^(pending|processing|completed)$"),
    feedback_type: str | None = Query(
        None,
        pattern="^(general|image_task|video_task|canvas|purchase|feature_request|bug_report|optimization)$",
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_feedbacks(
        db,
        user_id=user.id,
        task_id=task_id,
        status_filter=status,
        feedback_type_filter=feedback_type,
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count", response_model=FeedbackReadCountResponse)
def get_my_unread_feedback_count(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"count": count_user_unread_feedbacks(db, user_id=user.id)}


@router.get("/completed-unread-count", response_model=FeedbackReadCountResponse)
def get_my_completed_unread_feedback_count(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"count": count_user_unread_feedbacks(db, user_id=user.id)}


@router.patch("/{feedback_id}/read", response_model=FeedbackDetail)
def mark_my_feedback_read(
    feedback_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return mark_feedback_as_read(db, feedback_id, user_id=user.id)


@router.post("/read-all", response_model=FeedbackReadCountResponse)
def mark_my_feedbacks_read_all(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"count": mark_all_feedbacks_as_read(db, user_id=user.id)}


@router.get("/{feedback_id}/messages", response_model=FeedbackMessageListResponse)
def list_my_feedback_messages(
    feedback_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_feedback_messages(db, feedback_id, user_id=user.id)


@router.post("/{feedback_id}/messages", response_model=FeedbackMessageOut)
def send_my_feedback_message(
    feedback_id: str,
    body: FeedbackMessageCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_feedback_message(
        db,
        feedback_id,
        sender=user,
        sender_role="user",
        content=body.content,
        attachments=body.attachments,
        user_id=user.id,
    )


@router.get("/{feedback_id}", response_model=FeedbackDetail)
def get_my_feedback_detail(
    feedback_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_feedback_detail(db, feedback_id, user_id=user.id)
