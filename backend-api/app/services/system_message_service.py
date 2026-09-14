from __future__ import annotations

from html.parser import HTMLParser
import re
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.models.system_message import SystemMessage, SystemMessageRecipient
from app.models.user import User
from app.services.business_id_service import (
    get_system_message_by_business_id,
    get_user_by_business_id,
    system_message_external_id,
    user_external_id,
)
from app.utils.datetime_utils import now_local

VALID_RECIPIENT_SCOPES = {"selected", "all"}
ALLOWED_TAGS = {
    "p", "br", "strong", "b", "em", "i", "u", "s", "blockquote", "code", "pre",
    "ul", "ol", "li", "a", "h1", "h2", "h3", "h4", "span", "div", "img",
    "table", "thead", "tbody", "tr", "th", "td",
}
STYLE_TAGS = ALLOWED_TAGS - {"br"}
ALLOWED_ATTRS = {
    "a": {"href", "target", "rel"},
    "img": {"src", "alt", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}
ALLOWED_STYLE_PROPERTIES = {
    "color",
    "background-color",
    "text-align",
    "font-size",
    "font-weight",
    "font-style",
    "text-decoration",
    "line-height",
    "margin-left",
    "padding-left",
    "width",
    "height",
}
UNSAFE_STYLE_VALUE_PATTERN = re.compile(r"(url\s*\(|expression\s*\(|javascript:|behavior\s*:|@import|[<>])", re.I)


class _SystemMessageHtmlSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.html_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag not in ALLOWED_TAGS:
            return
        rendered_attrs = self._sanitize_attrs(normalized_tag, attrs)
        attr_text = "".join(f' {name}="{value}"' for name, value in rendered_attrs)
        self.html_parts.append(f"<{normalized_tag}{attr_text}>")
        if normalized_tag == "img":
            self.text_parts.append(" [图片] ")
        if normalized_tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4"}:
            self.text_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in ALLOWED_TAGS and normalized_tag not in {"br", "img"}:
            self.html_parts.append(f"</{normalized_tag}>")
            if normalized_tag in {"p", "div", "li", "h1", "h2", "h3", "h4"}:
                self.text_parts.append(" ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        escaped = self._escape(data)
        self.html_parts.append(escaped)
        self.text_parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self.handle_data(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.handle_data(f"&#{name};")

    def _sanitize_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> list[tuple[str, str]]:
        allowed = set(ALLOWED_ATTRS.get(tag, set()))
        if tag in STYLE_TAGS:
            allowed.add("style")
        sanitized: list[tuple[str, str]] = []
        for raw_name, raw_value in attrs:
            name = raw_name.lower()
            value = (raw_value or "").strip()
            if name not in allowed or not value:
                continue
            if name == "style":
                value = self._sanitize_style(value)
                if not value:
                    continue
            if tag == "a" and name == "href":
                parsed = urlparse(value)
                if parsed.scheme and parsed.scheme not in {"http", "https", "mailto"}:
                    continue
            if tag == "img" and name == "src":
                parsed = urlparse(value)
                if value.startswith("data:image/"):
                    if not re.match(r"^data:image/(png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=\s]+$", value, re.I):
                        continue
                    value = re.sub(r"\s+", "", value)
                    sanitized.append((name, value))
                    continue
                if parsed.scheme and parsed.scheme not in {"http", "https"}:
                    continue
                if not parsed.scheme and not value.startswith("/"):
                    continue
            if tag == "a" and name == "target":
                value = "_blank"
            if name in {"width", "height", "colspan", "rowspan"} and not value.isdigit():
                continue
            sanitized.append((name, self._escape_attr(value)))
        if tag == "a" and any(name == "href" for name, _value in sanitized):
            sanitized = [(name, value) for name, value in sanitized if name != "rel"]
            sanitized.append(("rel", "noopener noreferrer"))
        return sanitized

    @staticmethod
    def _sanitize_style(style: str) -> str:
        declarations: list[str] = []
        for declaration in style.split(";"):
            if ":" not in declaration:
                continue
            raw_property, raw_value = declaration.split(":", 1)
            property_name = raw_property.strip().lower()
            value = raw_value.strip()
            if property_name not in ALLOWED_STYLE_PROPERTIES or not value:
                continue
            if UNSAFE_STYLE_VALUE_PATTERN.search(value):
                continue
            declarations.append(f"{property_name}: {value}")
        return "; ".join(declarations)

    @staticmethod
    def _escape(value: str) -> str:
        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    @classmethod
    def _escape_attr(cls, value: str) -> str:
        return cls._escape(value).replace('"', "&quot;")


def _normalize_subject(subject: str) -> str:
    normalized = (subject or "").strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="消息主题不能为空")
    if len(normalized) > 200:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="消息主题不能超过 200 个字符")
    return normalized


def _sanitize_content(content_html: str) -> tuple[str, str]:
    sanitizer = _SystemMessageHtmlSanitizer()
    sanitizer.feed(content_html or "")
    sanitizer.close()
    sanitized_html = "".join(sanitizer.html_parts).strip()
    content_text = " ".join("".join(sanitizer.text_parts).split())
    if not content_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="消息内容不能为空")
    if len(content_text) > 20000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="消息内容不能超过 20000 个字符")
    return sanitized_html, content_text


def _message_base_query(db: Session):
    return (
        db.query(SystemMessage)
        .options(
            selectinload(SystemMessage.sender),
            selectinload(SystemMessage.recipients).selectinload(SystemMessageRecipient.user),
        )
    )


def _serialize_sender(user: User | None) -> dict:
    return {
        "user_id": user_external_id(user),
        "username": user.username if user else "",
    }


def _serialize_recipient(recipient: SystemMessageRecipient) -> dict:
    user = recipient.user
    return {
        "user_id": user_external_id(user),
        "username": user.username if user else "",
        "email": user.email if user else None,
        "is_read": bool(recipient.is_read),
        "read_at": recipient.read_at,
    }


def _serialize_message(
    message: SystemMessage,
    *,
    recipient: SystemMessageRecipient | None = None,
    include_html: bool = False,
    include_recipients: bool = False,
) -> dict:
    data = {
        "message_id": system_message_external_id(message),
        "subject": message.subject or "",
        "content_text": message.content_text or "",
        "sender": _serialize_sender(message.sender),
        "recipient_scope": message.recipient_scope or "selected",
        "recipient_count": int(message.recipient_count or 0),
        "is_read": bool(recipient.is_read) if recipient else False,
        "read_at": recipient.read_at if recipient else None,
        "created_at": message.created_at,
        "updated_at": message.updated_at,
    }
    if include_html:
        data["content_html"] = message.content_html or ""
    if include_recipients:
        data["recipients"] = [_serialize_recipient(item) for item in message.recipients or []]
    return data


def _resolve_recipients(db: Session, *, recipient_scope: str, recipient_user_ids: list[str]) -> list[User]:
    if recipient_scope not in VALID_RECIPIENT_SCOPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的接收范围")

    if recipient_scope == "all":
        return (
            db.query(User)
            .filter(User.status == "active")
            .order_by(User.id.asc())
            .all()
        )

    unique_ids = []
    seen = set()
    for user_id in recipient_user_ids or []:
        normalized = (user_id or "").strip()
        if normalized and normalized not in seen:
            unique_ids.append(normalized)
            seen.add(normalized)
    if not unique_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少选择一个接收用户")

    users: list[User] = []
    for user_id in unique_ids:
        user = get_user_by_business_id(db, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"用户不存在：{user_id}")
        if user.status != "active":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"用户不可用：{user.username}")
        users.append(user)
    return users


def create_system_message(
    db: Session,
    *,
    admin: User,
    subject: str,
    content_html: str,
    recipient_scope: str,
    recipient_user_ids: list[str],
) -> dict:
    recipients = _resolve_recipients(db, recipient_scope=recipient_scope, recipient_user_ids=recipient_user_ids)
    if not recipients:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有可接收消息的用户")

    sanitized_html, content_text = _sanitize_content(content_html)
    message = SystemMessage(
        subject=_normalize_subject(subject),
        content_html=sanitized_html,
        content_text=content_text,
        sender_id=admin.id,
        recipient_scope=recipient_scope,
        recipient_count=len(recipients),
    )
    db.add(message)
    db.flush()
    for user in recipients:
        db.add(SystemMessageRecipient(message_id=message.id, user_id=user.id))
    db.commit()

    created = _message_base_query(db).filter(SystemMessage.id == message.id).first()
    if not created:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="系统消息创建失败")
    return _serialize_message(created, include_html=True, include_recipients=True)


def list_admin_system_messages(db: Session, *, page: int = 1, page_size: int = 20) -> dict:
    query = _message_base_query(db)
    total = query.count()
    rows = (
        query.order_by(SystemMessage.created_at.desc(), SystemMessage.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"total": total, "items": [_serialize_message(item) for item in rows]}


def get_admin_system_message_detail(db: Session, message_id: str) -> dict:
    message = get_system_message_by_business_id(db, message_id)
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="系统消息不存在")
    detail = _message_base_query(db).filter(SystemMessage.id == message.id).first()
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="系统消息不存在")
    return _serialize_message(detail, include_html=True, include_recipients=True)


def list_my_system_messages(db: Session, *, user_id: int, page: int = 1, page_size: int = 20) -> dict:
    query = (
        db.query(SystemMessageRecipient)
        .join(SystemMessage, SystemMessage.id == SystemMessageRecipient.message_id)
        .options(
            selectinload(SystemMessageRecipient.message).selectinload(SystemMessage.sender),
        )
        .filter(SystemMessageRecipient.user_id == user_id)
    )
    total = query.count()
    rows = (
        query.order_by(SystemMessage.created_at.desc(), SystemMessage.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "items": [_serialize_message(row.message, recipient=row) for row in rows],
    }


def count_my_unread_system_messages(db: Session, *, user_id: int) -> int:
    return (
        db.query(SystemMessageRecipient)
        .filter(
            SystemMessageRecipient.user_id == user_id,
            SystemMessageRecipient.is_read.is_(False),
        )
        .count()
    )


def mark_all_my_system_messages_as_read(db: Session, *, user_id: int) -> int:
    unread_items = (
        db.query(SystemMessageRecipient)
        .filter(
            SystemMessageRecipient.user_id == user_id,
            SystemMessageRecipient.is_read.is_(False),
        )
        .all()
    )
    if not unread_items:
        return 0

    read_at = now_local()
    for item in unread_items:
        item.is_read = True
        item.read_at = read_at
        db.add(item)
    db.commit()
    return len(unread_items)


def get_my_system_message_detail(db: Session, message_id: str, *, user_id: int) -> dict:
    message = get_system_message_by_business_id(db, message_id)
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="系统消息不存在")
    recipient = (
        db.query(SystemMessageRecipient)
        .filter(
            SystemMessageRecipient.message_id == message.id,
            SystemMessageRecipient.user_id == user_id,
        )
        .first()
    )
    if not recipient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="系统消息不存在")

    if not recipient.is_read:
        recipient.is_read = True
        recipient.read_at = now_local()
        db.add(recipient)
        db.commit()

    detail = _message_base_query(db).filter(SystemMessage.id == message.id).first()
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="系统消息不存在")
    refreshed_recipient = next((item for item in detail.recipients if item.user_id == user_id), recipient)
    return _serialize_message(detail, recipient=refreshed_recipient, include_html=True)
