from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import case, func, or_
from fastapi import HTTPException, status
from app.models.user import User
from app.models.task import Task
from app.models.task_api_attempt import TaskApiAttempt
from app.models.credit_log import CreditLog
from app.models.credit_redeem_key import CreditRedeemKey
from app.models.user_credit import DEFAULT_USER_CREDIT_STATUS, UserCredit
from app.services.business_id_service import get_user_by_business_id, task_external_id, user_external_id
from app.services.prompt_reverse_service import (
    PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION,
    PROMPT_REVERSE_MODE,
    PROMPT_REVERSE_MODEL,
)
from app.services.task_service import ENQUEUE_FAILURE_DESCRIPTION, TASK_FAILURE_REFUND_DESCRIPTION
from app.services.task_type_service import (
    TASK_TYPE_IMAGE_EDIT,
    TASK_TYPE_INPAINT,
    TASK_TYPE_PROMPT_REVERSE,
    TASK_TYPE_TEXT_GENERATE,
    get_task_scene_type_map,
    resolve_task_type_for_task,
)
from app.services.user_credit_service import (
    DEFAULT_CREDIT_TYPE,
    change_user_credit_balance,
    create_default_credit_account,
    get_user_credit_balance,
    get_user_credits_map,
)
from app.utils.datetime_utils import LOCAL_TZ, now_local, to_local_naive
from app.utils.security import hash_password

TASK_CREDIT_REFUND_DESCRIPTIONS = (
    ENQUEUE_FAILURE_DESCRIPTION,
    TASK_FAILURE_REFUND_DESCRIPTION,
)


def _non_whitelisted_user_filter():
    return User.is_whitelisted.is_(False)


def _dialog_task_run_time_expr():
    return func.unix_timestamp(Task.request_finished_at) - func.unix_timestamp(
        func.coalesce(Task.request_started_at, Task.created_at)
    )


def _get_first_admin_id(db: Session) -> int | None:
    first = db.query(User).filter(User.role == "admin").order_by(User.created_at.asc()).first()
    return first.id if first else None


@dataclass
class AnalyticsRecord:
    user_id: int
    status: str
    source: str
    model: str
    mode: str
    task_type: str
    credit_cost: int
    created_at: datetime
    from_canvas: bool = False


def _get_refunded_task_ids(db: Session, task_ids: list[int]) -> set[int]:
    normalized_ids = [int(task_id) for task_id in task_ids if task_id]
    if not normalized_ids:
        return set()
    return {
        int(task_id)
        for (task_id,) in (
            db.query(CreditLog.task_id)
            .filter(
                CreditLog.task_id.in_(normalized_ids),
                CreditLog.task_id.is_not(None),
                CreditLog.type == "allocate",
                CreditLog.description.in_(TASK_CREDIT_REFUND_DESCRIPTIONS),
            )
            .distinct()
            .all()
        )
        if task_id
    }


def _task_credit_refund_filter():
    return CreditLog.description.in_(TASK_CREDIT_REFUND_DESCRIPTIONS)


def _serialize_user(user: User) -> dict:
    db = user._sa_instance_state.session
    return {
        "id": user_external_id(user),
        "username": user.username,
        "email": user.email,
        "avatar_url": user.avatar_url or "",
        "role": user.role,
        "status": user.status,
        "is_whitelisted": bool(user.is_whitelisted),
        "credits": get_user_credit_balance(db, user.id) if db else 0,
        "created_at": user.created_at,
    }


def create_user(db: Session, username: str, password: str, role: str = "user", operator: User | None = None) -> dict:
    if username == "administrator":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该用户名为系统保留，不可使用")
    exists = db.query(User).filter(User.username == username).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在")
    if len(password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码至少6位")
    if role not in ("user", "admin"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="角色必须是 user 或 admin")
    if role == "admin" and operator and operator.role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅超级管理员可创建管理员账号")

    user = User(username=username, password_hash=hash_password(password), role=role)
    db.add(user)
    db.flush()
    create_default_credit_account(db, user)
    db.commit()
    db.refresh(user)
    return _serialize_user(user)


def list_users(db: Session) -> list[dict]:
    users = (
        db.query(User)
        .filter(User.role != "superadmin")
        .order_by(User.created_at.desc())
        .all()
    )
    user_ids = [user.id for user in users]
    credit_map = get_user_credits_map(db, user_ids)
    consumed_credit_rows = (
        db.query(
            CreditLog.user_id,
            func.coalesce(func.sum(func.abs(CreditLog.amount)), 0).label("consumed_credits"),
        )
        .filter(
            CreditLog.user_id.in_(user_ids),
            CreditLog.type == "consume",
        )
        .group_by(CreditLog.user_id)
        .all()
    ) if user_ids else []
    refunded_credit_rows = (
        db.query(
            CreditLog.user_id,
            func.coalesce(func.sum(CreditLog.amount), 0).label("refunded_credits"),
        )
        .filter(
            CreditLog.user_id.in_(user_ids),
            CreditLog.type == "allocate",
            _task_credit_refund_filter(),
        )
        .group_by(CreditLog.user_id)
        .all()
    ) if user_ids else []
    refunded_credit_map = {
        int(row.user_id): int(row.refunded_credits or 0)
        for row in refunded_credit_rows
    }
    consumed_credit_map = {
        int(row.user_id): max(
            int(row.consumed_credits or 0) - refunded_credit_map.get(int(row.user_id), 0),
            0,
        )
        for row in consumed_credit_rows
    }
    return [
        _serialize_user_with_balance(
            user,
            credit_map.get(user.id, 0),
            consumed_credit_map.get(user.id, 0),
        )
        for user in users
    ]


def list_user_options(db: Session, keyword: str | None = None, limit: int = 2000) -> list[dict]:
    query = db.query(User).filter(User.role != "superadmin")
    normalized_keyword = (keyword or "").strip()
    if normalized_keyword:
        keyword_like = f"%{normalized_keyword}%"
        query = query.filter(or_(
            User.username.ilike(keyword_like),
            User.email.ilike(keyword_like),
            User.business_id.ilike(keyword_like),
        ))
    users = (
        query
        .order_by(User.created_at.desc())
        .limit(max(1, min(int(limit or 2000), 5000)))
        .all()
    )
    return [
        _serialize_user_with_balance(user, 0, 0)
        for user in users
    ]


def get_user_detail(db: Session, user_id: str) -> dict:
    user = get_user_by_business_id(db, user_id)
    if not user or user.role == "superadmin":
        raise HTTPException(status_code=404, detail="用户不存在")

    consumed_credits = (
        db.query(func.coalesce(func.sum(func.abs(CreditLog.amount)), 0))
        .filter(
            CreditLog.user_id == user.id,
            CreditLog.type == "consume",
        )
        .scalar()
    ) or 0
    refunded_credits = (
        db.query(func.coalesce(func.sum(CreditLog.amount), 0))
        .filter(
            CreditLog.user_id == user.id,
            CreditLog.type == "allocate",
            _task_credit_refund_filter(),
        )
        .scalar()
    ) or 0
    return _serialize_user_with_balance(
        user,
        get_user_credit_balance(db, user.id),
        max(int(consumed_credits) - int(refunded_credits), 0),
    )


def _serialize_user_with_balance(user: User, balance: int, consumed_credits: int = 0) -> dict:
    return {
        "id": user_external_id(user),
        "username": user.username,
        "email": user.email,
        "avatar_url": user.avatar_url or "",
        "role": user.role,
        "status": user.status,
        "is_whitelisted": bool(user.is_whitelisted),
        "credits": int(balance or 0),
        "consumed_credits": int(consumed_credits or 0),
        "created_at": user.created_at,
    }


def update_user_status(db: Session, user_id: str, new_status: str) -> dict:
    if new_status not in ("active", "disabled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="状态必须是 active 或 disabled")

    user = get_user_by_business_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if user.role == "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无法修改超级管理员")
    if user.id == _get_first_admin_id(db) and new_status == "disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="初始管理员不允许被禁用")

    user.status = new_status
    db.commit()
    db.refresh(user)
    return _serialize_user(user)


def update_user_role(db: Session, user_id: str, new_role: str) -> dict:
    if new_role not in ("user", "admin"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="角色必须是 user 或 admin")

    user = get_user_by_business_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if user.role == "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无法修改超级管理员")
    if user.id == _get_first_admin_id(db) and new_role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="初始管理员不允许被降级")

    user.role = new_role
    db.commit()
    db.refresh(user)
    return _serialize_user(user)


def update_user_whitelist(db: Session, user_id: str, is_whitelisted: bool) -> dict:
    user = get_user_by_business_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if user.role == "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无法修改超级管理员")

    user.is_whitelisted = is_whitelisted
    db.commit()
    db.refresh(user)
    return _serialize_user(user)


def reset_user_password(db: Session, user_id: str, new_password: str) -> dict:
    if len(new_password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码至少6位")

    user = get_user_by_business_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if user.role == "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无法重置超级管理员密码")

    user.password_hash = hash_password(new_password)
    db.commit()
    db.refresh(user)
    return _serialize_user(user)


def allocate_credits(db: Session, user_id: str, amount: int, description: str, operator_id: int) -> dict:
    if amount == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="积分数量不能为 0")
    user = get_user_by_business_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    change_user_credit_balance(
        db,
        user.id,
        delta=amount,
        log_type="allocate",
        description=description or ("管理员充值" if amount > 0 else "管理员扣减"),
        operator_id=operator_id,
    )
    db.commit()
    db.refresh(user)
    return _serialize_user(user)


def reset_user_credits(db: Session, user_id: str, description: str, operator_id: int) -> dict:
    user = get_user_by_business_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    current_balance = get_user_credit_balance(db, user.id)
    if current_balance <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前积分已为 0，无需清零")

    deducted_amount = int(current_balance or 0)
    change_user_credit_balance(
        db,
        user.id,
        delta=-deducted_amount,
        log_type="allocate",
        description=description or f"管理员积分清零（原余额 {deducted_amount}）",
        operator_id=operator_id,
    )
    db.commit()
    db.refresh(user)
    return _serialize_user(user)


def _resolve_credit_log_mode(log: CreditLog, task_modes: dict[int, str]) -> str:
    if log.task_id and task_modes.get(log.task_id):
        return task_modes[log.task_id]
    if log.description in {PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION, f"API {PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION}"}:
        return PROMPT_REVERSE_MODE
    if (log.description or "").startswith("兑换积分码 "):
        return "redeem"
    return "manual"


def get_credit_logs(
    db: Session,
    user_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    direction: str | None = None,
    mode: str | None = None,
) -> dict:
    query = db.query(CreditLog)
    if user_id is not None:
        query = query.filter(CreditLog.user_id == user_id)
    if start_date is not None:
        query = query.filter(CreditLog.created_at >= start_date)
    if end_date is not None:
        query = query.filter(CreditLog.created_at <= end_date)
    logs = query.order_by(CreditLog.created_at.desc()).all()

    task_ids = {log.task_id for log in logs if log.task_id}
    task_cache = {
        task.id: task
        for task in db.query(Task).filter(Task.id.in_(task_ids)).all()
    } if task_ids else {}
    scene_type_map = get_task_scene_type_map(db)
    task_modes = {
        task_id: resolve_task_type_for_task(task, scene_type_map=scene_type_map)
        for task_id, task in task_cache.items()
    }

    filtered_logs: list[CreditLog] = []
    for log in logs:
        if direction == "increase" and log.amount <= 0:
            continue
        if direction == "decrease" and log.amount >= 0:
            continue
        resolved_mode = _resolve_credit_log_mode(log, task_modes)
        if mode and resolved_mode != mode:
            continue
        filtered_logs.append(log)

    total = len(filtered_logs)
    paged_logs = filtered_logs[(page - 1) * page_size: page * page_size]

    items = []
    user_cache: dict[int, User | None] = {}
    operator_cache: dict[int, User | None] = {}
    for log in paged_logs:
        if log.user_id not in user_cache:
            user_cache[log.user_id] = db.query(User).filter(User.id == log.user_id).first()
        if log.operator_id and log.operator_id not in operator_cache:
            operator_cache[log.operator_id] = db.query(User).filter(User.id == log.operator_id).first()
        operator = operator_cache.get(log.operator_id) if log.operator_id else None
        items.append({
            "id": log.id,
            "user_id": user_external_id(user_cache[log.user_id]),
            "username": user_cache[log.user_id].username if user_cache[log.user_id] else "",
            "amount": log.amount,
            "type": log.type,
            "mode": _resolve_credit_log_mode(log, task_modes),
            "description": log.description,
            "operator_name": operator.username if operator else "",
            "task_id": task_external_id(task_cache.get(log.task_id)) if log.task_id else None,
            "created_at": log.created_at,
        })
    return {"total": total, "items": items}


def get_stats(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    total_users = db.query(func.count(User.id)).filter(User.role != "superadmin", _non_whitelisted_user_filter()).scalar()
    total_remain_credits = (
        db.query(func.coalesce(func.sum(UserCredit.remain_credit), 0))
        .join(User, User.id == UserCredit.user_id)
        .filter(
            User.role != "superadmin",
            _non_whitelisted_user_filter(),
            UserCredit.type == DEFAULT_CREDIT_TYPE,
            UserCredit.status == DEFAULT_USER_CREDIT_STATUS,
        )
        .scalar()
    )
    total_generation_tasks = (
        db.query(func.count(Task.id))
        .join(User, User.id == Task.user_id)
        .filter(User.role != "superadmin", _non_whitelisted_user_filter())
        .scalar()
    )
    total_prompt_reverse_tasks = (
        db.query(func.count(CreditLog.id))
        .join(User, User.id == CreditLog.user_id)
        .filter(
            CreditLog.type == "consume",
            CreditLog.description.in_([PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION, f"API {PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION}"]),
            User.role != "superadmin",
            _non_whitelisted_user_filter(),
        )
        .scalar()
    )
    total_generation_credit_cost = (
        db.query(func.coalesce(func.sum(Task.credit_cost), 0))
        .join(User, User.id == Task.user_id)
        .filter(User.role != "superadmin", _non_whitelisted_user_filter())
        .scalar()
    )
    total_refunded_generation_credit = (
        db.query(func.coalesce(func.sum(CreditLog.amount), 0))
        .join(User, User.id == CreditLog.user_id)
        .filter(
            CreditLog.type == "allocate",
            CreditLog.task_id.is_not(None),
            CreditLog.description.in_(TASK_CREDIT_REFUND_DESCRIPTIONS),
            User.role != "superadmin",
            _non_whitelisted_user_filter(),
        )
        .scalar()
    )
    total_prompt_reverse_credit_cost = (
        db.query(func.coalesce(func.sum(-CreditLog.amount), 0))
        .join(User, User.id == CreditLog.user_id)
        .filter(
            CreditLog.type == "consume",
            CreditLog.description.in_([PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION, f"API {PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION}"]),
            User.role != "superadmin",
            _non_whitelisted_user_filter(),
        )
        .scalar()
    )
    active_task_user_ids = {
        user_id
        for (user_id,) in (
            db.query(Task.user_id)
            .join(User, User.id == Task.user_id)
            .filter(
                Task.created_at >= now - timedelta(days=7),
                User.role != "superadmin",
                _non_whitelisted_user_filter(),
            )
            .distinct()
            .all()
        )
    }
    active_prompt_reverse_user_ids = {
        user_id
        for (user_id,) in (
            db.query(CreditLog.user_id)
            .join(User, User.id == CreditLog.user_id)
            .filter(
                CreditLog.type == "consume",
                CreditLog.description.in_([PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION, f"API {PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION}"]),
                CreditLog.created_at >= now - timedelta(days=7),
                User.role != "superadmin",
                _non_whitelisted_user_filter(),
            )
            .distinct()
            .all()
        )
    }

    return {
        "total_users": total_users or 0,
        "total_tasks": int(total_generation_tasks or 0) + int(total_prompt_reverse_tasks or 0),
        "total_credit_cost": max(
            int(total_generation_credit_cost or 0) - int(total_refunded_generation_credit or 0),
            0,
        ) + int(total_prompt_reverse_credit_cost or 0),
        "total_remain_credits": int(total_remain_credits or 0),
        "active_users": len(active_task_user_ids | active_prompt_reverse_user_ids),
    }


def _to_local_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=LOCAL_TZ)
    return value.astimezone(LOCAL_TZ)


def _to_db_datetime(value: datetime) -> datetime:
    return to_local_naive(value)


def _start_of_day(value: datetime) -> datetime:
    value = _to_local_datetime(value)
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _end_of_day(value: datetime) -> datetime:
    value = _to_local_datetime(value)
    return value.replace(hour=23, minute=59, second=59, microsecond=999999)


def _start_of_3hour(value: datetime) -> datetime:
    value = _to_local_datetime(value)
    return value.replace(hour=(value.hour // 3) * 3, minute=0, second=0, microsecond=0)


def _end_of_3hour(value: datetime) -> datetime:
    start = _start_of_3hour(value)
    return start + timedelta(hours=3) - timedelta(microseconds=1)


def _start_of_week(value: datetime) -> datetime:
    value = _start_of_day(value)
    return value - timedelta(days=value.weekday())


def _end_of_week(value: datetime) -> datetime:
    return _start_of_week(value) + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)


def _start_of_month(value: datetime) -> datetime:
    value = _to_local_datetime(value)
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _shift_months(value: datetime, months: int) -> datetime:
    value = _to_local_datetime(value)
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _end_of_month(value: datetime) -> datetime:
    month_start = _start_of_month(value)
    next_month = _shift_months(month_start, 1)
    return next_month - timedelta(microseconds=1)


def _format_range_label(start: datetime, end: datetime) -> str:
    if start.date() == end.date():
        return f"{start.strftime('%Y-%m-%d %H:%M')} ~ {end.strftime('%H:%M')}"
    return f"{start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}"


def _align_range(
    granularity: str,
    start_date: datetime | None,
    end_date: datetime | None,
) -> tuple[datetime, datetime]:
    now = now_local().replace(tzinfo=LOCAL_TZ)
    if start_date is None or end_date is None:
        if granularity == "3hour":
            end = _end_of_3hour(now)
            start = _start_of_day(now)
        elif granularity == "day":
            end = _end_of_day(now)
            start = _start_of_day(now - timedelta(days=6))
        elif granularity == "week":
            end = _end_of_week(now)
            start = _start_of_week(now) - timedelta(weeks=7)
        else:
            end = _end_of_month(now)
            start = _start_of_month(_shift_months(now, -5))
        return start, end

    if granularity == "3hour":
        start = _start_of_3hour(start_date)
        end = _end_of_3hour(end_date)
    elif granularity == "day":
        start = _start_of_day(start_date)
        end = _end_of_day(end_date)
    elif granularity == "week":
        start = _start_of_week(start_date)
        end = _end_of_week(end_date)
    else:
        start = _start_of_month(start_date)
        end = _end_of_month(end_date)

    if end < start:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="结束时间不能早于开始时间")
    return start, end


def _iter_bucket_starts(start: datetime, end: datetime, granularity: str) -> list[datetime]:
    buckets: list[datetime] = []
    cursor = start
    while cursor <= end:
        buckets.append(cursor)
        if granularity == "3hour":
            cursor += timedelta(hours=3)
        elif granularity == "day":
            cursor += timedelta(days=1)
        elif granularity == "week":
            cursor += timedelta(weeks=1)
        else:
            cursor = _start_of_month(_shift_months(cursor, 1))
    return buckets


def _previous_range(start: datetime, end: datetime, granularity: str) -> tuple[datetime, datetime]:
    bucket_count = len(_iter_bucket_starts(start, end, granularity))
    if granularity == "3hour":
        previous_start = start - timedelta(hours=3 * bucket_count)
    elif granularity == "day":
        previous_start = start - timedelta(days=bucket_count)
    elif granularity == "week":
        previous_start = start - timedelta(weeks=bucket_count)
    else:
        previous_start = _start_of_month(_shift_months(start, -bucket_count))
    previous_end = start - timedelta(microseconds=1)
    return previous_start, previous_end


def _bucket_start(value: datetime, granularity: str) -> datetime:
    if granularity == "3hour":
        return _start_of_3hour(value)
    if granularity == "day":
        return _start_of_day(value)
    if granularity == "week":
        return _start_of_week(value)
    return _start_of_month(value)


def _bucket_end(value: datetime, granularity: str) -> datetime:
    if granularity == "3hour":
        return _end_of_3hour(value)
    if granularity == "day":
        return _end_of_day(value)
    if granularity == "week":
        return _end_of_week(value)
    return _end_of_month(value)


def _bucket_label(value: datetime, granularity: str) -> str:
    if granularity == "3hour":
        return value.strftime("%m-%d %H:%M")
    if granularity == "day":
        return value.strftime("%m-%d")
    if granularity == "week":
        week_end = value + timedelta(days=6)
        return f"{value.strftime('%m-%d')} ~ {week_end.strftime('%m-%d')}"
    return value.strftime("%Y-%m")


def _metric_payload(current: int, previous: int) -> dict:
    delta = current - previous
    delta_pct = None if previous == 0 else round(delta / previous * 100, 1)
    return {
        "current": current,
        "previous": previous,
        "delta": delta,
        "delta_pct": delta_pct,
    }


def _task_query(
    db: Session,
    *,
    start_date: datetime,
    end_date: datetime,
    status_filter: str | None = None,
    user_id: int | None = None,
    source: str | None = None,
    model: str | None = None,
    mode: str | None = None,
):
    query = db.query(Task).join(User, User.id == Task.user_id).filter(
        Task.created_at >= _to_db_datetime(start_date),
        Task.created_at <= _to_db_datetime(end_date),
        User.role != "superadmin",
        _non_whitelisted_user_filter(),
    )
    scene_type_map = get_task_scene_type_map(db)
    if status_filter:
        query = query.filter(Task.status == status_filter)
    if user_id:
        query = query.filter(Task.user_id == user_id)
    if source:
        query = query.filter(Task.source == source)
    if model:
        query = query.filter(Task.model == model)
    if mode:
        if mode == TASK_TYPE_INPAINT:
            query = query.filter((Task.mode == "inpaint") | (Task.model == "inpaint"))
        elif mode == TASK_TYPE_TEXT_GENERATE:
            text_generate_models = [key for key, value in scene_type_map.items() if value == "generate"]
            query = query.filter(Task.mode == "generate")
            query = query.filter(Task.model.in_(text_generate_models)) if text_generate_models else query.filter(Task.id.is_(None))
        elif mode == TASK_TYPE_IMAGE_EDIT:
            image_edit_models = [key for key, value in scene_type_map.items() if value == "image_edit"]
            query = query.filter(Task.mode == "generate")
            query = query.filter(Task.model.in_(image_edit_models)) if image_edit_models else query.filter(Task.id.is_(None))
        elif mode == TASK_TYPE_PROMPT_REVERSE:
            query = query.filter(Task.id.is_(None))
        else:
            query = query.filter(Task.mode == mode)
    return query


def _prompt_reverse_query(
    db: Session,
    *,
    start_date: datetime,
    end_date: datetime,
    status_filter: str | None = None,
    user_id: int | None = None,
    source: str | None = None,
    model: str | None = None,
    mode: str | None = None,
):
    if status_filter and status_filter != "success":
        return None
    if mode and mode != TASK_TYPE_PROMPT_REVERSE:
        return None
    if model and model != PROMPT_REVERSE_MODEL:
        return None
    if source and source != "web":
        return None

    query = db.query(CreditLog).join(User, User.id == CreditLog.user_id).filter(
        CreditLog.type == "consume",
        CreditLog.description.in_([PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION, f"API {PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION}"]),
        CreditLog.created_at >= _to_db_datetime(start_date),
        CreditLog.created_at <= _to_db_datetime(end_date),
        User.role != "superadmin",
        _non_whitelisted_user_filter(),
    )
    if user_id:
        query = query.filter(CreditLog.user_id == user_id)
    return query


def _user_query(
    db: Session,
    *,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    user_id: int | None = None,
):
    query = db.query(User).filter(User.role != "superadmin", _non_whitelisted_user_filter())
    if start_date is not None:
        query = query.filter(User.created_at >= _to_db_datetime(start_date))
    if end_date is not None:
        query = query.filter(User.created_at <= _to_db_datetime(end_date))
    if user_id:
        query = query.filter(User.id == user_id)
    return query


def _build_analytics_records(
    db: Session,
    *,
    start_date: datetime,
    end_date: datetime,
    status_filter: str | None = None,
    user_id: int | None = None,
    source: str | None = None,
    model: str | None = None,
    mode: str | None = None,
) -> list[AnalyticsRecord]:
    scene_type_map = get_task_scene_type_map(db)
    tasks = _task_query(
        db,
        start_date=start_date,
        end_date=end_date,
        status_filter=status_filter,
        user_id=user_id,
        source=source,
        model=model,
        mode=mode,
    ).all()
    refunded_task_ids = _get_refunded_task_ids(db, [task.id for task in tasks])
    task_records = [
        AnalyticsRecord(
            user_id=task.user_id,
            status=task.status or "pending",
            source=task.source or "web",
            model=task.model or "未设置",
            mode=task.mode or "generate",
            task_type=resolve_task_type_for_task(task, scene_type_map=scene_type_map),
            credit_cost=0 if task.id in refunded_task_ids else int(task.credit_cost or 0),
            created_at=task.created_at,
            from_canvas=bool(getattr(task, "canvas_id", None)),
        )
        for task in tasks
    ]

    prompt_reverse_query = _prompt_reverse_query(
        db,
        start_date=start_date,
        end_date=end_date,
        status_filter=status_filter,
        user_id=user_id,
        source=source,
        model=model,
        mode=mode,
    )
    prompt_reverse_records = []
    if prompt_reverse_query is not None:
        prompt_reverse_records = [
            AnalyticsRecord(
                user_id=log.user_id,
                status="success",
                source="web",
                model=PROMPT_REVERSE_MODEL,
                mode=PROMPT_REVERSE_MODE,
                task_type=TASK_TYPE_PROMPT_REVERSE,
                credit_cost=max(0, int(-(log.amount or 0))),
                created_at=log.created_at,
                from_canvas=False,
            )
            for log in prompt_reverse_query.all()
        ]
    return task_records + prompt_reverse_records


def _task_summary_metrics(records: list[AnalyticsRecord]) -> dict[str, int]:
    return {
        "tasks_created": len(records),
        "success_tasks": sum(1 for record in records if record.status == "success"),
        "failed_tasks": sum(1 for record in records if record.status == "failed"),
        "credits_consumed": sum(record.credit_cost for record in records),
        "active_users": len({record.user_id for record in records}),
    }


def _build_timeseries_points(
    bucket_starts: list[datetime],
    *,
    granularity: str,
    records: list[AnalyticsRecord],
    users: list[User],
) -> list[dict]:
    bucket_map = {
        bucket: {
            "label": _bucket_label(bucket, granularity),
            "bucket_start": bucket,
            "bucket_end": _bucket_end(bucket, granularity),
            "tasks_created": 0,
            "success_tasks": 0,
            "failed_tasks": 0,
            "credits_consumed": 0,
            "new_users": 0,
            "active_users": 0,
            "_active_user_ids": set(),
        }
        for bucket in bucket_starts
    }

    for record in records:
        bucket = _bucket_start(_to_local_datetime(record.created_at), granularity)
        if bucket not in bucket_map:
            continue
        item = bucket_map[bucket]
        item["tasks_created"] += 1
        item["credits_consumed"] += record.credit_cost
        if record.status == "success":
            item["success_tasks"] += 1
        if record.status == "failed":
            item["failed_tasks"] += 1
        item["_active_user_ids"].add(record.user_id)

    for user in users:
        bucket = _bucket_start(_to_local_datetime(user.created_at), granularity)
        if bucket in bucket_map:
            bucket_map[bucket]["new_users"] += 1

    result: list[dict] = []
    for bucket in bucket_starts:
        item = bucket_map[bucket]
        item["active_users"] = len(item.pop("_active_user_ids"))
        result.append(item)
    return result


def get_analytics_summary(
    db: Session,
    *,
    granularity: str = "day",
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    user_id: int | None = None,
    source: str | None = None,
    model: str | None = None,
    mode: str | None = None,
    status_filter: str | None = None,
) -> dict:
    current_start, current_end = _align_range(granularity, start_date, end_date)
    previous_start, previous_end = _previous_range(current_start, current_end, granularity)

    current_records = _build_analytics_records(
        db,
        start_date=current_start,
        end_date=current_end,
        status_filter=status_filter,
        user_id=user_id,
        source=source,
        model=model,
        mode=mode,
    )
    previous_records = _build_analytics_records(
        db,
        start_date=previous_start,
        end_date=previous_end,
        status_filter=status_filter,
        user_id=user_id,
        source=source,
        model=model,
        mode=mode,
    )

    current_metrics = _task_summary_metrics(current_records)
    previous_metrics = _task_summary_metrics(previous_records)
    current_new_users = _user_query(db, start_date=current_start, end_date=current_end, user_id=user_id).count()
    previous_new_users = _user_query(db, start_date=previous_start, end_date=previous_end, user_id=user_id).count()
    total_users = _user_query(db).count()

    return {
        "granularity": granularity,
        "current_range_label": _format_range_label(current_start, current_end),
        "previous_range_label": _format_range_label(previous_start, previous_end),
        "total_users": total_users,
        "tasks_created": _metric_payload(current_metrics["tasks_created"], previous_metrics["tasks_created"]),
        "success_tasks": _metric_payload(current_metrics["success_tasks"], previous_metrics["success_tasks"]),
        "failed_tasks": _metric_payload(current_metrics["failed_tasks"], previous_metrics["failed_tasks"]),
        "credits_consumed": _metric_payload(current_metrics["credits_consumed"], previous_metrics["credits_consumed"]),
        "new_users": _metric_payload(current_new_users, previous_new_users),
        "active_users": _metric_payload(current_metrics["active_users"], previous_metrics["active_users"]),
    }


def get_analytics_timeseries(
    db: Session,
    *,
    granularity: str = "day",
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    user_id: int | None = None,
    source: str | None = None,
    model: str | None = None,
    mode: str | None = None,
    status_filter: str | None = None,
) -> dict:
    current_start, current_end = _align_range(granularity, start_date, end_date)
    previous_start, previous_end = _previous_range(current_start, current_end, granularity)
    current_bucket_starts = _iter_bucket_starts(current_start, current_end, granularity)
    previous_bucket_starts = _iter_bucket_starts(previous_start, previous_end, granularity)

    current_records = _build_analytics_records(
        db,
        start_date=current_start,
        end_date=current_end,
        status_filter=status_filter,
        user_id=user_id,
        source=source,
        model=model,
        mode=mode,
    )
    previous_records = _build_analytics_records(
        db,
        start_date=previous_start,
        end_date=previous_end,
        status_filter=status_filter,
        user_id=user_id,
        source=source,
        model=model,
        mode=mode,
    )
    current_users = _user_query(db, start_date=current_start, end_date=current_end, user_id=user_id).all()
    previous_users = _user_query(db, start_date=previous_start, end_date=previous_end, user_id=user_id).all()

    return {
        "granularity": granularity,
        "current_range_label": _format_range_label(current_start, current_end),
        "previous_range_label": _format_range_label(previous_start, previous_end),
        "current": _build_timeseries_points(
            current_bucket_starts,
            granularity=granularity,
            records=current_records,
            users=current_users,
        ),
        "previous": _build_timeseries_points(
            previous_bucket_starts,
            granularity=granularity,
            records=previous_records,
            users=previous_users,
        ),
    }


def _sorted_breakdown(items: dict[str, dict[str, int]], limit: int | None = None) -> list[dict]:
    rows = [
        {"name": name, "count": payload["count"], "credit_cost": payload["credit_cost"]}
        for name, payload in items.items()
    ]
    rows.sort(key=lambda item: (item["count"], item["credit_cost"], item["name"]), reverse=True)
    if limit is not None:
        return rows[:limit]
    return rows


def _model_compare_rows(items: dict[str, dict[str, int]], limit: int = 10) -> list[dict]:
    rows: list[dict] = []
    for name, payload in items.items():
        count = int(payload.get("count") or 0)
        success_count = int(payload.get("success_count") or 0)
        failed_count = int(payload.get("failed_count") or 0)
        credit_cost = int(payload.get("credit_cost") or 0)
        rows.append({
            "name": name,
            "count": count,
            "success_count": success_count,
            "failed_count": failed_count,
            "success_rate": round((success_count / count) * 100, 1) if count else 0.0,
            "credit_cost": credit_cost,
            "avg_credit_cost": round(credit_cost / count, 1) if count else 0.0,
        })
    rows.sort(key=lambda item: (item["count"], item["credit_cost"], item["name"]), reverse=True)
    return rows[:limit]


def _api_attempt_performance_rows(
    db: Session,
    *,
    start_date: datetime,
    end_date: datetime,
    status_filter: str | None = None,
    user_id: int | None = None,
    source: str | None = None,
    model: str | None = None,
    mode: str | None = None,
    limit: int = 10,
) -> list[dict]:
    task_subquery = (
        _task_query(
            db,
            start_date=start_date,
            end_date=end_date,
            status_filter=status_filter,
            user_id=user_id,
            source=source,
            model=model,
            mode=mode,
        )
        .with_entities(Task.id)
        .subquery()
    )
    task_duration_seconds = case(
        (Task.request_finished_at.is_not(None), _dialog_task_run_time_expr()),
        else_=TaskApiAttempt.duration_ms / 1000.0,
    )
    download_duration_ms = case(
        (
            (TaskApiAttempt.status == "success")
            & TaskApiAttempt.result_download_ms.is_not(None)
            & (TaskApiAttempt.result_download_ms > 0),
            TaskApiAttempt.result_download_ms,
        ),
        else_=None,
    )
    rows = (
        db.query(
            TaskApiAttempt.api_config_id,
            TaskApiAttempt.api_config_name,
            func.count(TaskApiAttempt.id).label("call_count"),
            func.count(task_duration_seconds).label("task_duration_count"),
            func.avg(task_duration_seconds).label("avg_task_duration_seconds"),
            func.count(download_duration_ms).label("download_count"),
            func.avg(download_duration_ms).label("avg_result_download_ms"),
        )
        .join(Task, Task.id == TaskApiAttempt.task_id)
        .join(task_subquery, task_subquery.c.id == Task.id)
        .group_by(TaskApiAttempt.api_config_id, TaskApiAttempt.api_config_name)
        .all()
    )
    result: list[dict] = []
    for row in rows:
        api_config_id = row.api_config_id
        api_config_name = (row.api_config_name or "").strip()
        result.append({
            "api_config_id": int(api_config_id) if api_config_id is not None else None,
            "name": api_config_name or (f"接口 {api_config_id}" if api_config_id is not None else "未记录接口"),
            "call_count": int(row.call_count or 0),
            "task_duration_count": int(row.task_duration_count or 0),
            "avg_task_duration_seconds": round(float(row.avg_task_duration_seconds or 0), 2),
            "download_count": int(row.download_count or 0),
            "avg_result_download_ms": round(float(row.avg_result_download_ms or 0), 1),
        })
    result.sort(key=lambda item: (item["call_count"], item["download_count"], item["name"]), reverse=True)
    return result[:limit]


def get_analytics_breakdown(
    db: Session,
    *,
    granularity: str = "day",
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    user_id: int | None = None,
    source: str | None = None,
    model: str | None = None,
    mode: str | None = None,
    status_filter: str | None = None,
) -> dict:
    current_start, current_end = _align_range(granularity, start_date, end_date)
    records = _build_analytics_records(
        db,
        start_date=current_start,
        end_date=current_end,
        status_filter=status_filter,
        user_id=user_id,
        source=source,
        model=model,
        mode=mode,
    )

    relevant_user_ids = {record.user_id for record in records}
    users_by_id = {
        user.id: user
        for user in db.query(User).filter(User.id.in_(relevant_user_ids)).all()
    } if relevant_user_ids else {}

    status_breakdown: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "credit_cost": 0})
    source_breakdown: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "credit_cost": 0})
    mode_breakdown: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "credit_cost": 0})
    model_breakdown: dict[str, dict[str, int]] = defaultdict(
        lambda: {"count": 0, "credit_cost": 0, "success_count": 0, "failed_count": 0}
    )
    user_task_breakdown: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "credit_cost": 0})
    canvas_breakdown: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "credit_cost": 0})

    for record in records:
        task_cost = record.credit_cost
        status_key = record.status or "unknown"
        mode_key = record.task_type or TASK_TYPE_TEXT_GENERATE
        model_key = record.model or "未设置"

        status_breakdown[status_key]["count"] += 1
        status_breakdown[status_key]["credit_cost"] += task_cost

        source_key = record.source or "web"
        source_breakdown[source_key]["count"] += 1
        source_breakdown[source_key]["credit_cost"] += task_cost

        mode_breakdown[mode_key]["count"] += 1
        mode_breakdown[mode_key]["credit_cost"] += task_cost

        canvas_key = "canvas" if record.from_canvas else "non_canvas"
        canvas_breakdown[canvas_key]["count"] += 1
        canvas_breakdown[canvas_key]["credit_cost"] += task_cost

        model_breakdown[model_key]["count"] += 1
        model_breakdown[model_key]["credit_cost"] += task_cost
        if record.status == "success":
            model_breakdown[model_key]["success_count"] += 1
        elif record.status == "failed":
            model_breakdown[model_key]["failed_count"] += 1

        user = users_by_id.get(record.user_id)
        if user and user.role != "superadmin":
            user_task_breakdown[user.username]["count"] += 1
            user_task_breakdown[user.username]["credit_cost"] += task_cost

    user_breakdown_rows = _sorted_breakdown(user_task_breakdown)
    top_users_by_tasks = user_breakdown_rows[:10]
    top_users_by_credit = sorted(
        user_breakdown_rows,
        key=lambda item: (item["credit_cost"], item["count"], item["name"]),
        reverse=True,
    )

    return {
        "range_label": _format_range_label(current_start, current_end),
        "status_breakdown": _sorted_breakdown(status_breakdown),
        "source_breakdown": _sorted_breakdown(source_breakdown),
        "mode_breakdown": _sorted_breakdown(mode_breakdown),
        "canvas_breakdown": _sorted_breakdown(canvas_breakdown),
        "model_breakdown": _sorted_breakdown(model_breakdown, limit=10),
        "model_compare": _model_compare_rows(model_breakdown, limit=10),
        "api_attempt_performance": _api_attempt_performance_rows(
            db,
            start_date=current_start,
            end_date=current_end,
            status_filter=status_filter,
            user_id=user_id,
            source=source,
            model=model,
            mode=mode,
        ),
        "top_users_by_tasks": top_users_by_tasks,
        "top_users_by_credit": top_users_by_credit[:10],
    }


REDEEM_UNIT_PRICES: dict[int, float] = {
    30: 1.45,
    50: 3.50,
    70: 2.00,
    100: 5.00,
    300: 18.50,
    500: 34.00,
    501: 32.00,
    1000: 65.00,
    1001: 58.00,
    2000: 120.00,
    2001: 112.00,
    6000: 300.00,
    10000: 500.00,
}


def get_analytics_redeem_revenue(
    db: Session,
    *,
    granularity: str = "day",
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    current_start, current_end = _align_range(granularity, start_date, end_date)

    rows = (
        db.query(
            CreditRedeemKey.credit_amount,
            func.count(CreditRedeemKey.id).label("used_count"),
        )
        .filter(
            CreditRedeemKey.used_at.isnot(None),
            CreditRedeemKey.used_at >= current_start,
            CreditRedeemKey.used_at <= current_end,
        )
        .group_by(CreditRedeemKey.credit_amount)
        .all()
    )
    count_map = {int(row.credit_amount): int(row.used_count) for row in rows}

    items: list[dict] = []
    total_used_count = 0
    total_amount = 0.0

    for credit_amount in sorted(REDEEM_UNIT_PRICES):
        used_count = count_map.pop(credit_amount, 0)
        unit_price = REDEEM_UNIT_PRICES[credit_amount]
        subtotal = round(used_count * unit_price, 2)
        items.append(
            {
                "credit_amount": credit_amount,
                "unit_price": unit_price,
                "used_count": used_count,
                "total_amount": subtotal,
            }
        )
        total_used_count += used_count
        total_amount += subtotal

    for credit_amount in sorted(count_map):
        used_count = count_map[credit_amount]
        items.append(
            {
                "credit_amount": credit_amount,
                "unit_price": 0.0,
                "used_count": used_count,
                "total_amount": 0.0,
            }
        )
        total_used_count += used_count

    return {
        "range_label": _format_range_label(current_start, current_end),
        "items": items,
        "total_used_count": total_used_count,
        "total_amount": round(total_amount, 2),
    }
