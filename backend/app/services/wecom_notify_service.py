from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)


def format_wecom_user_label(user: User | None, *, fallback_id: int | None = None) -> str:
    if user is None:
        return f"ID {fallback_id}" if fallback_id is not None else "-"
    username = (user.username or "").strip() or f"ID {user.id}"
    extras = [item for item in ((user.email or "").strip(), (user.phone or "").strip()) if item]
    if extras:
        return f"{username} ({' / '.join(extras)})"
    return username


def is_wecom_notify_enabled() -> bool:
    return bool(settings.WECOM_NOTIFY_ENABLED and (settings.WECOM_WEBHOOK_URL or "").strip())


def is_wecom_alert_enabled() -> bool:
    return bool(settings.API_ALERT_ENABLED and (settings.WECOM_ALERT_WEBHOOK_URL or "").strip())


def send_wecom_markdown_to_url(content: str, webhook_url: str) -> bool:
    url = (webhook_url or "").strip()
    if not url:
        return False

    try:
        response = httpx.post(
            url,
            json={"msgtype": "markdown", "markdown": {"content": content}},
            timeout=max(int(settings.WECOM_NOTIFY_TIMEOUT_SECONDS or 0), 1),
        )
        response.raise_for_status()
        payload = response.json()
        if int(payload.get("errcode") or 0) != 0:
            logger.warning("WeCom notify failed: %s", payload)
            return False
        return True
    except Exception:
        logger.exception("Failed to send WeCom markdown message")
        return False


def send_wecom_markdown(content: str) -> bool:
    webhook_url = (settings.WECOM_WEBHOOK_URL or "").strip()
    if not settings.WECOM_NOTIFY_ENABLED or not webhook_url:
        return False
    return send_wecom_markdown_to_url(content, webhook_url)


def send_wecom_alert_markdown(content: str) -> bool:
    webhook_url = (settings.WECOM_ALERT_WEBHOOK_URL or "").strip()
    if not settings.API_ALERT_ENABLED or not webhook_url:
        return False
    return send_wecom_markdown_to_url(content, webhook_url)
