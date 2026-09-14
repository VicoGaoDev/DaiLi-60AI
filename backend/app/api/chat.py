from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.chat import (
    ChatGenerateActionRequest,
    ChatMessageListOut,
    ChatMessageOut,
    ChatSendMessageRequest,
    ChatSessionCreate,
    ChatSessionListOut,
    ChatSessionOut,
    ChatSessionUpdate,
)
from app.services.chat_generate_service import confirm_or_cancel_chat_generate
from app.services.chat_service import (
    chat_send_uses_sse,
    create_session,
    delete_session,
    get_session,
    iter_prepared_send_message_sse,
    list_messages,
    list_sessions,
    prepare_chat_send,
    replay_send_message_sse,
    send_message,
    update_session,
)

CHAT_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

router = APIRouter(prefix="/api/chat", tags=["AI对话"])


@router.get("/sessions", response_model=ChatSessionListOut)
def get_chat_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_sessions(db, user.id, page=page, page_size=page_size)


@router.post("/sessions", response_model=ChatSessionOut)
def create_chat_session(
    body: ChatSessionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_session(db, user.id, body)


@router.get("/sessions/{session_id}", response_model=ChatSessionOut)
def get_chat_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_session(db, user.id, session_id)


@router.patch("/sessions/{session_id}", response_model=ChatSessionOut)
def patch_chat_session(
    session_id: str,
    body: ChatSessionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_session(db, user.id, session_id, body)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_chat_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_session(db, user.id, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions/{session_id}/messages", response_model=ChatMessageListOut)
def get_chat_messages(
    session_id: str,
    before_id: int | None = Query(default=None, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_messages(db, user.id, session_id, before_id=before_id, page_size=page_size)


@router.post("/sessions/{session_id}/messages")
async def post_chat_message(
    session_id: str,
    body: ChatSendMessageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not chat_send_uses_sse(db, user, session_id, body):
        return send_message(db, user, session_id, body)
    prepared = prepare_chat_send(db, user, session_id, body)
    if prepared.existing:
        return StreamingResponse(
            replay_send_message_sse(prepared.existing),
            media_type="text/event-stream; charset=utf-8",
            headers=CHAT_SSE_HEADERS,
        )
    if (
        prepared.session is None
        or prepared.user_message is None
        or prepared.assistant_message is None
        or prepared.primary_config is None
    ):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="对话准备失败")
    return StreamingResponse(
        iter_prepared_send_message_sse(
            user_id=user.id,
            session_pk=int(prepared.session.id),
            user_message_id=int(prepared.user_message.id),
            assistant_message_id=int(prepared.assistant_message.id),
            model=prepared.model,
            credit_cost=prepared.credit_cost,
            context_messages=prepared.context_messages or [],
            user_content=prepared.user_content,
            system_prompt=getattr(prepared.binding, "system_prompt", "") or "",
            scene_label=getattr(prepared.binding, "scene_label", "") or "",
            primary_config_id=int(prepared.primary_config.id),
            backup_config_id=int(prepared.backup_config.id) if prepared.backup_config else None,
        ),
        media_type="text/event-stream; charset=utf-8",
        headers=CHAT_SSE_HEADERS,
    )


@router.post("/sessions/{session_id}/messages/{message_id}/generate", response_model=ChatMessageOut)
def post_chat_message_generate(
    session_id: str,
    message_id: int,
    body: ChatGenerateActionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return confirm_or_cancel_chat_generate(db, user, session_id, message_id, body)
