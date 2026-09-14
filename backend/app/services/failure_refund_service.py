from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.credit_log import CreditLog
from app.utils.datetime_utils import now_local

IMAGE_TASK_FAILURE_REFUND_DESCRIPTION = "任务失败，返还积分"
VIDEO_TASK_FAILURE_REFUND_PREFIX = "AI视频任务失败返还"
DAILY_FAILURE_REFUND_LIMIT = 20


def get_failure_refund_remaining_count(used_count: int) -> int:
    return max(DAILY_FAILURE_REFUND_LIMIT - max(int(used_count or 0), 0), 0)


def today_failure_refund_window() -> tuple[datetime, datetime]:
    today_start = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
    return today_start, today_start + timedelta(days=1)


def get_today_failure_refund_count(db: Session, user_id: int) -> int:
    today_start, tomorrow_start = today_failure_refund_window()
    rows = (
        db.query(CreditLog.id)
        .filter(
            CreditLog.user_id == user_id,
            CreditLog.type == "allocate",
            or_(
                CreditLog.description == IMAGE_TASK_FAILURE_REFUND_DESCRIPTION,
                CreditLog.description.like(f"{VIDEO_TASK_FAILURE_REFUND_PREFIX} %"),
            ),
            CreditLog.created_at >= today_start,
            CreditLog.created_at < tomorrow_start,
        )
        .with_for_update()
        .all()
    )
    return len(rows)


def get_current_failure_refund_remaining_count(db: Session, user_id: int) -> int:
    return get_failure_refund_remaining_count(get_today_failure_refund_count(db, user_id))
