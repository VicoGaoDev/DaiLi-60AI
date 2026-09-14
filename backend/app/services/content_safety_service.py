from __future__ import annotations

import re

from sqlalchemy import or_

CONTENT_SAFETY_ERROR_KEYWORDS = (
    "unsafe",
    "image_unsafe",
    "content blocked",
    "appear to be unsafe",
    "safety",
    "nsfw",
    "moderation",
    "prompt blocked",
    "prompt rejected",
    "prompt violation",
    "content policy",
    "policy violation",
    "敏感",
    "违规",
    "审核拒绝",
    "审核未通过",
    "未通过审核",
    "安全风险",
    "内容安全",
)

CONTENT_SAFETY_ERROR_PATTERN = re.compile(
    "|".join(re.escape(keyword) for keyword in CONTENT_SAFETY_ERROR_KEYWORDS),
    re.IGNORECASE,
)


def is_content_safety_error_text(message: str | None) -> bool:
    return bool(CONTENT_SAFETY_ERROR_PATTERN.search(message or ""))


def build_content_safety_error_clause(column):
    return or_(*[column.ilike(f"%{keyword}%") for keyword in CONTENT_SAFETY_ERROR_KEYWORDS])


def build_exclude_content_safety_failed_task_clause(status_column, error_message_column):
    return or_(
        status_column.is_(None),
        status_column != "failed",
        error_message_column.is_(None),
        ~build_content_safety_error_clause(error_message_column),
    )
