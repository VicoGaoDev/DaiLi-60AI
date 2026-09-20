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
    from app.services.wecom_channel_service import EVENT_DAILY_REPORT, event_channel_enabled

    return event_channel_enabled(EVENT_DAILY_REPORT)


def is_wecom_alert_enabled() -> bool:
    from app.services.wecom_channel_service import EVENT_API_ALERT, event_channel_enabled

    return event_channel_enabled(EVENT_API_ALERT)


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
    from app.services.wecom_channel_service import EVENT_DAILY_REPORT

    return dispatch_wecom_event(EVENT_DAILY_REPORT, content, {"report_markdown": content, "content": content})


def send_wecom_alert_markdown(content: str) -> bool:
    from app.services.wecom_channel_service import EVENT_API_ALERT

    return dispatch_wecom_event(EVENT_API_ALERT, content, {"alert_markdown": content, "content": content})


def dispatch_wecom_event(event_key: str, content: str, context: dict | None = None) -> bool:
    from app.services.wecom_channel_service import render_wecom_template, resolve_dispatch_targets

    payload = context or {}
    sent = False
    for target in resolve_dispatch_targets(event_key, payload):
        template = (target.get("template_markdown") or "").strip()
        rendered = render_wecom_template(template, payload) if template else content
        if send_wecom_markdown_to_url(rendered, target["webhook_url"]):
            sent = True
    return sent
