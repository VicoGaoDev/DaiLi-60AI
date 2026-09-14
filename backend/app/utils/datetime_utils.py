from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Asia/Shanghai")


def now_local() -> datetime:
    return datetime.now(LOCAL_TZ).replace(tzinfo=None)


def to_local_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=LOCAL_TZ).replace(tzinfo=None)
    return value.astimezone(LOCAL_TZ).replace(tzinfo=None)
