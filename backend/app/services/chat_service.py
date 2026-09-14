from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import string
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.utils.datetime_utils import now_local
from app.models.chat_external_api_config import ChatExternalApiConfig
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.user import User
from app.schemas.chat import (
    ChatImagePart,
    ChatMessageListOut,
    ChatMessageOut,
    ChatSendMessageRequest,
    ChatSendMessageResponse,
    ChatSessionAdminListOut,
    ChatSessionAdminOut,
    ChatSessionCreate,
    ChatSessionListOut,
    ChatSessionOut,
    ChatSessionUpdate,
)
from app.services.business_id_service import user_external_id
from app.services.chat_external_api_config_service import (
    get_chat_scene_credit_cost,
    list_chat_generation_models,
    payload_json_wants_stream,
    resolve_chat_scene_configs,
)
from app.services.external_api_config_service import (
    build_external_request_kwargs,
    build_secret_variables,
    parse_http_statuses_json,
    read_value_by_path,
    render_config,
)
from app.services.image_delivery_service import build_webp_url, get_optional_cos_config, resolve_user_avatar_url
from app.services.chat_generate_service import (
    GENERATE_IMAGE_SYSTEM_HINT,
    apply_generate_proposal,
    parse_generate_extra,
    reconcile_running_chat_generates,
)
from app.services.user_credit_service import change_user_credit_balance, get_user_credit_balance


logger = logging.getLogger(__name__)
CHAT_CREDIT_LOG_DESCRIPTION = "AI对话"
MAX_PROVIDER_RESPONSE_PREVIEW_LENGTH = 2000
DEFAULT_SESSION_PAGE_SIZE = 50
DEFAULT_MESSAGE_PAGE_SIZE = 50
SYNTHETIC_STREAM_DELAY_SECONDS = 0.001
PUBLIC_SESSION_ID_RE = re.compile(r"^[0-9]{12}[a-z0-9]{4}$")
_SESSION_ID_RANDOM_ALPHABET = string.ascii_lowercase + string.digits
ADMIN_VIEWER_EXCLUDED_ROLES = ("admin", "superadmin")


def _is_credit_exempt_user(user: User | None) -> bool:
    return bool(user and user.role == "superadmin")


def _extract_text_value(payload: object, field_path: str) -> str:
    raw_value, _parent = read_value_by_path(payload, field_path or "")
    return str(raw_value or "").strip()


def _normalize_public_session_id(session_id: str) -> str:
    cleaned = (session_id or "").strip().lower()
    if not PUBLIC_SESSION_ID_RE.fullmatch(cleaned):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return cleaned


def generate_chat_session_id(now: datetime | None = None) -> str:
    """16 位：yymmddhhmmss + 4 位随机小写字母/数字。"""
    stamp = (now or datetime.now()).strftime("%y%m%d%H%M%S")
    suffix = "".join(secrets.choice(_SESSION_ID_RANDOM_ALPHABET) for _ in range(4))
    return f"{stamp}{suffix}"


def _allocate_session_id(db: Session, *, now: datetime | None = None) -> str:
    for _ in range(12):
        candidate = generate_chat_session_id(now)
        exists = (
            db.query(ChatSession.id)
            .filter(ChatSession.session_id == candidate)
            .first()
        )
        if not exists:
            return candidate
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="生成会话 ID 失败，请重试")


def _serialize_session(session: ChatSession) -> ChatSessionOut:
    return ChatSessionOut(
        id=(session.session_id or "").strip(),
        title=session.title or "",
        model=session.model or "",
        last_message_at=session.last_message_at,
        created_at=session.created_at or now_local(),
        updated_at=session.updated_at,
    )


def _parse_message_image_urls(raw: str | None) -> list[str]:
    if not (raw or "").strip():
        return []
    try:
        payload = json.loads(raw)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    urls: list[str] = []
    seen: set[str] = set()
    for item in payload:
        url = ""
        if isinstance(item, str):
            url = item.strip()
        elif isinstance(item, dict):
            url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        lowered = url.lower()
        if not (lowered.startswith("http://") or lowered.startswith("https://")):
            continue
        seen.add(url)
        urls.append(url)
    return urls


def _dump_message_images_json(urls: list[str]) -> str:
    return json.dumps(urls, ensure_ascii=False)


def _request_image_urls(body: ChatSendMessageRequest) -> list[str]:
    return [item.url for item in (body.images or []) if item.url]


def _message_image_urls(message: ChatMessage) -> list[str]:
    return _parse_message_image_urls(getattr(message, "images_json", None))


def _message_images_out(message: ChatMessage) -> list[ChatImagePart]:
    return [ChatImagePart(url=url) for url in _message_image_urls(message)]


def _to_provider_content(text: str, image_urls: list[str] | None = None) -> str | list[dict[str, Any]]:
    cleaned = (text or "").strip()
    urls = [url for url in (image_urls or []) if (url or "").strip()]
    if not urls:
        return cleaned
    parts: list[dict[str, Any]] = []
    if cleaned:
        parts.append({"type": "text", "text": cleaned})
    for url in urls:
        parts.append({"type": "image_url", "image_url": {"url": build_webp_url(url)}})
    return parts


def _serialize_message(message: ChatMessage, *, public_session_id: str) -> ChatMessageOut:
    return ChatMessageOut(
        id=int(message.id),
        session_id=public_session_id,
        role=message.role or "user",
        content=message.content or "",
        images=_message_images_out(message),
        generate=parse_generate_extra(getattr(message, "extra_json", None)),
        model=message.model or "",
        client_message_id=message.client_message_id,
        credit_cost=int(message.credit_cost or 0),
        status=message.status or "success",
        error_message=message.error_message or "",
        created_at=message.created_at or now_local(),
    )


def _require_session(db: Session, user_id: int, session_id: str) -> ChatSession:
    public_id = _normalize_public_session_id(session_id)
    session = (
        db.query(ChatSession)
        .filter(
            ChatSession.session_id == public_id,
            ChatSession.user_id == user_id,
            ChatSession.is_deleted.is_(False),
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return session


def _require_session_any_user(db: Session, session_id: str) -> ChatSession:
    public_id = _normalize_public_session_id(session_id)
    session = (
        db.query(ChatSession)
        .join(User, User.id == ChatSession.user_id)
        .filter(
            ChatSession.session_id == public_id,
            ChatSession.is_deleted.is_(False),
            User.role.notin_(ADMIN_VIEWER_EXCLUDED_ROLES),
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return session


def _session_credit_costs(db: Session, session_ids: list[int]) -> dict[int, int]:
    if not session_ids:
        return {}
    rows = (
        db.query(ChatMessage.session_id, func.coalesce(func.sum(ChatMessage.credit_cost), 0))
        .filter(ChatMessage.session_id.in_(session_ids))
        .group_by(ChatMessage.session_id)
        .all()
    )
    return {int(session_id): int(total or 0) for session_id, total in rows}


def _serialize_admin_session(
    session: ChatSession,
    user: User | None,
    *,
    credit_cost: int = 0,
    cos_config=None,
) -> ChatSessionAdminOut:
    return ChatSessionAdminOut(
        id=(session.session_id or "").strip(),
        title=session.title or "",
        model=session.model or "",
        last_message_at=session.last_message_at,
        created_at=session.created_at or now_local(),
        updated_at=session.updated_at,
        user_id=user_external_id(user) if user else "",
        username=(user.username if user else "") or "",
        avatar_url=resolve_user_avatar_url(user, cos_config=cos_config),
        credit_cost=max(int(credit_cost or 0), 0),
    )


def _ensure_model_available(db: Session, model: str) -> str:
    normalized = (model or "").strip().lower()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择对话模型")
    available = {item.model_key for item in list_chat_generation_models(db)}
    if normalized not in available:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="对话模型不可用或未绑定接口")
    return normalized


def list_sessions(
    db: Session,
    user_id: int,
    *,
    page: int = 1,
    page_size: int = DEFAULT_SESSION_PAGE_SIZE,
) -> ChatSessionListOut:
    normalized_page = max(int(page or 1), 1)
    normalized_page_size = min(max(int(page_size or DEFAULT_SESSION_PAGE_SIZE), 1), 100)
    # 多取 1 条判断 has_more，避免每次 COUNT(*)
    rows = (
        db.query(ChatSession)
        .filter(
            ChatSession.user_id == user_id,
            ChatSession.is_deleted.is_(False),
        )
        .order_by(
            func.coalesce(ChatSession.last_message_at, ChatSession.updated_at, ChatSession.created_at).desc(),
            ChatSession.id.desc(),
        )
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size + 1)
        .all()
    )
    has_more = len(rows) > normalized_page_size
    page_rows = rows[:normalized_page_size]
    # total 仅作兼容字段：无更多时为精确值，有更多时为下界估计
    total = (normalized_page - 1) * normalized_page_size + len(page_rows) + (1 if has_more else 0)
    return ChatSessionListOut(
        items=[_serialize_session(item) for item in page_rows],
        total=total,
        page=normalized_page,
        page_size=normalized_page_size,
        has_more=has_more,
    )


def get_session(db: Session, user_id: int, session_id: str) -> ChatSessionOut:
    return _serialize_session(_require_session(db, user_id, session_id))


def create_session(db: Session, user_id: int, body: ChatSessionCreate) -> ChatSessionOut:
    model = _ensure_model_available(db, body.model)
    now = datetime.now()
    last_error: Exception | None = None
    # 并发下以 DB 唯一索引为最终兜底；撞号后换新 ID 重试
    for _ in range(12):
        session = ChatSession(
            session_id=_allocate_session_id(db, now=now),
            user_id=user_id,
            title=body.title or "",
            model=model,
            last_message_at=now,
        )
        try:
            db.add(session)
            db.commit()
            db.refresh(session)
            return _serialize_session(session)
        except IntegrityError as exc:
            db.rollback()
            last_error = exc
            continue
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="生成会话 ID 失败，请重试",
    ) from last_error


def update_session(db: Session, user_id: int, session_id: str, body: ChatSessionUpdate) -> ChatSessionOut:
    session = _require_session(db, user_id, session_id)
    if body.title is not None:
        session.title = body.title
    if body.model is not None:
        session.model = _ensure_model_available(db, body.model)
    db.add(session)
    db.commit()
    db.refresh(session)
    return _serialize_session(session)


def delete_session(db: Session, user_id: int, session_id: str) -> None:
    session = _require_session(db, user_id, session_id)
    session.is_deleted = True
    db.add(session)
    db.commit()


def list_messages(
    db: Session,
    user_id: int,
    session_id: str,
    *,
    before_id: int | None = None,
    page_size: int = DEFAULT_MESSAGE_PAGE_SIZE,
) -> ChatMessageListOut:
    session = _require_session(db, user_id, session_id)
    public_session_id = (session.session_id or "").strip()
    normalized_page_size = min(max(int(page_size or DEFAULT_MESSAGE_PAGE_SIZE), 1), 100)
    query = db.query(ChatMessage).filter(ChatMessage.session_id == session.id)
    if before_id is not None:
        query = query.filter(ChatMessage.id < int(before_id))
    rows = (
        query.order_by(ChatMessage.id.desc())
        .limit(normalized_page_size + 1)
        .all()
    )
    has_more = len(rows) > normalized_page_size
    page_rows = rows[:normalized_page_size]
    page_rows.reverse()
    reconcile_running_chat_generates(db, page_rows)
    return ChatMessageListOut(
        items=[_serialize_message(item, public_session_id=public_session_id) for item in page_rows],
        has_more=has_more,
        next_before_id=page_rows[0].id if has_more and page_rows else None,
    )


def _session_sort_at(session: ChatSession):
    return session.last_message_at or session.updated_at or session.created_at or now_local()


def _load_session_cursor(db: Session, session_id: str | None) -> ChatSession | None:
    if not session_id:
        return None
    try:
        public_id = _normalize_public_session_id(session_id)
    except HTTPException:
        return None
    return db.query(ChatSession).filter(ChatSession.session_id == public_id).first()


def list_admin_sessions(
    db: Session,
    *,
    page_size: int = DEFAULT_SESSION_PAGE_SIZE,
    user_id: int | None = None,
    keyword: str | None = None,
    before_session_id: str | None = None,
) -> ChatSessionAdminListOut:
    normalized_page_size = min(max(int(page_size or DEFAULT_SESSION_PAGE_SIZE), 1), 100)
    sort_at = ChatSession.last_message_at
    query = (
        db.query(ChatSession, User)
        .join(User, User.id == ChatSession.user_id)
        .filter(
            ChatSession.is_deleted.is_(False),
            User.role.notin_(ADMIN_VIEWER_EXCLUDED_ROLES),
        )
    )
    if user_id is not None:
        query = query.filter(ChatSession.user_id == user_id)
    cleaned_keyword = (keyword or "").strip()[:50]
    if cleaned_keyword:
        like = f"%{cleaned_keyword}%"
        query = query.filter(or_(ChatSession.title.ilike(like), User.username.ilike(like)))
    cursor = _load_session_cursor(db, before_session_id)
    if cursor is not None:
        cursor_time = _session_sort_at(cursor)
        query = query.filter(
            or_(
                sort_at < cursor_time,
                and_(sort_at == cursor_time, ChatSession.id < int(cursor.id)),
            )
        )
    rows = (
        query.order_by(sort_at.desc(), ChatSession.id.desc())
        .limit(normalized_page_size + 1)
        .all()
    )
    has_more = len(rows) > normalized_page_size
    page_rows = rows[:normalized_page_size]
    credit_costs = _session_credit_costs(db, [int(session.id) for session, _user in page_rows])
    last_public_id = (page_rows[-1][0].session_id or "").strip() if page_rows else ""
    cos_config = get_optional_cos_config(db)
    return ChatSessionAdminListOut(
        items=[
            _serialize_admin_session(
                session,
                user,
                credit_cost=credit_costs.get(int(session.id), 0),
                cos_config=cos_config,
            )
            for session, user in page_rows
        ],
        total=len(page_rows) + (1 if has_more else 0),
        page=1,
        page_size=normalized_page_size,
        has_more=has_more,
        next_before_session_id=last_public_id if has_more and last_public_id else None,
    )


def get_admin_session(db: Session, session_id: str) -> ChatSessionAdminOut:
    session = _require_session_any_user(db, session_id)
    user = db.query(User).filter(User.id == session.user_id).first()
    credit_cost = _session_credit_costs(db, [int(session.id)]).get(int(session.id), 0)
    return _serialize_admin_session(
        session,
        user,
        credit_cost=credit_cost,
        cos_config=get_optional_cos_config(db),
    )


def list_admin_messages(
    db: Session,
    session_id: str,
    *,
    before_id: int | None = None,
    page_size: int = DEFAULT_MESSAGE_PAGE_SIZE,
) -> ChatMessageListOut:
    session = _require_session_any_user(db, session_id)
    public_session_id = (session.session_id or "").strip()
    normalized_page_size = min(max(int(page_size or DEFAULT_MESSAGE_PAGE_SIZE), 1), 100)
    query = db.query(ChatMessage).filter(ChatMessage.session_id == session.id)
    if before_id is not None:
        query = query.filter(ChatMessage.id < int(before_id))
    rows = (
        query.order_by(ChatMessage.id.desc())
        .limit(normalized_page_size + 1)
        .all()
    )
    has_more = len(rows) > normalized_page_size
    page_rows = rows[:normalized_page_size]
    page_rows.reverse()
    reconcile_running_chat_generates(db, page_rows)
    return ChatMessageListOut(
        items=[_serialize_message(item, public_session_id=public_session_id) for item in page_rows],
        has_more=has_more,
        next_before_id=page_rows[0].id if has_more and page_rows else None,
    )


def _build_context_messages(
    db: Session,
    session_id: int,
    *,
    system_prompt: str,
    context_message_limit: int,
    current_user_content: str,
    current_image_urls: list[str] | None = None,
) -> list[dict[str, Any]]:
    limit = max(2, int(context_message_limit or 10))
    history_rows = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session_id,
            ChatMessage.role.in_(["user", "assistant"]),
            ChatMessage.status == "success",
        )
        .order_by(ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    history_rows.reverse()
    messages: list[dict[str, Any]] = []
    combined_system = "\n\n".join(
        part for part in ((system_prompt or "").strip(), GENERATE_IMAGE_SYSTEM_HINT) if part
    )
    if combined_system:
        messages.append({"role": "system", "content": combined_system})
    for item in history_rows:
        text = (item.content or "").strip()
        image_urls = _message_image_urls(item)
        if not text and not image_urls:
            continue
        messages.append({"role": item.role, "content": _to_provider_content(text, image_urls)})
    current_content = _to_provider_content(current_user_content, current_image_urls)
    if not current_user_content.strip() and not (current_image_urls or []):
        return messages
    if not messages or messages[-1].get("content") != current_content:
        messages.append({"role": "user", "content": current_content})
    return messages


_STREAM_CLOSE_ERRORS = tuple(
    error_cls
    for error_cls in (
        getattr(httpx, "ReadError", None),
        getattr(httpx, "WriteError", None),
        getattr(httpx, "RemoteProtocolError", None),
        getattr(httpx, "LocalProtocolError", None),
        getattr(httpx, "DecodingError", None),
        getattr(httpx, "StreamClosed", None),
    )
    if error_cls is not None
)


def _payload_wants_stream(payload: object) -> bool:
    return isinstance(payload, dict) and payload.get("stream") is True


def _format_sse(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _split_client_delta(text: str) -> list[str]:
    if not text:
        return []
    # 上游或中间层偶尔会把完整回复塞进一个 delta；出口兜底拆开，保证前端仍逐字/逐词更新。
    if len(text) <= 12:
        return [text]
    parts = re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+|[^\u4e00-\u9fffA-Za-z0-9_]", text)
    return [part for part in parts if part]


def _dt_json(value) -> str:
    if value is None:
        value = now_local()
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%S")
    return str(value)[:19]


def _plain_message_payload(message: ChatMessage, *, public_session_id: str, content_override: str | None = None) -> dict:
    return {
        "id": int(message.id),
        "session_id": public_session_id,
        "role": message.role or "user",
        "content": content_override if content_override is not None else (message.content or ""),
        "images": [{"url": item.url} for item in _message_images_out(message)],
        "model": message.model or "",
        "client_message_id": message.client_message_id,
        "credit_cost": int(message.credit_cost or 0),
        "status": message.status or "success",
        "error_message": message.error_message or "",
        "created_at": _dt_json(message.created_at),
    }


def _plain_session_payload(session: ChatSession) -> dict:
    return {
        "id": (session.session_id or "").strip(),
        "title": session.title or "",
        "model": session.model or "",
        "last_message_at": _dt_json(session.last_message_at) if session.last_message_at else None,
        "created_at": _dt_json(session.created_at),
        "updated_at": _dt_json(session.updated_at) if session.updated_at else None,
    }


def _plain_done_payload(
    *,
    session: ChatSession,
    user_message: ChatMessage,
    assistant_message: ChatMessage,
    reply_text: str,
    balance: int | None,
) -> dict:
    public_session_id = (session.session_id or "").strip()
    return {
        "user_message": _plain_message_payload(user_message, public_session_id=public_session_id),
        "assistant_message": _plain_message_payload(
            assistant_message,
            public_session_id=public_session_id,
            content_override=reply_text,
        ),
        "credit_cost": int(assistant_message.credit_cost or 0),
        "balance": balance,
        "session": _plain_session_payload(session),
    }


def _dump_model(model) -> dict:
    if isinstance(model, dict):
        return model
    data = model.model_dump()
    return json.loads(
        json.dumps(
            data,
            ensure_ascii=False,
            default=lambda value: value.strftime("%Y-%m-%dT%H:%M:%S") if isinstance(value, datetime) else str(value),
        )
    )


def _snapshot_done_payload(
    *,
    user_plain: dict,
    assistant_plain: dict,
    session_plain: dict,
    reply_text: str,
    credit_cost: int = 0,
    balance: int | None = None,
) -> dict:
    assistant = dict(assistant_plain)
    assistant["content"] = reply_text
    assistant["status"] = "success"
    assistant["error_message"] = ""
    assistant["credit_cost"] = int(credit_cost or assistant.get("credit_cost") or 0)
    return {
        "user_message": user_plain,
        "assistant_message": assistant,
        "credit_cost": int(assistant["credit_cost"] or 0),
        "balance": balance,
        "session": session_plain,
    }


def _coerce_delta_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str) and item:
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text:
                    parts.append(text)
        return "".join(parts)
    return ""


def _unwrap_provider_payload(payload: object) -> object:
    current = payload
    for _ in range(3):
        if not isinstance(current, dict):
            return current
        inner = current.get("data")
        if isinstance(inner, dict) and (
            "choices" in inner or "delta" in inner or "output" in inner or "content" in inner
        ):
            current = inner
            continue
        inner = current.get("result")
        if isinstance(inner, dict) and ("choices" in inner or "delta" in inner or "output" in inner):
            current = inner
            continue
        inner = current.get("output")
        if isinstance(inner, dict) and ("choices" in inner or "text" in inner or "delta" in inner):
            current = inner
            continue
        return current
    return current


def _looks_like_stream_chunk(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    obj = str(payload.get("object") or "")
    if "chunk" in obj.lower():
        return True
    if "delta" in payload:
        return True
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict) and "delta" in choices[0]:
        return True
    event_type = str(payload.get("type") or "")
    return "delta" in event_type.lower()


def _extract_sse_delta_text(payload: object) -> str:
    payload = _unwrap_provider_payload(payload)
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            delta = first.get("delta")
            if isinstance(delta, dict):
                text = _coerce_delta_text(delta.get("content")) or _coerce_delta_text(delta.get("text"))
                if text:
                    return text
            elif isinstance(delta, str) and delta:
                return delta
            text = _coerce_delta_text(first.get("text"))
            if text:
                return text
    delta = payload.get("delta")
    if isinstance(delta, dict):
        text = _coerce_delta_text(delta.get("content")) or _coerce_delta_text(delta.get("text"))
        if text:
            return text
    if isinstance(delta, str) and delta:
        return delta
    event_type = str(payload.get("type") or "")
    if "delta" in event_type.lower():
        text = _coerce_delta_text(payload.get("output_text")) or _coerce_delta_text(payload.get("text"))
        if text:
            return text
    return ""


def _extract_sse_error_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("msg") or "").strip()
    if isinstance(error, str):
        return error.strip()
    return ""


def _iter_sse_payloads(response: httpx.Response) -> Iterator[object]:
    try:
        for raw_line in response.iter_lines():
            line = (raw_line or "").strip()
            if line.startswith("data:"):
                data = line[5:].strip()
            elif line[:1] in "{[":
                data = line
            else:
                continue
            if not data:
                continue
            if data == "[DONE]":
                return
            try:
                yield json.loads(data)
            except Exception:
                continue
    except _STREAM_CLOSE_ERRORS:
        return


async def _aiter_sse_payloads(response: httpx.Response) -> AsyncIterator[object]:
    try:
        async for raw_line in response.aiter_lines():
            line = (raw_line or "").strip()
            if line.startswith("data:"):
                data = line[5:].strip()
            elif line[:1] in "{[":
                data = line
            else:
                continue
            if not data:
                continue
            if data == "[DONE]":
                return
            try:
                yield json.loads(data)
            except Exception:
                continue
    except _STREAM_CLOSE_ERRORS:
        return


def _chunk_from_stream_payload(payload: object, *, result_text_field: str, collected: str) -> tuple[str, str]:
    view = _unwrap_provider_payload(payload)
    error_text = _extract_sse_error_text(view) or _extract_sse_error_text(payload)
    chunk = _extract_sse_delta_text(view)
    if not chunk and result_text_field and (_looks_like_stream_chunk(view) or collected):
        full = _extract_text_value(view, result_text_field) or _extract_text_value(payload, result_text_field)
        if full.startswith(collected) and len(full) > len(collected):
            chunk = full[len(collected) :]
    return chunk, error_text


def _fallback_full_text(payload: object, result_text_field: str) -> str:
    view = _unwrap_provider_payload(payload)
    return _extract_text_value(view, result_text_field) or _extract_text_value(payload, result_text_field)


@dataclass
class _RenderedChatCall:
    config_id: int
    result_text_field: str
    result_error_field: str
    success_statuses: list[int]
    rendered: object


def _raise_provider_http_error(
    config: ChatExternalApiConfig,
    *,
    status_code: int,
    payload: object | None,
    preview: str,
) -> None:
    error_text = ""
    if payload is not None and config.result_error_field:
        error_text = _extract_text_value(payload, config.result_error_field)
    if not error_text and payload is not None:
        error_text = _extract_sse_error_text(payload)
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=error_text or f"对话接口调用失败（HTTP {status_code}）",
    )


def _call_chat_provider_json(
    db: Session,
    config: ChatExternalApiConfig,
    *,
    messages: list[dict[str, Any]],
    system_prompt: str,
    user_message: str,
) -> tuple[str, str]:
    variables = {
        **build_secret_variables(db),
        "messages": messages,
        "system_prompt": system_prompt or "",
        "user_message": user_message,
    }
    rendered = render_config(config, variables)
    request_kwargs = build_external_request_kwargs(rendered)
    with httpx.Client(timeout=settings.AI_TIMEOUT, trust_env=False) as client:
        response = client.post(rendered.request_url, **request_kwargs)
    preview = (response.text or "")[:MAX_PROVIDER_RESPONSE_PREVIEW_LENGTH]
    success_statuses = parse_http_statuses_json(config.submit_success_statuses_json) or [200, 201, 202]
    try:
        payload = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"对话接口返回非 JSON：{preview or str(exc)}",
        ) from exc

    if response.status_code not in success_statuses:
        _raise_provider_http_error(config, status_code=response.status_code, payload=payload, preview=preview)

    text = _extract_text_value(payload, config.result_text_field)
    if not text:
        error_text = _extract_text_value(payload, config.result_error_field) if config.result_error_field else ""
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=error_text or "对话接口未返回有效文本",
        )
    return text, preview or json.dumps(payload, ensure_ascii=False)[:MAX_PROVIDER_RESPONSE_PREVIEW_LENGTH]


def _force_stream_true(rendered):
    payload = getattr(rendered, "payload", None)
    if not isinstance(payload, dict) or payload.get("stream") is True:
        return rendered
    updated = {**payload, "stream": True}
    try:
        return rendered.model_copy(update={"payload": updated})
    except Exception:
        payload["stream"] = True
        return rendered


def _build_stream_request_kwargs(rendered) -> dict:
    request_kwargs = build_external_request_kwargs(rendered)
    headers = dict(request_kwargs.get("headers") or {})
    headers.setdefault("Accept", "text/event-stream")
    request_kwargs["headers"] = headers
    return request_kwargs


def _iter_rendered_chat_text(
    *,
    result_text_field: str,
    result_error_field: str,
    success_statuses: list[int],
    rendered,
    preview_box: list[str] | None = None,
) -> Iterator[str]:
    rendered = _force_stream_true(rendered)
    request_kwargs = _build_stream_request_kwargs(rendered)
    collected = ""
    error_config = SimpleNamespace(result_error_field=result_error_field)
    try:
        with httpx.Client(timeout=settings.AI_TIMEOUT, trust_env=False) as client:
            with client.stream("POST", rendered.request_url, **request_kwargs) as response:
                if response.status_code not in success_statuses:
                    raw = response.read()
                    preview = raw.decode("utf-8", errors="replace")[:MAX_PROVIDER_RESPONSE_PREVIEW_LENGTH]
                    payload = None
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        payload = None
                    if preview_box is not None:
                        preview_box[:] = [preview]
                    _raise_provider_http_error(
                        error_config,  # type: ignore[arg-type]
                        status_code=response.status_code,
                        payload=payload,
                        preview=preview,
                    )
                    return

                got_text = False
                last_payload = None
                payload_count = 0
                chunk_count = 0
                content_type = str(response.headers.get("content-type") or "")
                for payload in _iter_sse_payloads(response):
                    payload_count += 1
                    last_payload = payload
                    chunk, error_text = _chunk_from_stream_payload(
                        payload, result_text_field=result_text_field, collected=collected
                    )
                    if error_text and not got_text:
                        if preview_box is not None:
                            preview_box[:] = [collected[:MAX_PROVIDER_RESPONSE_PREVIEW_LENGTH]]
                        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error_text)
                    if not chunk:
                        continue
                    got_text = True
                    chunk_count += 1
                    collected += chunk
                    yield chunk
                if not got_text and last_payload is not None and result_text_field:
                    chunk = _fallback_full_text(last_payload, result_text_field)
                    if chunk:
                        got_text = True
                        chunk_count += 1
                        collected += chunk
                        yield chunk
                logger.info(
                    "chat upstream stream content_type=%s payloads=%s chunks=%s stream=%s",
                    content_type,
                    payload_count,
                    chunk_count,
                    _payload_wants_stream(getattr(rendered, "payload", None)),
                )
                if preview_box is not None:
                    preview_box[:] = [collected[:MAX_PROVIDER_RESPONSE_PREVIEW_LENGTH]]
                if not got_text:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="对话接口未返回有效文本",
                    )
    except HTTPException:
        if collected:
            logger.warning("chat upstream http error after tokens")
            if preview_box is not None:
                preview_box[:] = [collected[:MAX_PROVIDER_RESPONSE_PREVIEW_LENGTH]]
            return
        raise
    except Exception as exc:
        if collected:
            logger.warning("chat upstream ended after tokens: %s", exc)
            if preview_box is not None:
                preview_box[:] = [collected[:MAX_PROVIDER_RESPONSE_PREVIEW_LENGTH]]
            return
        raise


async def _aiter_rendered_chat_text(
    *,
    result_text_field: str,
    result_error_field: str,
    success_statuses: list[int],
    rendered,
    preview_box: list[str] | None = None,
) -> AsyncIterator[str]:
    rendered = _force_stream_true(rendered)
    request_kwargs = _build_stream_request_kwargs(rendered)
    collected = ""
    error_config = SimpleNamespace(result_error_field=result_error_field)
    try:
        async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT, trust_env=False) as client:
            async with client.stream("POST", rendered.request_url, **request_kwargs) as response:
                if response.status_code not in success_statuses:
                    raw = await response.aread()
                    preview = raw.decode("utf-8", errors="replace")[:MAX_PROVIDER_RESPONSE_PREVIEW_LENGTH]
                    payload = None
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        payload = None
                    if preview_box is not None:
                        preview_box[:] = [preview]
                    _raise_provider_http_error(
                        error_config,  # type: ignore[arg-type]
                        status_code=response.status_code,
                        payload=payload,
                        preview=preview,
                    )
                    return

                got_text = False
                last_payload = None
                payload_count = 0
                chunk_count = 0
                content_type = str(response.headers.get("content-type") or "")
                async for payload in _aiter_sse_payloads(response):
                    payload_count += 1
                    last_payload = payload
                    chunk, error_text = _chunk_from_stream_payload(
                        payload, result_text_field=result_text_field, collected=collected
                    )
                    if error_text and not got_text:
                        if preview_box is not None:
                            preview_box[:] = [collected[:MAX_PROVIDER_RESPONSE_PREVIEW_LENGTH]]
                        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error_text)
                    if not chunk:
                        continue
                    got_text = True
                    chunk_count += 1
                    collected += chunk
                    yield chunk
                if not got_text and last_payload is not None and result_text_field:
                    chunk = _fallback_full_text(last_payload, result_text_field)
                    if chunk:
                        got_text = True
                        chunk_count += 1
                        collected += chunk
                        yield chunk
                logger.info(
                    "chat upstream stream content_type=%s payloads=%s chunks=%s stream=%s",
                    content_type,
                    payload_count,
                    chunk_count,
                    _payload_wants_stream(getattr(rendered, "payload", None)),
                )
                if preview_box is not None:
                    preview_box[:] = [collected[:MAX_PROVIDER_RESPONSE_PREVIEW_LENGTH]]
                if not got_text:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="对话接口未返回有效文本",
                    )
    except HTTPException:
        if collected:
            logger.warning("chat upstream http error after tokens")
            if preview_box is not None:
                preview_box[:] = [collected[:MAX_PROVIDER_RESPONSE_PREVIEW_LENGTH]]
            return
        raise
    except Exception as exc:
        if collected:
            logger.warning("chat upstream ended after tokens: %s", exc)
            if preview_box is not None:
                preview_box[:] = [collected[:MAX_PROVIDER_RESPONSE_PREVIEW_LENGTH]]
            return
        raise


def _iter_chat_provider_text(
    db: Session,
    config: ChatExternalApiConfig,
    *,
    messages: list[dict[str, Any]],
    system_prompt: str,
    user_message: str,
    preview_box: list[str] | None = None,
) -> Iterator[str]:
    variables = {
        **build_secret_variables(db),
        "messages": messages,
        "system_prompt": system_prompt or "",
        "user_message": user_message,
    }
    rendered = render_config(config, variables)
    if not _payload_wants_stream(rendered.payload):
        text, preview = _call_chat_provider_json(
            db,
            config,
            messages=messages,
            system_prompt=system_prompt,
            user_message=user_message,
        )
        if preview_box is not None:
            preview_box[:] = [preview]
        yield text
        return

    yield from _iter_rendered_chat_text(
        result_text_field=config.result_text_field or "",
        result_error_field=config.result_error_field or "",
        success_statuses=parse_http_statuses_json(config.submit_success_statuses_json) or [200, 201, 202],
        rendered=rendered,
        preview_box=preview_box,
    )


def _call_chat_provider(
    db: Session,
    config: ChatExternalApiConfig,
    *,
    messages: list[dict[str, Any]],
    system_prompt: str,
    user_message: str,
) -> tuple[str, str]:
    preview_box = [""]
    chunks: list[str] = []
    for chunk in _iter_chat_provider_text(
        db,
        config,
        messages=messages,
        system_prompt=system_prompt,
        user_message=user_message,
        preview_box=preview_box,
    ):
        chunks.append(chunk)
    text = "".join(chunks).strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="对话接口未返回有效文本")
    return text, preview_box[0]


def _get_reply_assistant(db: Session, session_id: int, user_message_id: int) -> ChatMessage | None:
    return (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session_id,
            ChatMessage.role == "assistant",
            ChatMessage.reply_to_message_id == user_message_id,
        )
        .first()
    )


@dataclass
class _PreparedChatSend:
    existing: ChatSendMessageResponse | None = None
    session: ChatSession | None = None
    user_message: ChatMessage | None = None
    assistant_message: ChatMessage | None = None
    model: str = ""
    binding: object | None = None
    primary_config: ChatExternalApiConfig | None = None
    backup_config: ChatExternalApiConfig | None = None
    credit_cost: int = 0
    context_messages: list[dict[str, Any]] | None = None
    user_content: str = ""


def chat_send_uses_sse(db: Session, user: User, session_id: str, body: ChatSendMessageRequest) -> bool:
    session = _require_session(db, user.id, session_id)
    model = _ensure_model_available(db, body.model or session.model)
    primary_config, _backup_config, _binding = resolve_chat_scene_configs(db, model)
    return payload_json_wants_stream(primary_config.payload_json)


def _existing_send_response(
    db: Session,
    user: User,
    session: ChatSession,
    existing_user: ChatMessage,
) -> ChatSendMessageResponse:
    public_session_id = (session.session_id or "").strip()
    assistant = _get_reply_assistant(db, session.id, existing_user.id)
    if assistant:
        if (assistant.status or "") == "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该消息仍在处理中，请稍后重试")
        return ChatSendMessageResponse(
            user_message=_serialize_message(existing_user, public_session_id=public_session_id),
            assistant_message=_serialize_message(assistant, public_session_id=public_session_id),
            credit_cost=int(assistant.credit_cost or 0),
            balance=get_user_credit_balance(db, user.id),
            session=_serialize_session(session),
        )
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该消息仍在处理中，请稍后重试")


def _prepare_send_message(
    db: Session,
    user: User,
    session_id: str,
    body: ChatSendMessageRequest,
) -> _PreparedChatSend:
    session = _require_session(db, user.id, session_id)
    existing_user = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session.id,
            ChatMessage.client_message_id == body.client_message_id,
            ChatMessage.role == "user",
        )
        .first()
    )
    if existing_user:
        return _PreparedChatSend(existing=_existing_send_response(db, user, session, existing_user))

    model = _ensure_model_available(db, body.model or session.model)
    primary_config, backup_config, binding = resolve_chat_scene_configs(db, model)
    credit_cost = get_chat_scene_credit_cost(db, model)
    current_balance = get_user_credit_balance(db, user.id)
    if not _is_credit_exempt_user(user) and current_balance < credit_cost:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"积分不足，需要 {credit_cost} 积分，当前余额 {current_balance}",
        )

    now = now_local()
    image_urls = _request_image_urls(body)
    user_message = ChatMessage(
        session_id=session.id,
        role="user",
        content=body.content,
        images_json=_dump_message_images_json(image_urls),
        model=model,
        client_message_id=body.client_message_id,
        credit_cost=0,
        status="success",
    )
    assistant_message = ChatMessage(
        session_id=session.id,
        role="assistant",
        reply_to_message_id=None,
        content="",
        model=model,
        credit_cost=0,
        status="pending",
        error_message="",
        provider_response_preview="",
    )
    try:
        db.add(user_message)
        db.flush()
        assistant_message.reply_to_message_id = user_message.id
        db.add(assistant_message)
        if not (session.title or "").strip():
            title_source = (body.content or "").strip() or ("图片对话" if image_urls else "")
            session.title = title_source[:30]
        session.model = model
        session.last_message_at = now
        db.add(session)
        db.commit()
    except Exception as exc:
        db.rollback()
        existing_user = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session.id,
                ChatMessage.client_message_id == body.client_message_id,
                ChatMessage.role == "user",
            )
            .first()
        )
        if existing_user:
            return _PreparedChatSend(existing=_existing_send_response(db, user, session, existing_user))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="消息提交冲突，请重试") from exc
    db.refresh(user_message)
    db.refresh(assistant_message)
    db.refresh(session)

    context_messages = _build_context_messages(
        db,
        session.id,
        system_prompt=binding.system_prompt or "",
        context_message_limit=int(binding.context_message_limit or 10),
        current_user_content=body.content,
        current_image_urls=image_urls,
    )
    return _PreparedChatSend(
        session=session,
        user_message=user_message,
        assistant_message=assistant_message,
        model=model,
        binding=binding,
        primary_config=primary_config,
        backup_config=backup_config,
        credit_cost=credit_cost,
        context_messages=context_messages,
        user_content=body.content,
    )


def send_message(
    db: Session,
    user: User,
    session_id: str,
    body: ChatSendMessageRequest,
) -> ChatSendMessageResponse:
    prepared = _prepare_send_message(db, user, session_id, body)
    if prepared.existing:
        return prepared.existing
    return _finish_provider_round(
        db,
        user=user,
        session=prepared.session,
        user_message=prepared.user_message,
        assistant_message=prepared.assistant_message,
        model=prepared.model,
        binding=prepared.binding,
        primary_config=prepared.primary_config,
        backup_config=prepared.backup_config,
        credit_cost=prepared.credit_cost,
        context_messages=prepared.context_messages or [],
        user_content=prepared.user_content,
    )


async def _replay_send_message_sse(response: ChatSendMessageResponse) -> AsyncIterator[str]:
    yield _format_sse(
        "meta",
        {
            "user_message": _dump_model(response.user_message),
            "assistant_message": _dump_model(response.assistant_message),
            "session": _dump_model(response.session),
        },
    )
    yield _format_sse("done", _dump_model(response))


def _serialize_user_message_for_result(
    db: Session,
    assistant_message: ChatMessage,
    *,
    public_session_id: str,
) -> ChatMessageOut:
    user_message = (
        db.get(ChatMessage, assistant_message.reply_to_message_id)
        if assistant_message.reply_to_message_id
        else None
    )
    if user_message:
        return _serialize_message(user_message, public_session_id=public_session_id)
    return _serialize_message(assistant_message, public_session_id=public_session_id)


def _mark_assistant_result(
    db: Session,
    *,
    user: User,
    session: ChatSession,
    assistant_message: ChatMessage,
    model: str,
    binding,
    credit_cost: int,
    reply_text: str,
    preview: str,
    used_fallback: bool,
    provider_config_id: int,
    last_error: str,
) -> ChatSendMessageResponse:
    public_session_id = (session.session_id or "").strip()
    if not reply_text:
        assistant_message.content = last_error
        assistant_message.status = "failed"
        assistant_message.error_message = last_error
        assistant_message.provider_api_config_id = provider_config_id
        assistant_message.used_fallback_api = used_fallback
        assistant_message.provider_response_preview = preview
        db.add(assistant_message)
        session.last_message_at = now_local()
        db.add(session)
        db.commit()
        db.refresh(assistant_message)
        db.refresh(session)
        return ChatSendMessageResponse(
            user_message=_serialize_user_message_for_result(
                db, assistant_message, public_session_id=public_session_id
            ),
            assistant_message=_serialize_message(assistant_message, public_session_id=public_session_id),
            credit_cost=0,
            balance=get_user_credit_balance(db, user.id),
            session=_serialize_session(session),
        )

    user_for_generate = (
        db.get(ChatMessage, assistant_message.reply_to_message_id)
        if assistant_message.reply_to_message_id
        else None
    )
    reply_text = apply_generate_proposal(
        db,
        session=session,
        assistant_message=assistant_message,
        user_message=user_for_generate,
        reply_text=reply_text,
    )
    assistant_message.content = reply_text
    assistant_message.model = model
    assistant_message.credit_cost = 0
    assistant_message.status = "success"
    assistant_message.error_message = ""
    assistant_message.provider_api_config_id = provider_config_id
    assistant_message.used_fallback_api = used_fallback
    assistant_message.provider_response_preview = preview
    db.add(assistant_message)
    session.last_message_at = now_local()
    db.add(session)
    db.commit()
    if not _is_credit_exempt_user(user) and credit_cost > 0:
        try:
            change_user_credit_balance(
                db,
                user.id,
                delta=-credit_cost,
                log_type="consume",
                description=f"{CHAT_CREDIT_LOG_DESCRIPTION}·{getattr(binding, 'scene_label', None) or model}",
            )
            assistant_message.credit_cost = credit_cost
            db.add(assistant_message)
            db.commit()
        except Exception:
            logger.exception("chat credit deduct failed after saving reply")
            db.rollback()
            assistant_message = db.get(ChatMessage, int(assistant_message.id)) or assistant_message
    db.refresh(assistant_message)
    db.refresh(session)
    return ChatSendMessageResponse(
        user_message=_serialize_user_message_for_result(
            db, assistant_message, public_session_id=public_session_id
        ),
        assistant_message=_serialize_message(assistant_message, public_session_id=public_session_id),
        credit_cost=int(assistant_message.credit_cost or 0),
        balance=get_user_credit_balance(db, user.id),
        session=_serialize_session(session),
    )


async def replay_send_message_sse(response: ChatSendMessageResponse) -> AsyncIterator[str]:
    async for item in _replay_send_message_sse(response):
        yield item


def prepare_chat_send(
    db: Session,
    user: User,
    session_id: str,
    body: ChatSendMessageRequest,
) -> _PreparedChatSend:
    return _prepare_send_message(db, user, session_id, body)


async def iter_prepared_send_message_sse(
    *,
    user_id: int,
    session_pk: int,
    user_message_id: int,
    assistant_message_id: int,
    model: str,
    credit_cost: int,
    context_messages: list[dict[str, Any]],
    user_content: str,
    system_prompt: str,
    scene_label: str,
    primary_config_id: int,
    backup_config_id: int | None,
) -> AsyncIterator[str]:
    db: Session | None = SessionLocal()
    completed = False
    reply_text = ""
    user_plain: dict = {}
    assistant_plain: dict = {}
    session_plain: dict = {}
    try:
        user = db.get(User, user_id)
        session = db.get(ChatSession, session_pk)
        user_message = db.get(ChatMessage, user_message_id)
        assistant_message = db.get(ChatMessage, assistant_message_id)
        primary_config = db.get(ChatExternalApiConfig, primary_config_id)
        backup_config = db.get(ChatExternalApiConfig, backup_config_id) if backup_config_id else None
        if not user or not session or not user_message or not assistant_message or not primary_config:
            yield _format_sse("error", {"message": "对话准备失败"})
            completed = True
            return

        public_session_id = (session.session_id or "").strip()
        user_plain = _plain_message_payload(user_message, public_session_id=public_session_id)
        assistant_plain = _plain_message_payload(assistant_message, public_session_id=public_session_id)
        session_plain = _plain_session_payload(session)
        yield _format_sse(
            "meta",
            {
                "user_message": user_plain,
                "assistant_message": assistant_plain,
                "session": session_plain,
            },
        )

        secret_variables = build_secret_variables(db)
        candidates = [primary_config] + ([backup_config] if backup_config else [])
        rendered_calls: list[_RenderedChatCall] = []
        for config in candidates:
            rendered = render_config(
                config,
                {
                    **secret_variables,
                    "messages": context_messages,
                    "system_prompt": system_prompt,
                    "user_message": user_content,
                },
            )
            rendered_calls.append(
                _RenderedChatCall(
                    config_id=int(config.id),
                    result_text_field=config.result_text_field or "",
                    result_error_field=config.result_error_field or "",
                    success_statuses=parse_http_statuses_json(config.submit_success_statuses_json) or [200, 201, 202],
                    rendered=rendered,
                )
            )
        # 流式期间释放 DB 连接，避免腾讯云 MySQL 把空闲连接掐掉后落库失败
        db.close()
        db = None

        preview = ""
        used_fallback = False
        provider_config_id = primary_config_id
        last_error = "对话服务异常，请稍后重试"
        got_token = False
        outbound_delta_count = 0
        for index, call in enumerate(rendered_calls):
            preview_box = [""]
            try:
                async for chunk in _aiter_rendered_chat_text(
                    result_text_field=call.result_text_field,
                    result_error_field=call.result_error_field,
                    success_statuses=call.success_statuses,
                    rendered=call.rendered,
                    preview_box=preview_box,
                ):
                    if not chunk:
                        continue
                    got_token = True
                    for piece in _split_client_delta(chunk):
                        outbound_delta_count += 1
                        reply_text += piece
                        yield _format_sse("delta", {"text": piece})
                        if piece != chunk:
                            await asyncio.sleep(SYNTHETIC_STREAM_DELAY_SECONDS)
                        else:
                            await asyncio.sleep(0)
                provider_config_id = call.config_id
                used_fallback = index > 0
                preview = preview_box[0]
                last_error = ""
                break
            except HTTPException as exc:
                preview = preview_box[0] or preview
                if got_token and reply_text.strip():
                    logger.warning("chat stream http error after tokens: %s", exc.detail)
                    provider_config_id = call.config_id
                    used_fallback = index > 0
                    last_error = ""
                    break
                last_error = str(exc.detail)
            except Exception as exc:
                preview = preview_box[0] or preview
                if got_token and reply_text.strip():
                    logger.warning("chat stream closed after tokens: %s", exc)
                    provider_config_id = call.config_id
                    used_fallback = index > 0
                    last_error = ""
                    break
                logger.exception("chat stream failed before tokens")
                last_error = "对话服务异常，请稍后重试"

        logger.info(
            "chat sse outbound deltas=%s chars=%s assistant_message_id=%s",
            outbound_delta_count,
            len(reply_text),
            assistant_message_id,
        )
        final_text = reply_text.strip()
        db = SessionLocal()
        user = db.get(User, user_id)
        session = db.get(ChatSession, session_pk)
        assistant_message = db.get(ChatMessage, assistant_message_id)
        if not user or not session or not assistant_message:
            completed = True
            if not final_text:
                yield _format_sse("error", {"message": "对话结果保存失败"})
                return
            logger.error("chat sse missing rows after tokens")
            yield _format_sse(
                "done",
                _snapshot_done_payload(
                    user_plain=user_plain,
                    assistant_plain=assistant_plain,
                    session_plain=session_plain,
                    reply_text=final_text,
                ),
            )
            return

        result = _mark_assistant_result(
            db,
            user=user,
            session=session,
            assistant_message=assistant_message,
            model=model,
            binding=SimpleNamespace(scene_label=scene_label),
            credit_cost=credit_cost,
            reply_text=final_text,
            preview=preview,
            used_fallback=used_fallback,
            provider_config_id=provider_config_id,
            last_error=last_error,
        )
        completed = True
        if (result.assistant_message.status or "") == "failed" and not final_text:
            yield _format_sse(
                "error",
                {
                    "message": result.assistant_message.error_message or last_error,
                    "assistant_message": _dump_model(result.assistant_message),
                    "balance": result.balance,
                    "session": _dump_model(result.session),
                },
            )
            return
        try:
            yield _format_sse("done", _dump_model(result))
        except Exception:
            logger.exception("chat sse dump done failed")
            yield _format_sse(
                "done",
                _snapshot_done_payload(
                    user_plain=user_plain,
                    assistant_plain=assistant_plain,
                    session_plain=session_plain,
                    reply_text=final_text or (result.assistant_message.content or ""),
                    credit_cost=int(result.credit_cost or 0),
                    balance=result.balance,
                ),
            )
    except Exception:
        logger.exception("chat sse finalize failed")
        if not completed:
            completed = True
            final_text = reply_text.strip()
            if final_text:
                try:
                    if db is not None:
                        db.rollback()
                        db.close()
                    db = SessionLocal()
                    user = db.get(User, user_id)
                    session = db.get(ChatSession, session_pk)
                    assistant_message = db.get(ChatMessage, assistant_message_id)
                    if user and session and assistant_message:
                        result = _mark_assistant_result(
                            db,
                            user=user,
                            session=session,
                            assistant_message=assistant_message,
                            model=model,
                            binding=SimpleNamespace(scene_label=scene_label),
                            credit_cost=credit_cost,
                            reply_text=final_text,
                            preview="",
                            used_fallback=False,
                            provider_config_id=primary_config_id,
                            last_error="",
                        )
                        yield _format_sse("done", _dump_model(result))
                        return
                except Exception:
                    logger.exception("chat sse retry save failed")
                yield _format_sse(
                    "done",
                    _snapshot_done_payload(
                        user_plain=user_plain,
                        assistant_plain=assistant_plain,
                        session_plain=session_plain,
                        reply_text=final_text,
                    ),
                )
                return
            yield _format_sse("error", {"message": "对话服务异常，请稍后重试"})
    finally:
        if not completed:
            if db is None:
                db = SessionLocal()
            try:
                assistant = db.get(ChatMessage, assistant_message_id)
                session_row = db.get(ChatSession, session_pk)
                if assistant and (assistant.status or "") == "pending":
                    assistant.content = reply_text or "已中断"
                    assistant.status = "failed"
                    assistant.error_message = "已中断"
                    db.add(assistant)
                    if session_row:
                        session_row.last_message_at = now_local()
                        db.add(session_row)
                    db.commit()
            except Exception:
                db.rollback()
                logger.exception("chat sse interrupt save failed")
        if db is not None:
            db.close()


def _finish_provider_round(
    db: Session,
    *,
    user: User,
    session: ChatSession,
    user_message: ChatMessage,
    assistant_message: ChatMessage,
    model: str,
    binding,
    primary_config: ChatExternalApiConfig,
    backup_config: ChatExternalApiConfig | None,
    credit_cost: int,
    context_messages: list[dict[str, Any]],
    user_content: str,
) -> ChatSendMessageResponse:
    reply_text = ""
    preview = ""
    used_fallback = False
    provider_config_id = int(primary_config.id)
    last_error = "对话服务异常，请稍后重试"
    candidates = [primary_config] + ([backup_config] if backup_config else [])
    for index, config in enumerate(candidates):
        try:
            reply_text, preview = _call_chat_provider(
                db,
                config,
                messages=context_messages,
                system_prompt=binding.system_prompt or "",
                user_message=user_content,
            )
            provider_config_id = int(config.id)
            used_fallback = index > 0
            last_error = ""
            break
        except HTTPException as exc:
            last_error = str(exc.detail)
        except httpx.TimeoutException:
            last_error = "对话请求超时，请稍后重试"
        except Exception:
            last_error = "对话服务异常，请稍后重试"

    if not reply_text:
        assistant_message.content = last_error
        assistant_message.status = "failed"
        assistant_message.error_message = last_error
        assistant_message.provider_api_config_id = provider_config_id
        assistant_message.used_fallback_api = used_fallback
        assistant_message.provider_response_preview = preview
        db.add(assistant_message)
        session.last_message_at = now_local()
        db.add(session)
        db.commit()
        db.refresh(assistant_message)
        db.refresh(session)
        public_session_id = (session.session_id or "").strip()
        return ChatSendMessageResponse(
            user_message=_serialize_message(user_message, public_session_id=public_session_id),
            assistant_message=_serialize_message(assistant_message, public_session_id=public_session_id),
            credit_cost=0,
            balance=get_user_credit_balance(db, user.id),
            session=_serialize_session(session),
        )

    reply_text = apply_generate_proposal(
        db,
        session=session,
        assistant_message=assistant_message,
        user_message=user_message,
        reply_text=reply_text,
    )
    assistant_message.content = reply_text
    assistant_message.model = model
    assistant_message.credit_cost = credit_cost if not _is_credit_exempt_user(user) else 0
    assistant_message.status = "success"
    assistant_message.error_message = ""
    assistant_message.provider_api_config_id = provider_config_id
    assistant_message.used_fallback_api = used_fallback
    assistant_message.provider_response_preview = preview
    db.add(assistant_message)
    session.last_message_at = now_local()
    db.add(session)
    if not _is_credit_exempt_user(user) and credit_cost > 0:
        change_user_credit_balance(
            db,
            user.id,
            delta=-credit_cost,
            log_type="consume",
            description=f"{CHAT_CREDIT_LOG_DESCRIPTION}·{binding.scene_label or model}",
        )
    db.commit()
    db.refresh(assistant_message)
    db.refresh(session)

    public_session_id = (session.session_id or "").strip()
    return ChatSendMessageResponse(
        user_message=_serialize_message(user_message, public_session_id=public_session_id),
        assistant_message=_serialize_message(assistant_message, public_session_id=public_session_id),
        credit_cost=int(assistant_message.credit_cost or 0),
        balance=get_user_credit_balance(db, user.id),
        session=_serialize_session(session),
    )
