from calendar import monthrange
from collections import defaultdict
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from sqlalchemy.orm import Session, aliased, joinedload
from sqlalchemy import case, func, or_
from fastapi import HTTPException, status
from app.models.user import User
from app.models.task import Task
from app.models.external_api_scene_binding import ExternalApiSceneBinding
from app.models.task_api_attempt import TaskApiAttempt
from app.models.credit_log import CreditLog
from app.models.credit_redeem_key import CreditRedeemKey
from app.models.admin_ledger import AdminLedger, AdminLedgerExpense, AdminLedgerLog
from app.models.offline_order import OfflineOrder
from app.models.payment_order import PaymentOrder
from app.models.referral_reward_grant import ReferralRewardGrant
from app.models.promo_reward_grant import PromoRewardGrant
from app.models.user_promo_code import UserPromoCode
from app.models.video_task import VideoTask
from app.models.video_task_api_attempt import VideoTaskApiAttempt
from app.models.user_credit import DEFAULT_USER_CREDIT_STATUS, UserCredit
from app.services.promo_service import PROMO_CODE_REWARD_CREDITS, get_user_promo_dashboard_for_admin
from app.services.promo_reward_service import (
    current_reward_month,
    fen_to_yuan,
    parse_reward_month,
    promo_rebate_start_at,
)
from app.services.business_id_service import get_user_by_business_id, task_external_id, user_external_id
from app.services.image_delivery_service import get_optional_cos_config, resolve_avatar_url, resolve_user_avatar_url
from app.services.content_safety_service import (
    build_content_safety_error_clause,
    build_exclude_content_safety_failed_task_clause,
    is_content_safety_error_text,
)
from app.services.external_api_config_service import SCENE_INPAINT, SCENE_SMART_CUTOUT
from app.services.prompt_optimize_service import (
    PROMPT_OPTIMIZE_CREDIT_LOG_DESCRIPTION,
    PROMPT_OPTIMIZE_MODE,
    PROMPT_OPTIMIZE_MODEL,
)
from app.services.prompt_reverse_service import (
    PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION,
    PROMPT_REVERSE_MODE,
    PROMPT_REVERSE_MODEL,
)
from app.services.task_service import ENQUEUE_FAILURE_DESCRIPTION, TASK_FAILURE_REFUND_DESCRIPTION
from app.services.task_service import is_task_generation_failure_credit_refunded
from app.services.task_type_service import (
    TASK_TYPE_IMAGE_EDIT,
    TASK_TYPE_INPAINT,
    TASK_TYPE_SMART_CUTOUT,
    TASK_TYPE_PROMPT_OPTIMIZE,
    TASK_TYPE_PROMPT_REVERSE,
    TASK_TYPE_TEXT_GENERATE,
    get_task_scene_type_map,
    get_task_scene_type_subset,
    resolve_task_type,
    resolve_task_type_for_task,
)
from app.services.user_credit_service import (
    DEFAULT_CREDIT_TYPE,
    change_user_credit_balance,
    create_default_credit_account,
    get_user_credit_account,
    get_user_credit_balance,
    get_user_credits_map,
)
from app.services.username_service import ensure_username_available
from app.services.video_task_service import (
    VIDEO_TASK_ENQUEUE_REFUND_PREFIX,
    VIDEO_TASK_FAILURE_REFUND_PREFIX,
    is_video_task_credit_refunded,
)
from app.services.history_service import _calculate_task_run_time
from app.services.wecom_notify_service import format_wecom_user_label, send_wecom_markdown
from app.utils.datetime_utils import LOCAL_TZ, now_local, to_local_naive
from app.utils.security import hash_password

TASK_CREDIT_REFUND_DESCRIPTIONS = (
    ENQUEUE_FAILURE_DESCRIPTION,
    TASK_FAILURE_REFUND_DESCRIPTION,
)


def _non_whitelisted_user_filter():
    return User.is_whitelisted.is_(False)


def _analytics_user_filter():
    return User.role == "user", _non_whitelisted_user_filter()


def _exclude_example_template_seed_task_clause():
    return or_(Task.is_example_template_seed.is_(False), Task.is_example_template_seed.is_(None))


def _dialog_task_run_time_expr():
    # 与任务详情 dialog 的 run_time 一致：finished - (started or created)
    return func.unix_timestamp(Task.request_finished_at) - func.unix_timestamp(
        func.coalesce(Task.request_started_at, Task.created_at)
    )


def _task_duration_seconds(task: Task, attempt_duration_ms: int | None = None) -> float | None:
    run_time = _calculate_task_run_time(task)
    if run_time is not None:
        return float(run_time)
    if attempt_duration_ms and attempt_duration_ms > 0:
        return attempt_duration_ms / 1000.0
    return None


def _task_attempt_duration_ms_map(db: Session, task_ids: list[int]) -> dict[int, int]:
    normalized_ids = [int(task_id) for task_id in task_ids if task_id]
    if not normalized_ids:
        return {}
    rows = (
        db.query(TaskApiAttempt.task_id, func.coalesce(func.sum(TaskApiAttempt.duration_ms), 0))
        .filter(
            TaskApiAttempt.task_id.in_(normalized_ids),
            TaskApiAttempt.duration_ms.is_not(None),
            TaskApiAttempt.duration_ms > 0,
        )
        .group_by(TaskApiAttempt.task_id)
        .all()
    )
    return {int(task_id): int(total_ms) for task_id, total_ms in rows if total_ms}


def _model_avg_run_time_map(
    db: Session,
    *,
    start_date: datetime,
    end_date: datetime,
    status_filter: str | None = None,
    user_id: int | None = None,
    source: str | None = None,
    model: str | None = None,
    mode: str | None = None,
    canvas_task_filter: str | None = None,
    include_unsafe_tasks: bool = True,
) -> dict[str, tuple[float, int]]:
    attempt_seconds = (
        db.query(func.sum(TaskApiAttempt.duration_ms) / 1000.0)
        .filter(
            TaskApiAttempt.task_id == Task.id,
            TaskApiAttempt.duration_ms.is_not(None),
            TaskApiAttempt.duration_ms > 0,
        )
        .correlate(Task)
        .scalar_subquery()
    )
    run_time = case(
        (Task.request_finished_at.is_not(None), _dialog_task_run_time_expr()),
        else_=attempt_seconds,
    )
    rows = (
        _task_query(
            db,
            start_date=start_date,
            end_date=end_date,
            status_filter=status_filter,
            user_id=user_id,
            source=source,
            model=model,
            mode=mode,
            canvas_task_filter=canvas_task_filter,
            include_unsafe_tasks=include_unsafe_tasks,
            include_restricted_users=True,
        )
        .with_entities(Task.model, func.avg(run_time), func.count(run_time))
        .group_by(Task.model)
        .all()
    )
    result: dict[str, tuple[float, int]] = {}
    for model_name, avg_value, sample_count in rows:
        count = int(sample_count or 0)
        if not count or avg_value is None:
            continue
        result[(model_name or "").strip() or "未设置"] = (round(float(avg_value), 1), count)
    return result


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
    used_fallback_api: bool = False
    from_canvas: bool = False
    duration_seconds: float | None = None


VIDEO_TASK_TYPE_TEXT_TO_VIDEO = "text_to_video"
VIDEO_TASK_TYPE_IMAGE_TO_VIDEO = "image_to_video"
VIDEO_TASK_TYPE_FIRST_LAST_FRAME = "first_last_frame"
ERROR_ANALYTICS_TASK_KIND_IMAGE = "image"
ERROR_ANALYTICS_TASK_KIND_VIDEO = "video"


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
    return or_(
        CreditLog.description.in_(TASK_CREDIT_REFUND_DESCRIPTIONS),
        CreditLog.description.like(f"{VIDEO_TASK_FAILURE_REFUND_PREFIX} %"),
        CreditLog.description.like(f"{VIDEO_TASK_ENQUEUE_REFUND_PREFIX} %"),
    )


def _serialize_user(user: User, *, cos_config=None) -> dict:
    db = user._sa_instance_state.session
    resolved_cos = cos_config if cos_config is not None else (get_optional_cos_config(db) if db else None)
    return {
        "id": user_external_id(user),
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "avatar_url": resolve_avatar_url(user.avatar_url, cos_config=resolved_cos),
        "role": user.role,
        "status": user.status,
        "is_whitelisted": bool(user.is_whitelisted),
        "credits": get_user_credit_balance(db, user.id) if db else 0,
        "created_at": user.created_at,
    }


def _get_first_admin_external_id(db: Session) -> str | None:
    first = db.query(User).filter(User.role == "admin").order_by(User.created_at.asc()).first()
    return user_external_id(first) if first else None


def create_user(db: Session, username: str, password: str, role: str = "user", operator: User | None = None) -> dict:
    normalized_username = ensure_username_available(db, username)
    if len(password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码至少6位")
    if role not in ("user", "admin"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="角色必须是 user 或 admin")
    if role == "admin" and operator and operator.role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅超级管理员可创建管理员账号")

    user = User(username=normalized_username, password_hash=hash_password(password), role=role)
    db.add(user)
    db.flush()
    create_default_credit_account(db, user)
    db.commit()
    db.refresh(user)
    return _serialize_user(user)


def list_users(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 30,
    keyword: str | None = None,
    status_filter: str | None = None,
    whitelist: bool | None = None,
    sort: str = "created_at_desc",
) -> dict:
    normalized_page = max(int(page or 1), 1)
    normalized_page_size = max(1, min(int(page_size or 30), 100))
    normalized_keyword = (keyword or "").strip()
    normalized_status = (status_filter or "").strip()
    normalized_sort = (sort or "created_at_desc").strip()

    query = db.query(User).filter(User.role != "superadmin")
    if normalized_keyword:
        keyword_like = f"%{normalized_keyword}%"
        query = query.filter(or_(
            User.username.ilike(keyword_like),
            User.email.ilike(keyword_like),
            User.phone.ilike(keyword_like),
            User.business_id.ilike(keyword_like),
        ))
    if normalized_status in {"active", "disabled"}:
        query = query.filter(User.status == normalized_status)
    if whitelist is not None:
        query = query.filter(User.is_whitelisted.is_(bool(whitelist)))

    total = int(query.count() or 0)

    if normalized_sort == "credits_desc":
        credit_subquery = (
            db.query(
                UserCredit.user_id.label("user_id"),
                func.coalesce(UserCredit.remain_credit, 0).label("credits"),
            )
            .subquery()
        )
        query = (
            query
            .outerjoin(credit_subquery, credit_subquery.c.user_id == User.id)
            .order_by(func.coalesce(credit_subquery.c.credits, 0).desc(), User.created_at.desc())
        )
    elif normalized_sort == "consumed_credits_desc":
        consumed_subquery = (
            db.query(
                CreditLog.user_id.label("user_id"),
                func.coalesce(func.sum(func.abs(CreditLog.amount)), 0).label("consumed_credits"),
            )
            .filter(CreditLog.type == "consume")
            .group_by(CreditLog.user_id)
            .subquery()
        )
        refunded_subquery = (
            db.query(
                CreditLog.user_id.label("user_id"),
                func.coalesce(func.sum(CreditLog.amount), 0).label("refunded_credits"),
            )
            .filter(
                CreditLog.type == "allocate",
                _task_credit_refund_filter(),
            )
            .group_by(CreditLog.user_id)
            .subquery()
        )
        net_consumed = case(
            (
                func.coalesce(consumed_subquery.c.consumed_credits, 0)
                - func.coalesce(refunded_subquery.c.refunded_credits, 0)
                > 0,
                func.coalesce(consumed_subquery.c.consumed_credits, 0)
                - func.coalesce(refunded_subquery.c.refunded_credits, 0),
            ),
            else_=0,
        )
        query = (
            query
            .outerjoin(consumed_subquery, consumed_subquery.c.user_id == User.id)
            .outerjoin(refunded_subquery, refunded_subquery.c.user_id == User.id)
            .order_by(net_consumed.desc(), User.created_at.desc())
        )
    else:
        query = query.order_by(User.created_at.desc())

    users = (
        query
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
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
    whitelisted_total = int(
        db.query(func.count(User.id))
        .filter(
            User.role != "superadmin",
            User.is_whitelisted.is_(True),
        )
        .scalar()
        or 0
    )
    cos_config = get_optional_cos_config(db)
    return {
        "items": [
            _serialize_user_with_balance(
                user,
                credit_map.get(user.id, 0),
                consumed_credit_map.get(user.id, 0),
                cos_config=cos_config,
            )
            for user in users
        ],
        "total": total,
        "page": normalized_page,
        "page_size": normalized_page_size,
        "has_more": normalized_page * normalized_page_size < total,
        "first_admin_id": _get_first_admin_external_id(db),
        "whitelisted_total": whitelisted_total,
    }


def list_user_options(db: Session, keyword: str | None = None, limit: int = 2000) -> list[dict]:
    query = db.query(User).filter(User.role != "superadmin")
    normalized_keyword = (keyword or "").strip()
    if normalized_keyword:
        keyword_like = f"%{normalized_keyword}%"
        query = query.filter(or_(
            User.username.ilike(keyword_like),
            User.email.ilike(keyword_like),
            User.phone.ilike(keyword_like),
            User.business_id.ilike(keyword_like),
        ))
    users = (
        query
        .order_by(User.created_at.desc())
        .limit(max(1, min(int(limit or 2000), 5000)))
        .all()
    )
    cos_config = get_optional_cos_config(db)
    return [
        _serialize_user_with_balance(user, 0, 0, cos_config=cos_config)
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


def _serialize_user_with_balance(user: User, balance: int, consumed_credits: int = 0, *, cos_config=None) -> dict:
    db = user._sa_instance_state.session
    resolved_cos = cos_config if cos_config is not None else (get_optional_cos_config(db) if db else None)
    return {
        "id": user_external_id(user),
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "avatar_url": resolve_avatar_url(user.avatar_url, cos_config=resolved_cos),
        "role": user.role,
        "status": user.status,
        "is_whitelisted": bool(user.is_whitelisted),
        "credits": int(balance or 0),
        "consumed_credits": int(consumed_credits or 0),
        "created_at": user.created_at,
    }


def _format_user_label(user: User | None) -> str:
    return format_wecom_user_label(user)


def _status_label(value: str) -> str:
    if value == "active":
        return "启用"
    if value == "disabled":
        return "禁用"
    return value or "-"


def _role_label(value: str) -> str:
    if value == "admin":
        return "管理员"
    if value == "user":
        return "普通用户"
    if value == "superadmin":
        return "超级管理员"
    return value or "-"


def _credit_snapshot(db: Session, user_id: int) -> tuple[int, int]:
    account = get_user_credit_account(db, user_id, create_if_missing=False)
    if not account:
        return 0, 0
    return int(account.remain_credit or 0), int(account.used_credit or 0)


def _send_user_admin_action_notification(
    db: Session,
    *,
    operator: User,
    target_user: User,
    action_type: str,
    detail_lines: list[str] | None = None,
) -> None:
    details = [line for line in (detail_lines or []) if line]
    content = (
        "## 👤 用户管理操作通知\n"
        f"> 🙋 操作人: **{_format_user_label(operator)}**\n"
        f"> 🎯 操作对象: **{_format_user_label(target_user)}**\n"
        f"> 🧾 用户ID: `{user_external_id(target_user)}`\n"
        f"> 🛠️ 操作类型: **{action_type}**\n"
    )
    if details:
        content += "\n".join(details) + "\n"
    content += f"> ⏰ 操作时间: {now_local().strftime('%Y-%m-%d %H:%M:%S')}"
    send_wecom_markdown(content)


def _yuan_to_fen(amount_yuan: Decimal | int | float | str) -> int:
    try:
        normalized = Decimal(str(amount_yuan)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="金额格式不正确") from exc
    if normalized <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="金额必须大于 0")
    return int((normalized * Decimal("100")).to_integral_value(rounding=ROUND_HALF_UP))


def _serialize_offline_order(order: OfflineOrder, user: User | None, creator: User | None) -> dict:
    amount_fen = int(order.amount_fen or 0)
    return {
        "id": int(order.id),
        "business_id": order.business_id,
        "user_id": user_external_id(user) if user else "",
        "username": user.username if user else "",
        "user_email": (user.email or "") if user else "",
        "order_type": order.order_type or "purchase",
        "credit_amount": int(order.credit_amount or 0),
        "amount_fen": amount_fen,
        "amount_yuan": round(amount_fen / 100, 2),
        "remark": order.remark or "",
        "created_by": user_external_id(creator) if creator else "",
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }


def update_user_status(db: Session, user_id: str, new_status: str, operator: User) -> dict:
    if new_status not in ("active", "disabled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="状态必须是 active 或 disabled")

    user = get_user_by_business_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if user.role == "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无法修改超级管理员")
    if user.id == _get_first_admin_id(db) and new_status == "disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="初始管理员不允许被禁用")

    previous_status = user.status or "active"
    user.status = new_status
    db.commit()
    db.refresh(user)
    _send_user_admin_action_notification(
        db,
        operator=operator,
        target_user=user,
        action_type="用户状态变更",
        detail_lines=[f"> 🔁 状态变更: **{_status_label(previous_status)} -> {_status_label(new_status)}**"],
    )
    return _serialize_user(user)


def update_user_role(db: Session, user_id: str, new_role: str, operator: User) -> dict:
    if new_role not in ("user", "admin"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="角色必须是 user 或 admin")

    user = get_user_by_business_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if user.role == "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无法修改超级管理员")
    if user.id == _get_first_admin_id(db) and new_role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="初始管理员不允许被降级")

    previous_role = user.role or "user"
    user.role = new_role
    db.commit()
    db.refresh(user)
    _send_user_admin_action_notification(
        db,
        operator=operator,
        target_user=user,
        action_type="用户角色变更",
        detail_lines=[f"> 🔁 角色变更: **{_role_label(previous_role)} -> {_role_label(new_role)}**"],
    )
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


def reset_user_password(db: Session, user_id: str, new_password: str, operator: User) -> dict:
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
    _send_user_admin_action_notification(
        db,
        operator=operator,
        target_user=user,
        action_type="重置用户密码",
    )
    return _serialize_user(user)


def allocate_credits(db: Session, user_id: str, amount: int, description: str, operator: User) -> dict:
    if amount == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="积分数量不能为 0")
    user = get_user_by_business_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    before_remain_credit, before_used_credit = _credit_snapshot(db, user.id)
    change_user_credit_balance(
        db,
        user.id,
        delta=amount,
        log_type="allocate",
        description=description or ("管理员充值" if amount > 0 else "管理员扣减"),
        operator_id=operator.id,
    )
    db.commit()
    db.refresh(user)
    after_remain_credit, after_used_credit = _credit_snapshot(db, user.id)
    _send_user_admin_action_notification(
        db,
        operator=operator,
        target_user=user,
        action_type="分配积分" if amount > 0 else "扣减积分",
        detail_lines=[
            f"> ⚡ 本次积分变更: **{amount:+d}**",
            f"> ⚡ 剩余积分: **{before_remain_credit} -> {after_remain_credit}**",
            f"> ⚡ 已使用积分: **{before_used_credit} -> {after_used_credit}**",
            f"> 📝 备注: {description.strip() if (description or '').strip() else '-'}",
        ],
    )
    return _serialize_user(user)


def reset_user_credits(db: Session, user_id: str, description: str, operator: User) -> dict:
    user = get_user_by_business_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    before_remain_credit, before_used_credit = _credit_snapshot(db, user.id)
    current_balance = before_remain_credit
    if current_balance <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前积分已为 0，无需清零")

    deducted_amount = int(current_balance or 0)
    change_user_credit_balance(
        db,
        user.id,
        delta=-deducted_amount,
        log_type="allocate",
        description=description or f"管理员积分清零（原余额 {deducted_amount}）",
        operator_id=operator.id,
    )
    db.commit()
    db.refresh(user)
    after_remain_credit, after_used_credit = _credit_snapshot(db, user.id)
    _send_user_admin_action_notification(
        db,
        operator=operator,
        target_user=user,
        action_type="积分清零",
        detail_lines=[
            f"> ⚡ 本次积分变更: **-{deducted_amount}**",
            f"> ⚡ 剩余积分: **{before_remain_credit} -> {after_remain_credit}**",
            f"> ⚡ 已使用积分: **{before_used_credit} -> {after_used_credit}**",
            f"> 📝 备注: {description.strip() if (description or '').strip() else '-'}",
        ],
    )
    return _serialize_user(user)


def create_offline_order(
    db: Session,
    *,
    user_id: str,
    order_type: str,
    credit_amount: int,
    amount_yuan: Decimal | int | float | str,
    remark: str,
    admin: User,
) -> dict:
    user = get_user_by_business_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if order_type not in ("purchase", "refund"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="线下订单类型必须是 purchase 或 refund")
    if credit_amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="积分必须大于 0")

    order = OfflineOrder(
        user_id=user.id,
        order_type=order_type,
        credit_amount=int(credit_amount),
        amount_fen=_yuan_to_fen(amount_yuan),
        remark=(remark or "").strip(),
        created_by=admin.id,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return _serialize_offline_order(order, user, admin)


def list_offline_orders(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    user_keyword: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    creator_alias = aliased(User)
    query = (
        db.query(OfflineOrder, User, creator_alias)
        .join(User, User.id == OfflineOrder.user_id)
        .join(creator_alias, creator_alias.id == OfflineOrder.created_by)
    )

    keyword = (user_keyword or "").strip()
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            (User.username.ilike(like))
            | (User.email.ilike(like))
            | (User.business_id.ilike(like))
            | (OfflineOrder.business_id.ilike(like))
        )
    if start_date:
        query = query.filter(OfflineOrder.created_at >= start_date)
    if end_date:
        query = query.filter(OfflineOrder.created_at <= end_date)

    total = query.count()
    rows = (
        query
        .order_by(OfflineOrder.created_at.desc(), OfflineOrder.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for order, user, creator in rows:
        items.append(_serialize_offline_order(order, user, creator))
    return {"total": total, "items": items}


def _resolve_credit_log_mode(log: CreditLog, task_modes: dict[int, str]) -> str:
    if log.task_id and task_modes.get(log.task_id):
        return task_modes[log.task_id]
    if log.description in {PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION, f"API {PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION}"}:
        return PROMPT_REVERSE_MODE
    if log.description in {PROMPT_OPTIMIZE_CREDIT_LOG_DESCRIPTION, f"API {PROMPT_OPTIMIZE_CREDIT_LOG_DESCRIPTION}"}:
        return PROMPT_OPTIMIZE_MODE
    if (log.description or "").startswith("兑换积分码 "):
        return "redeem"
    if (log.description or "").startswith("在线支付订单 "):
        return "purchase"
    return "manual"


def _credit_log_prompt_reverse_descriptions() -> list[str]:
    return [
        PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION,
        f"API {PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION}",
    ]


def _credit_log_prompt_optimize_descriptions() -> list[str]:
    return [
        PROMPT_OPTIMIZE_CREDIT_LOG_DESCRIPTION,
        f"API {PROMPT_OPTIMIZE_CREDIT_LOG_DESCRIPTION}",
    ]


def _credit_log_prompt_tool_descriptions() -> list[str]:
    return [
        *_credit_log_prompt_reverse_descriptions(),
        *_credit_log_prompt_optimize_descriptions(),
    ]


@dataclass
class _CreditLogTaskSnapshot:
    id: int
    business_id: str | None
    mode: str | None
    model: str | None


def _credit_log_image_edit_scene_keys_query(db: Session):
    return (
        db.query(ExternalApiSceneBinding.scene_key)
        .filter(ExternalApiSceneBinding.is_deleted.is_(False))
        .filter(ExternalApiSceneBinding.scene_type == TASK_TYPE_IMAGE_EDIT)
    )


def _apply_credit_log_mode_filter(query, db: Session, mode: str):
    description = func.coalesce(CreditLog.description, "")
    prompt_reverse_descriptions = _credit_log_prompt_reverse_descriptions()
    prompt_optimize_descriptions = _credit_log_prompt_optimize_descriptions()
    prompt_tool_descriptions = _credit_log_prompt_tool_descriptions()

    if mode == "redeem":
        return query.filter(description.like("兑换积分码 %"))
    if mode == "purchase":
        return query.filter(description.like("在线支付订单 %"))
    if mode == TASK_TYPE_PROMPT_REVERSE:
        return (
            query
            .outerjoin(Task, Task.id == CreditLog.task_id)
            .filter(
                or_(
                    description.in_(prompt_reverse_descriptions),
                    Task.mode == PROMPT_REVERSE_MODE,
                )
            )
        )
    if mode == TASK_TYPE_PROMPT_OPTIMIZE:
        return (
            query
            .outerjoin(Task, Task.id == CreditLog.task_id)
            .filter(
                or_(
                    description.in_(prompt_optimize_descriptions),
                    Task.mode == PROMPT_OPTIMIZE_MODE,
                )
            )
        )
    if mode == TASK_TYPE_INPAINT:
        return (
            query
            .join(Task, Task.id == CreditLog.task_id)
            .filter(
                or_(
                    Task.mode == TASK_TYPE_INPAINT,
                    Task.model == SCENE_INPAINT,
                )
            )
        )
    if mode == TASK_TYPE_SMART_CUTOUT:
        return (
            query
            .join(Task, Task.id == CreditLog.task_id)
            .filter(
                or_(
                    Task.mode == TASK_TYPE_SMART_CUTOUT,
                    Task.model == SCENE_SMART_CUTOUT,
                )
            )
        )
    if mode == TASK_TYPE_IMAGE_EDIT:
        image_edit_scene_keys = _credit_log_image_edit_scene_keys_query(db)
        return (
            query
            .join(Task, Task.id == CreditLog.task_id)
            .filter(Task.model.in_(image_edit_scene_keys))
            .filter(or_(Task.mode.is_(None), Task.mode != PROMPT_REVERSE_MODE))
            .filter(or_(Task.mode.is_(None), Task.mode != PROMPT_OPTIMIZE_MODE))
            .filter(or_(Task.mode.is_(None), Task.mode != TASK_TYPE_INPAINT))
            .filter(or_(Task.model.is_(None), Task.model != SCENE_INPAINT))
            .filter(or_(Task.mode.is_(None), Task.mode != TASK_TYPE_SMART_CUTOUT))
            .filter(or_(Task.model.is_(None), Task.model != SCENE_SMART_CUTOUT))
        )
    if mode == TASK_TYPE_TEXT_GENERATE:
        image_edit_scene_keys = _credit_log_image_edit_scene_keys_query(db)
        return (
            query
            .join(Task, Task.id == CreditLog.task_id)
            .filter(or_(Task.mode.is_(None), Task.mode != PROMPT_REVERSE_MODE))
            .filter(or_(Task.mode.is_(None), Task.mode != PROMPT_OPTIMIZE_MODE))
            .filter(or_(Task.mode.is_(None), Task.mode != TASK_TYPE_INPAINT))
            .filter(or_(Task.model.is_(None), Task.model != SCENE_INPAINT))
            .filter(or_(Task.mode.is_(None), Task.mode != TASK_TYPE_SMART_CUTOUT))
            .filter(or_(Task.model.is_(None), Task.model != SCENE_SMART_CUTOUT))
            .filter(or_(Task.model.is_(None), ~Task.model.in_(image_edit_scene_keys)))
        )
    if mode == "manual":
        return (
            query
            .outerjoin(Task, Task.id == CreditLog.task_id)
            .filter(Task.id.is_(None))
            .filter(~description.in_(prompt_tool_descriptions))
            .filter(~description.like("兑换积分码 %"))
            .filter(~description.like("在线支付订单 %"))
        )
    return query.filter(CreditLog.id.is_(None))


def _get_credit_log_task_context(
    db: Session,
    logs: list[CreditLog],
) -> tuple[dict[int, _CreditLogTaskSnapshot], dict[int, str]]:
    task_ids = {int(log.task_id) for log in logs if log.task_id}
    if not task_ids:
        return {}, {}

    task_rows = (
        db.query(Task.id, Task.business_id, Task.mode, Task.model)
        .filter(Task.id.in_(task_ids))
        .all()
    )
    tasks = [
        _CreditLogTaskSnapshot(
            id=task_id,
            business_id=business_id,
            mode=mode,
            model=model,
        )
        for task_id, business_id, mode, model in task_rows
    ]
    scene_type_map = get_task_scene_type_subset(
        db,
        {
            (task.model or "").strip()
            for task in tasks
            if (task.model or "").strip()
        },
    )
    task_cache = {task.id: task for task in tasks}
    task_modes = {
        task.id: resolve_task_type(
            mode=task.mode,
            model=task.model,
            scene_type_map=scene_type_map,
        )
        for task in tasks
    }
    return task_cache, task_modes


def _serialize_credit_logs_page(db: Session, logs: list[CreditLog]) -> list[dict]:
    if not logs:
        return []

    task_cache, task_modes = _get_credit_log_task_context(db, logs)
    related_user_ids = {
        int(user_id)
        for user_id in [
            *(log.user_id for log in logs if log.user_id),
            *(log.operator_id for log in logs if log.operator_id),
        ]
        if user_id
    }
    user_cache = {
        user.id: user
        for user in db.query(User).filter(User.id.in_(related_user_ids)).all()
    } if related_user_ids else {}

    items = []
    for log in logs:
        target_user = user_cache.get(log.user_id)
        operator = user_cache.get(log.operator_id) if log.operator_id else None
        items.append({
            "id": log.id,
            "user_id": user_external_id(target_user) if target_user else "",
            "username": target_user.username if target_user else "",
            "amount": log.amount,
            "type": log.type,
            "mode": _resolve_credit_log_mode(log, task_modes),
            "description": log.description,
            "operator_name": operator.username if operator else "",
            "task_id": task_external_id(task_cache.get(log.task_id)) if log.task_id and task_cache.get(log.task_id) else None,
            "created_at": log.created_at,
        })
    return items


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
    if direction == "increase":
        query = query.filter(CreditLog.amount > 0)
    elif direction == "decrease":
        query = query.filter(CreditLog.amount < 0)

    if mode:
        query = _apply_credit_log_mode_filter(query, db, mode)

    total = int(query.count() or 0)
    paged_logs = (
        query
        .order_by(CreditLog.created_at.desc(), CreditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "total": total,
        "items": _serialize_credit_logs_page(db, paged_logs),
    }


def list_payment_orders(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    user_keyword: str | None = None,
    status_filter: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    query = db.query(PaymentOrder, User).join(User, User.id == PaymentOrder.user_id)
    keyword = (user_keyword or "").strip()
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            (User.username.ilike(like))
            | (User.email.ilike(like))
            | (User.business_id.ilike(like))
            | (PaymentOrder.order_no.ilike(like))
            | (PaymentOrder.alipay_trade_no.ilike(like))
        )
    if status_filter:
        query = query.filter(PaymentOrder.status == status_filter)
    if start_date:
        query = query.filter(PaymentOrder.created_at >= start_date)
    if end_date:
        query = query.filter(PaymentOrder.created_at <= end_date)

    total = query.count()
    rows = (
        query
        .order_by(PaymentOrder.created_at.desc(), PaymentOrder.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for order, user in rows:
        items.append(
            {
                "id": order.id,
                "order_no": order.order_no,
                "out_trade_no": order.out_trade_no,
                "alipay_trade_no": order.alipay_trade_no or "",
                "user_id": user_external_id(user),
                "username": user.username,
                "user_email": user.email or "",
                "plan_key": order.plan_key,
                "subject": order.subject,
                "amount_fen": int(order.amount_fen or 0),
                "amount_yuan": round(int(order.amount_fen or 0) / 100, 2),
                "credits": int(order.credits or 0),
                "status": order.status,
                "trade_status": order.trade_status or "",
                "buyer_id": order.buyer_id or "",
                "paid_at": order.paid_at,
                "credited_at": order.credited_at,
                "closed_at": order.closed_at,
                "failed_at": order.failed_at,
                "created_at": order.created_at,
                "updated_at": order.updated_at,
            }
        )
    return {"total": total, "items": items}


def get_admin_invite_reward_dashboard(db: Session) -> dict:
    invitee_alias = aliased(User)
    referral_count = (
        db.query(func.count(User.id))
        .filter(User.referrer_id.is_not(None), User.used_promo_code_id.is_(None))
        .scalar()
        or 0
    )
    reward_summary = (
        db.query(
            func.count(ReferralRewardGrant.id),
            func.count(func.distinct(ReferralRewardGrant.referrer_id)),
            func.count(func.distinct(ReferralRewardGrant.invitee_id)),
            func.coalesce(func.sum(ReferralRewardGrant.source_credits), 0),
            func.coalesce(func.sum(ReferralRewardGrant.reward_credits), 0),
        )
        .join(invitee_alias, invitee_alias.id == ReferralRewardGrant.invitee_id)
        .filter(invitee_alias.used_promo_code_id.is_(None))
        .first()
    )
    payment_reward_count = (
        db.query(func.count(ReferralRewardGrant.id))
        .join(invitee_alias, invitee_alias.id == ReferralRewardGrant.invitee_id)
        .filter(ReferralRewardGrant.source_type == "payment", invitee_alias.used_promo_code_id.is_(None))
        .scalar()
        or 0
    )
    redeem_reward_count = (
        db.query(func.count(ReferralRewardGrant.id))
        .join(invitee_alias, invitee_alias.id == ReferralRewardGrant.invitee_id)
        .filter(ReferralRewardGrant.source_type == "redeem", invitee_alias.used_promo_code_id.is_(None))
        .scalar()
        or 0
    )

    referral_rows = (
        db.query(User.referrer_id, func.count(User.id))
        .filter(User.referrer_id.is_not(None), User.used_promo_code_id.is_(None))
        .group_by(User.referrer_id)
        .all()
    )
    referral_count_map = {int(referrer_id): int(count or 0) for referrer_id, count in referral_rows if referrer_id}

    reward_rows = (
        db.query(
            ReferralRewardGrant.referrer_id,
            func.count(ReferralRewardGrant.id),
            func.count(func.distinct(ReferralRewardGrant.invitee_id)),
            func.coalesce(func.sum(ReferralRewardGrant.source_credits), 0),
            func.coalesce(func.sum(ReferralRewardGrant.reward_credits), 0),
            func.max(ReferralRewardGrant.created_at),
        )
        .join(invitee_alias, invitee_alias.id == ReferralRewardGrant.invitee_id)
        .filter(invitee_alias.used_promo_code_id.is_(None))
        .group_by(ReferralRewardGrant.referrer_id)
        .all()
    )
    reward_map = {
        int(referrer_id): {
            "reward_grant_count": int(reward_grant_count or 0),
            "rewarded_invitees": int(rewarded_invitees or 0),
            "source_credits": int(source_credits or 0),
            "reward_credits": int(reward_credits or 0),
            "last_reward_at": last_reward_at,
        }
        for referrer_id, reward_grant_count, rewarded_invitees, source_credits, reward_credits, last_reward_at in reward_rows
        if referrer_id
    }

    referrer_ids = sorted(set(referral_count_map) | set(reward_map))
    users = db.query(User).filter(User.id.in_(referrer_ids)).all() if referrer_ids else []
    user_map = {user.id: user for user in users}
    user_items = []
    for referrer_id in referrer_ids:
        user = user_map.get(referrer_id)
        if not user:
            continue
        rewards = reward_map.get(referrer_id, {})
        user_items.append(
            {
                "user_id": user_external_id(user),
                "username": user.username,
                "email": user.email or "",
                "invite_code": user.invite_code or "",
                "total_referrals": referral_count_map.get(referrer_id, 0),
                "rewarded_invitees": int(rewards.get("rewarded_invitees") or 0),
                "reward_grant_count": int(rewards.get("reward_grant_count") or 0),
                "source_credits": int(rewards.get("source_credits") or 0),
                "reward_credits": int(rewards.get("reward_credits") or 0),
                "last_reward_at": rewards.get("last_reward_at"),
                "created_at": user.created_at,
            }
        )
    user_items.sort(key=lambda item: (item["reward_credits"], item["total_referrals"]), reverse=True)

    recent_rows = (
        db.query(ReferralRewardGrant, User, invitee_alias)
        .join(User, User.id == ReferralRewardGrant.referrer_id)
        .join(invitee_alias, invitee_alias.id == ReferralRewardGrant.invitee_id)
        .filter(invitee_alias.used_promo_code_id.is_(None))
        .order_by(ReferralRewardGrant.created_at.desc(), ReferralRewardGrant.id.desc())
        .limit(100)
        .all()
    )
    recent_logs = []
    for grant, referrer, invitee in recent_rows:
        recent_logs.append(
            {
                "id": grant.id,
                "referrer_user_id": user_external_id(referrer),
                "referrer_username": referrer.username,
                "invitee_user_id": user_external_id(invitee),
                "invitee_username": invitee.username,
                "source_type": grant.source_type,
                "source_id": grant.source_id,
                "source_credits": int(grant.source_credits or 0),
                "reward_rate": int(grant.reward_rate or 0),
                "reward_credits": int(grant.reward_credits or 0),
                "reward_index": int(grant.reward_index or 0),
                "created_at": grant.created_at,
            }
        )

    reward_grant_count, rewarded_referrers, rewarded_invitees, source_credits, reward_credits = reward_summary
    return {
        "summary": {
            "total_referrals": int(referral_count),
            "rewarded_referrers": int(rewarded_referrers or 0),
            "rewarded_invitees": int(rewarded_invitees or 0),
            "reward_grant_count": int(reward_grant_count or 0),
            "source_credits": int(source_credits or 0),
            "reward_credits": int(reward_credits or 0),
            "payment_reward_count": int(payment_reward_count),
            "redeem_reward_count": int(redeem_reward_count),
        },
        "users": user_items,
        "recent_logs": recent_logs,
    }


def get_admin_invite_reward_user_detail(db: Session, user_id: str) -> dict:
    target_user = get_user_by_business_id(db, user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    referrals = (
        db.query(User)
        .filter(User.referrer_id == target_user.id, User.used_promo_code_id.is_(None))
        .order_by(User.created_at.desc(), User.id.desc())
        .all()
    )
    invitee_ids = [user.id for user in referrals]
    reward_map: dict[int, dict] = {}
    if invitee_ids:
        reward_rows = (
            db.query(
                ReferralRewardGrant.invitee_id,
                func.count(ReferralRewardGrant.id),
                func.coalesce(func.sum(ReferralRewardGrant.reward_credits), 0),
                func.max(ReferralRewardGrant.created_at),
            )
            .filter(
                ReferralRewardGrant.referrer_id == target_user.id,
                ReferralRewardGrant.invitee_id.in_(invitee_ids),
            )
            .group_by(ReferralRewardGrant.invitee_id)
            .all()
        )
        reward_map = {
            int(invitee_id): {
                "reward_count": int(reward_count or 0),
                "reward_credits": int(reward_credits or 0),
                "last_reward_at": last_reward_at,
            }
            for invitee_id, reward_count, reward_credits, last_reward_at in reward_rows
            if invitee_id
        }

    referral_items = []
    for invitee in referrals:
        rewards = reward_map.get(invitee.id, {})
        referral_items.append(
            {
                "user_id": user_external_id(invitee),
                "username": invitee.username,
                "email": invitee.email or "",
                "reward_count": int(rewards.get("reward_count") or 0),
                "reward_credits": int(rewards.get("reward_credits") or 0),
                "last_reward_at": rewards.get("last_reward_at"),
                "registered_at": invitee.created_at,
            }
        )

    invitee_alias = aliased(User)
    log_rows = (
        db.query(ReferralRewardGrant, invitee_alias)
        .join(invitee_alias, invitee_alias.id == ReferralRewardGrant.invitee_id)
        .filter(ReferralRewardGrant.referrer_id == target_user.id, invitee_alias.used_promo_code_id.is_(None))
        .order_by(ReferralRewardGrant.created_at.desc(), ReferralRewardGrant.id.desc())
        .all()
    )
    reward_logs = [
        {
            "id": grant.id,
            "invitee_user_id": user_external_id(invitee),
            "invitee_username": invitee.username,
            "invitee_email": invitee.email or "",
            "source_type": grant.source_type,
            "source_id": grant.source_id,
            "source_credits": int(grant.source_credits or 0),
            "reward_rate": int(grant.reward_rate or 0),
            "reward_credits": int(grant.reward_credits or 0),
            "reward_index": int(grant.reward_index or 0),
            "created_at": grant.created_at,
        }
        for grant, invitee in log_rows
    ]

    total_reward_credits = sum(item["reward_credits"] for item in reward_logs)
    total_source_credits = sum(item["source_credits"] for item in reward_logs)
    rewarded_invitees = len({item["invitee_user_id"] for item in reward_logs})
    return {
        "user": {
            "user_id": user_external_id(target_user),
            "username": target_user.username,
            "email": target_user.email or "",
            "invite_code": target_user.invite_code or "",
            "created_at": target_user.created_at,
        },
        "summary": {
            "total_referrals": len(referral_items),
            "rewarded_invitees": rewarded_invitees,
            "reward_grant_count": len(reward_logs),
            "source_credits": int(total_source_credits),
            "reward_credits": int(total_reward_credits),
        },
        "referrals": referral_items,
        "reward_logs": reward_logs,
    }


def get_admin_promo_stats_dashboard(db: Session, *, month: str | None = None) -> dict:
    selected_month, month_start, month_end = parse_reward_month(month or current_reward_month())
    whitelisted_users = (
        db.query(func.count(User.id)).filter(User.is_whitelisted.is_(True)).scalar() or 0
    )
    total_promo_codes = db.query(func.count(UserPromoCode.id)).scalar() or 0

    promo_codes = db.query(UserPromoCode).all()
    owner_promo_ids: dict[int, list[int]] = defaultdict(list)
    promo_id_to_owner: dict[int, int] = {}
    for promo in promo_codes:
        owner_promo_ids[int(promo.user_id)].append(int(promo.id))
        promo_id_to_owner[int(promo.id)] = int(promo.user_id)

    promo_referral_rows = (
        db.query(User.used_promo_code_id, func.count(User.id))
        .filter(User.used_promo_code_id.is_not(None))
        .group_by(User.used_promo_code_id)
        .all()
    )
    promo_referral_map = {
        int(promo_id): int(count or 0)
        for promo_id, count in promo_referral_rows
        if promo_id
    }
    used_promo_codes = sum(1 for count in promo_referral_map.values() if count > 0)

    referred_users = (
        db.query(User)
        .filter(User.used_promo_code_id.is_not(None))
        .order_by(User.created_at.desc(), User.id.desc())
        .all()
    )
    total_referrals = len(referred_users)

    owner_referral_map: dict[int, int] = defaultdict(int)
    owner_last_referral: dict[int, datetime | None] = {}
    invitee_to_owner: dict[int, int] = {}
    for invitee in referred_users:
        owner_id = promo_id_to_owner.get(int(invitee.used_promo_code_id or 0)) or (
            int(invitee.referrer_id) if invitee.referrer_id else None
        )
        if not owner_id:
            continue
        owner_referral_map[owner_id] += 1
        invitee_to_owner[int(invitee.id)] = owner_id
        previous = owner_last_referral.get(owner_id)
        if previous is None or (
            invitee.created_at is not None and (previous is None or invitee.created_at > previous)
        ):
            owner_last_referral[owner_id] = invitee.created_at

    all_invitee_ids = list(invitee_to_owner.keys())
    purchase_count = 0
    purchase_credits = 0
    redeem_count = 0
    redeem_credits = 0
    owner_purchase_credits: dict[int, int] = defaultdict(int)
    owner_redeem_credits: dict[int, int] = defaultdict(int)
    owner_reward_amount_fen: dict[int, int] = defaultdict(int)
    owner_reward_grant_count: dict[int, int] = defaultdict(int)
    owner_month_reward_amount_fen: dict[int, int] = defaultdict(int)
    owner_month_reward_grant_count: dict[int, int] = defaultdict(int)
    rebate_rows = (
        db.query(
            PromoRewardGrant.referrer_id,
            func.count(PromoRewardGrant.id),
            func.coalesce(func.sum(PromoRewardGrant.reward_amount_fen), 0),
        )
        .group_by(PromoRewardGrant.referrer_id)
        .all()
    )
    for referrer_id, grant_count, amount_fen in rebate_rows:
        if not referrer_id:
            continue
        owner_reward_grant_count[int(referrer_id)] = int(grant_count or 0)
        owner_reward_amount_fen[int(referrer_id)] = int(amount_fen or 0)
    total_reward_amount_fen = sum(owner_reward_amount_fen.values())
    total_reward_grant_count = sum(owner_reward_grant_count.values())
    month_rebate_rows = (
        db.query(
            PromoRewardGrant.referrer_id,
            func.count(PromoRewardGrant.id),
            func.coalesce(func.sum(PromoRewardGrant.reward_amount_fen), 0),
        )
        .filter(
            PromoRewardGrant.created_at >= month_start,
            PromoRewardGrant.created_at < month_end,
        )
        .group_by(PromoRewardGrant.referrer_id)
        .all()
    )
    for referrer_id, grant_count, amount_fen in month_rebate_rows:
        if not referrer_id:
            continue
        owner_month_reward_grant_count[int(referrer_id)] = int(grant_count or 0)
        owner_month_reward_amount_fen[int(referrer_id)] = int(amount_fen or 0)
    month_reward_amount_fen = sum(owner_month_reward_amount_fen.values())
    month_reward_grant_count = sum(owner_month_reward_grant_count.values())
    if all_invitee_ids:
        payment_rows = (
            db.query(
                PaymentOrder.user_id,
                func.count(PaymentOrder.id),
                func.coalesce(func.sum(PaymentOrder.credits), 0),
            )
            .filter(
                PaymentOrder.user_id.in_(all_invitee_ids),
                PaymentOrder.credited_at.is_not(None),
            )
            .group_by(PaymentOrder.user_id)
            .all()
        )
        for user_id, count, credits in payment_rows:
            purchase_count += int(count or 0)
            purchase_credits += int(credits or 0)
            owner_id = invitee_to_owner.get(int(user_id))
            if owner_id:
                owner_purchase_credits[owner_id] += int(credits or 0)

        redeem_rows = (
            db.query(
                CreditRedeemKey.used_by_user_id,
                func.count(CreditRedeemKey.id),
                func.coalesce(func.sum(CreditRedeemKey.credit_amount), 0),
            )
            .filter(
                CreditRedeemKey.used_by_user_id.in_(all_invitee_ids),
                CreditRedeemKey.used_at.is_not(None),
            )
            .group_by(CreditRedeemKey.used_by_user_id)
            .all()
        )
        for user_id, count, credits in redeem_rows:
            redeem_count += int(count or 0)
            redeem_credits += int(credits or 0)
            owner_id = invitee_to_owner.get(int(user_id))
            if owner_id:
                owner_redeem_credits[owner_id] += int(credits or 0)

    promoter_ids = sorted(set(owner_promo_ids) | set(owner_referral_map))
    users = db.query(User).filter(User.id.in_(promoter_ids)).all() if promoter_ids else []
    user_map = {user.id: user for user in users}
    user_items = []
    active_promoters = 0
    for owner_id in promoter_ids:
        user = user_map.get(owner_id)
        if not user:
            continue
        promo_ids = owner_promo_ids.get(owner_id, [])
        used_code_count = sum(1 for promo_id in promo_ids if promo_referral_map.get(promo_id, 0) > 0)
        referrals = int(owner_referral_map.get(owner_id, 0))
        if referrals > 0:
            active_promoters += 1
        user_items.append(
            {
                "user_id": user_external_id(user),
                "username": user.username,
                "email": user.email or "",
                "is_whitelisted": bool(user.is_whitelisted),
                "promo_code_count": len(promo_ids),
                "used_code_count": used_code_count,
                "total_referrals": referrals,
                "reward_credits": referrals * PROMO_CODE_REWARD_CREDITS,
                "purchase_credits": int(owner_purchase_credits.get(owner_id, 0)),
                "redeem_credits": int(owner_redeem_credits.get(owner_id, 0)),
                "reward_grant_count": int(owner_reward_grant_count.get(owner_id, 0)),
                "total_reward_amount_yuan": fen_to_yuan(owner_reward_amount_fen.get(owner_id, 0)),
                "month_reward_grant_count": int(owner_month_reward_grant_count.get(owner_id, 0)),
                "month_reward_amount_yuan": fen_to_yuan(owner_month_reward_amount_fen.get(owner_id, 0)),
                "last_referral_at": owner_last_referral.get(owner_id),
                "created_at": user.created_at,
            }
        )
    user_items.sort(key=lambda item: (item["total_referrals"], item["reward_credits"]), reverse=True)

    promoter_alias = aliased(User)
    recent_rows = (
        db.query(User, UserPromoCode, promoter_alias)
        .join(UserPromoCode, UserPromoCode.id == User.used_promo_code_id)
        .join(promoter_alias, promoter_alias.id == UserPromoCode.user_id)
        .order_by(User.created_at.desc(), User.id.desc())
        .limit(100)
        .all()
    )
    recent_referrals = [
        {
            "id": invitee.id,
            "promoter_user_id": user_external_id(promoter),
            "promoter_username": promoter.username,
            "invitee_user_id": user_external_id(invitee),
            "invitee_username": invitee.username,
            "promo_code": promo.code,
            "platform_name": promo.platform_name or "",
            "reward_credits": PROMO_CODE_REWARD_CREDITS,
            "registered_at": invitee.created_at,
        }
        for invitee, promo, promoter in recent_rows
    ]

    return {
        "summary": {
            "total_referrals": int(total_referrals),
            "active_promoters": int(active_promoters),
            "total_promo_codes": int(total_promo_codes),
            "used_promo_codes": int(used_promo_codes),
            "whitelisted_users": int(whitelisted_users),
            "reward_credits": int(total_referrals * PROMO_CODE_REWARD_CREDITS),
            "purchase_count": int(purchase_count),
            "purchase_credits": int(purchase_credits),
            "redeem_count": int(redeem_count),
            "redeem_credits": int(redeem_credits),
            "reward_grant_count": int(total_reward_grant_count),
            "total_reward_amount_yuan": fen_to_yuan(total_reward_amount_fen),
            "month": selected_month,
            "month_reward_grant_count": int(month_reward_grant_count),
            "month_reward_amount_yuan": fen_to_yuan(month_reward_amount_fen),
            "start_at": promo_rebate_start_at(),
        },
        "users": user_items,
        "recent_referrals": recent_referrals,
    }


def get_admin_promo_stats_user_detail(
    db: Session,
    user_id: str,
    *,
    month: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    target_user = get_user_by_business_id(db, user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return get_user_promo_dashboard_for_admin(
        db,
        target_user,
        require_whitelist=False,
        month=month,
        start_date=start_date,
        end_date=end_date,
    )


def get_stats(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    total_users = db.query(func.count(User.id)).filter(*_analytics_user_filter()).scalar()
    total_remain_credits = (
        db.query(func.coalesce(func.sum(UserCredit.remain_credit), 0))
        .join(User, User.id == UserCredit.user_id)
        .filter(
            *_analytics_user_filter(),
            UserCredit.type == DEFAULT_CREDIT_TYPE,
            UserCredit.status == DEFAULT_USER_CREDIT_STATUS,
        )
        .scalar()
    )
    total_generation_tasks = (
        db.query(func.count(Task.id))
        .join(User, User.id == Task.user_id)
        .filter(*_analytics_user_filter(), _exclude_example_template_seed_task_clause())
        .scalar()
    )
    total_prompt_reverse_tasks = (
        db.query(func.count(CreditLog.id))
        .join(User, User.id == CreditLog.user_id)
        .filter(
            CreditLog.type == "consume",
            CreditLog.description.in_(_credit_log_prompt_tool_descriptions()),
            *_analytics_user_filter(),
        )
        .scalar()
    )
    total_generation_credit_cost = (
        db.query(func.coalesce(func.sum(Task.credit_cost), 0))
        .join(User, User.id == Task.user_id)
        .filter(*_analytics_user_filter(), _exclude_example_template_seed_task_clause())
        .scalar()
    )
    total_refunded_generation_credit = (
        db.query(func.coalesce(func.sum(CreditLog.amount), 0))
        .join(User, User.id == CreditLog.user_id)
        .filter(
            CreditLog.type == "allocate",
            CreditLog.task_id.is_not(None),
            CreditLog.description.in_(TASK_CREDIT_REFUND_DESCRIPTIONS),
            *_analytics_user_filter(),
        )
        .scalar()
    )
    total_prompt_reverse_credit_cost = (
        db.query(func.coalesce(func.sum(-CreditLog.amount), 0))
        .join(User, User.id == CreditLog.user_id)
        .filter(
            CreditLog.type == "consume",
            CreditLog.description.in_(_credit_log_prompt_tool_descriptions()),
            *_analytics_user_filter(),
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
                *_analytics_user_filter(),
                _exclude_example_template_seed_task_clause(),
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
                CreditLog.description.in_(_credit_log_prompt_tool_descriptions()),
                CreditLog.created_at >= now - timedelta(days=7),
                *_analytics_user_filter(),
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


_HOUR_GRANULARITY_BUCKETS = {
    "1hour": 1,
    "3hour": 3,
    "6hour": 6,
}


def _hour_bucket_size(granularity: str) -> int | None:
    return _HOUR_GRANULARITY_BUCKETS.get(granularity)


def _start_of_hour_bucket(value: datetime, hours: int) -> datetime:
    value = _to_local_datetime(value)
    return value.replace(hour=(value.hour // hours) * hours, minute=0, second=0, microsecond=0)


def _end_of_hour_bucket(value: datetime, hours: int) -> datetime:
    start = _start_of_hour_bucket(value, hours)
    return start + timedelta(hours=hours) - timedelta(microseconds=1)


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
        hour_bucket_size = _hour_bucket_size(granularity)
        if hour_bucket_size:
            end = _end_of_hour_bucket(now, hour_bucket_size)
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

    hour_bucket_size = _hour_bucket_size(granularity)
    if hour_bucket_size:
        start = _start_of_hour_bucket(start_date, hour_bucket_size)
        end = _end_of_hour_bucket(end_date, hour_bucket_size)
    elif granularity == "3hour":
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
        hour_bucket_size = _hour_bucket_size(granularity)
        if hour_bucket_size:
            cursor += timedelta(hours=hour_bucket_size)
        elif granularity == "3hour":
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
    hour_bucket_size = _hour_bucket_size(granularity)
    if hour_bucket_size:
        previous_start = start - timedelta(hours=hour_bucket_size * bucket_count)
    elif granularity == "3hour":
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
    hour_bucket_size = _hour_bucket_size(granularity)
    if hour_bucket_size:
        return _start_of_hour_bucket(value, hour_bucket_size)
    if granularity == "3hour":
        return _start_of_3hour(value)
    if granularity == "day":
        return _start_of_day(value)
    if granularity == "week":
        return _start_of_week(value)
    return _start_of_month(value)


def _bucket_end(value: datetime, granularity: str) -> datetime:
    hour_bucket_size = _hour_bucket_size(granularity)
    if hour_bucket_size:
        return _end_of_hour_bucket(value, hour_bucket_size)
    if granularity == "3hour":
        return _end_of_3hour(value)
    if granularity == "day":
        return _end_of_day(value)
    if granularity == "week":
        return _end_of_week(value)
    return _end_of_month(value)


def _bucket_label(value: datetime, granularity: str) -> str:
    if _hour_bucket_size(granularity) or granularity == "3hour":
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
    canvas_task_filter: str | None = None,
    include_unsafe_tasks: bool = True,
    include_restricted_users: bool = False,
):
    user_filters = (User.role != "superadmin",) if include_restricted_users else _analytics_user_filter()
    query = db.query(Task).join(User, User.id == Task.user_id).filter(
        Task.created_at >= _to_db_datetime(start_date),
        Task.created_at <= _to_db_datetime(end_date),
        *user_filters,
        _exclude_example_template_seed_task_clause(),
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
    if canvas_task_filter == "canvas":
        query = query.filter(Task.canvas_id.is_not(None))
    elif canvas_task_filter == "non_canvas":
        query = query.filter(Task.canvas_id.is_(None))
    if not include_unsafe_tasks:
        query = query.filter(build_exclude_content_safety_failed_task_clause(Task.status, Task.error_message))
    if mode:
        if mode == TASK_TYPE_INPAINT:
            query = query.filter((Task.mode == "inpaint") | (Task.model == "inpaint"))
        elif mode == TASK_TYPE_SMART_CUTOUT:
            query = query.filter((Task.mode == "smart_cutout") | (Task.model == "smart_cutout"))
        elif mode == TASK_TYPE_TEXT_GENERATE:
            text_generate_models = [key for key, value in scene_type_map.items() if value == "generate"]
            query = query.filter(Task.mode == "generate")
            query = query.filter(Task.model.in_(text_generate_models)) if text_generate_models else query.filter(Task.id.is_(None))
        elif mode == TASK_TYPE_IMAGE_EDIT:
            image_edit_models = [key for key, value in scene_type_map.items() if value == "image_edit"]
            query = query.filter(Task.mode == "generate")
            query = query.filter(Task.model.in_(image_edit_models)) if image_edit_models else query.filter(Task.id.is_(None))
        elif mode in {TASK_TYPE_PROMPT_REVERSE, TASK_TYPE_PROMPT_OPTIMIZE}:
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
    canvas_task_filter: str | None = None,
):
    if status_filter and status_filter != "success":
        return None
    if mode and mode not in {TASK_TYPE_PROMPT_REVERSE, TASK_TYPE_PROMPT_OPTIMIZE}:
        return None
    if model and model not in {PROMPT_REVERSE_MODEL, PROMPT_OPTIMIZE_MODEL}:
        return None
    if source and source != "web":
        return None
    if canvas_task_filter == "canvas":
        return None

    query = db.query(CreditLog).join(User, User.id == CreditLog.user_id).filter(
        CreditLog.type == "consume",
        CreditLog.description.in_(_credit_log_prompt_tool_descriptions()),
        CreditLog.created_at >= _to_db_datetime(start_date),
        CreditLog.created_at <= _to_db_datetime(end_date),
        *_analytics_user_filter(),
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
    query = db.query(User).filter(*_analytics_user_filter())
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
    canvas_task_filter: str | None = None,
    include_unsafe_tasks: bool = True,
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
        canvas_task_filter=canvas_task_filter,
        include_unsafe_tasks=include_unsafe_tasks,
    ).all()
    refunded_task_ids = _get_refunded_task_ids(db, [task.id for task in tasks])
    attempt_duration_ms_map = _task_attempt_duration_ms_map(db, [task.id for task in tasks])
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
            used_fallback_api=bool(task.used_fallback_api),
            from_canvas=bool(getattr(task, "canvas_id", None)),
            duration_seconds=_task_duration_seconds(
                task,
                attempt_duration_ms_map.get(int(task.id)),
            ),
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
        canvas_task_filter=canvas_task_filter,
    )
    prompt_reverse_records = []
    if prompt_reverse_query is not None:
        prompt_reverse_records = [
            AnalyticsRecord(
                user_id=log.user_id,
                status="success",
                source="web",
                model=(
                    PROMPT_OPTIMIZE_MODEL
                    if log.description in set(_credit_log_prompt_optimize_descriptions())
                    else PROMPT_REVERSE_MODEL
                ),
                mode=(
                    PROMPT_OPTIMIZE_MODE
                    if log.description in set(_credit_log_prompt_optimize_descriptions())
                    else PROMPT_REVERSE_MODE
                ),
                task_type=(
                    TASK_TYPE_PROMPT_OPTIMIZE
                    if log.description in set(_credit_log_prompt_optimize_descriptions())
                    else TASK_TYPE_PROMPT_REVERSE
                ),
                credit_cost=max(0, int(-(log.amount or 0))),
                created_at=log.created_at,
                used_fallback_api=False,
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


def _fallback_summary_metrics(records: list[AnalyticsRecord]) -> dict[str, int]:
    fallback_records = [record for record in records if record.used_fallback_api]
    return {
        "fallback_task_total": len(fallback_records),
        "fallback_success_tasks": sum(1 for record in fallback_records if record.status == "success"),
        "fallback_failed_tasks": sum(1 for record in fallback_records if record.status == "failed"),
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
    canvas_task_filter: str | None = None,
    status_filter: str | None = None,
    include_unsafe_tasks: bool = True,
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
        canvas_task_filter=canvas_task_filter,
        include_unsafe_tasks=include_unsafe_tasks,
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
        canvas_task_filter=canvas_task_filter,
        include_unsafe_tasks=include_unsafe_tasks,
    )

    current_metrics = _task_summary_metrics(current_records)
    previous_metrics = _task_summary_metrics(previous_records)
    current_fallback_metrics = _fallback_summary_metrics(current_records)
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
        "fallback_task_total": current_fallback_metrics["fallback_task_total"],
        "fallback_success_tasks": current_fallback_metrics["fallback_success_tasks"],
        "fallback_failed_tasks": current_fallback_metrics["fallback_failed_tasks"],
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
    canvas_task_filter: str | None = None,
    status_filter: str | None = None,
    include_unsafe_tasks: bool = True,
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
        canvas_task_filter=canvas_task_filter,
        include_unsafe_tasks=include_unsafe_tasks,
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
        canvas_task_filter=canvas_task_filter,
        include_unsafe_tasks=include_unsafe_tasks,
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


def _model_compare_rows(
    items: dict[str, dict[str, int]],
    limit: int = 10,
    duration_map: dict[str, tuple[float, int]] | None = None,
) -> list[dict]:
    duration_map = duration_map or {}
    rows: list[dict] = []
    for name, payload in items.items():
        count = int(payload.get("count") or 0)
        success_count = int(payload.get("success_count") or 0)
        failed_count = int(payload.get("failed_count") or 0)
        credit_cost = int(payload.get("credit_cost") or 0)
        mapped_avg, mapped_count = duration_map.get(name, (0.0, 0))
        duration_count = int(mapped_count or payload.get("duration_count") or 0)
        duration_total = float(payload.get("duration_total") or 0)
        avg_duration_seconds = (
            float(mapped_avg)
            if mapped_count
            else (round(duration_total / duration_count, 1) if duration_count else 0.0)
        )
        rows.append({
            "name": name,
            "count": count,
            "success_count": success_count,
            "failed_count": failed_count,
            "success_rate": round((success_count / count) * 100, 1) if count else 0.0,
            "credit_cost": credit_cost,
            "avg_credit_cost": round(credit_cost / count, 1) if count else 0.0,
            "duration_count": duration_count,
            "avg_duration_seconds": avg_duration_seconds,
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
    canvas_task_filter: str | None = None,
    include_unsafe_tasks: bool = True,
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
            canvas_task_filter=canvas_task_filter,
            include_unsafe_tasks=include_unsafe_tasks,
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
    canvas_task_filter: str | None = None,
    status_filter: str | None = None,
    include_unsafe_tasks: bool = True,
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
        canvas_task_filter=canvas_task_filter,
        include_unsafe_tasks=include_unsafe_tasks,
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
        lambda: {
            "count": 0,
            "credit_cost": 0,
            "success_count": 0,
            "failed_count": 0,
            "duration_total": 0,
            "duration_count": 0,
        }
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
        if record.duration_seconds:
            model_breakdown[model_key]["duration_total"] += float(record.duration_seconds)
            model_breakdown[model_key]["duration_count"] += 1

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
        "model_compare": _model_compare_rows(
            model_breakdown,
            limit=10,
            duration_map=_model_avg_run_time_map(
                db,
                start_date=current_start,
                end_date=current_end,
                status_filter=status_filter,
                user_id=user_id,
                source=source,
                model=model,
                mode=mode,
                canvas_task_filter=canvas_task_filter,
                include_unsafe_tasks=include_unsafe_tasks,
            ),
        ),
        "api_attempt_performance": _api_attempt_performance_rows(
            db,
            start_date=current_start,
            end_date=current_end,
            status_filter=status_filter,
            user_id=user_id,
            source=source,
            model=model,
            mode=mode,
            canvas_task_filter=canvas_task_filter,
            include_unsafe_tasks=include_unsafe_tasks,
        ),
        "top_users_by_tasks": top_users_by_tasks,
        "top_users_by_credit": top_users_by_credit[:10],
    }


def _video_task_type_for_task(task: VideoTask) -> str:
    generation_mode = (getattr(task, "generation_mode", "") or "").strip()
    if generation_mode in {
        VIDEO_TASK_TYPE_TEXT_TO_VIDEO,
        VIDEO_TASK_TYPE_IMAGE_TO_VIDEO,
        VIDEO_TASK_TYPE_FIRST_LAST_FRAME,
    }:
        return generation_mode
    reference_images = (task.reference_images or "").strip()
    if reference_images and reference_images != "[]":
        return VIDEO_TASK_TYPE_IMAGE_TO_VIDEO
    return VIDEO_TASK_TYPE_TEXT_TO_VIDEO


def _get_refunded_video_task_ids(db: Session, task_ids: list[int]) -> set[int]:
    normalized_ids = [int(task_id) for task_id in task_ids if task_id]
    if not normalized_ids:
        return set()
    rows = (
        db.query(CreditLog.description)
        .filter(
            CreditLog.type == "allocate",
            or_(
                CreditLog.description.like(f"{VIDEO_TASK_FAILURE_REFUND_PREFIX} %"),
                CreditLog.description.like(f"{VIDEO_TASK_ENQUEUE_REFUND_PREFIX} %"),
            ),
        )
        .all()
    )
    refunded_business_ids = {
        (description or "").rsplit(" ", 1)[-1].strip()
        for (description,) in rows
        if description and " " in description
    }
    if not refunded_business_ids:
        return set()
    return {
        int(task.id)
        for task in db.query(VideoTask.id, VideoTask.business_id).filter(VideoTask.id.in_(normalized_ids)).all()
        if (task.business_id or "") in refunded_business_ids
    }


def get_video_stats(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    base_query = (
        db.query(VideoTask)
        .join(User, User.id == VideoTask.user_id)
        .filter(*_analytics_user_filter())
    )
    total_tasks = base_query.count()
    refunded_video_task_ids = _get_refunded_video_task_ids(db, [task_id for (task_id,) in base_query.with_entities(VideoTask.id).all()])
    total_credit_cost = sum(
        max(0, int(task.credit_cost or 0) - (int(task.credit_cost or 0) if task.id in refunded_video_task_ids else 0))
        for task in base_query.with_entities(VideoTask.id, VideoTask.credit_cost).all()
    )
    total_users = (
        db.query(func.count(func.distinct(VideoTask.user_id)))
        .join(User, User.id == VideoTask.user_id)
        .filter(*_analytics_user_filter())
        .scalar()
    )
    active_users = (
        db.query(func.count(func.distinct(VideoTask.user_id)))
        .join(User, User.id == VideoTask.user_id)
        .filter(
            *_analytics_user_filter(),
            VideoTask.created_at >= now - timedelta(days=7),
        )
        .scalar()
    )
    success_tasks = base_query.filter(VideoTask.status == "success").count()
    failed_tasks = base_query.filter(VideoTask.status == "failed").count()
    return {
        "total_users": int(total_users or 0),
        "total_tasks": int(total_tasks or 0),
        "total_credit_cost": int(total_credit_cost or 0),
        "active_users": int(active_users or 0),
        "success_tasks": int(success_tasks or 0),
        "failed_tasks": int(failed_tasks or 0),
    }


def _video_task_query(
    db: Session,
    *,
    start_date: datetime,
    end_date: datetime,
    status_filter: str | None = None,
    user_id: int | None = None,
    source: str | None = None,
    model: str | None = None,
    mode: str | None = None,
    include_unsafe_tasks: bool = True,
):
    query = db.query(VideoTask).join(User, User.id == VideoTask.user_id).filter(
        VideoTask.created_at >= _to_db_datetime(start_date),
        VideoTask.created_at <= _to_db_datetime(end_date),
        *_analytics_user_filter(),
    )
    if status_filter:
        query = query.filter(VideoTask.status == status_filter)
    if user_id:
        query = query.filter(VideoTask.user_id == user_id)
    if source:
        query = query.filter(VideoTask.source == source)
    if model:
        query = query.filter(VideoTask.model == model)
    if not include_unsafe_tasks:
        query = query.filter(build_exclude_content_safety_failed_task_clause(VideoTask.status, VideoTask.error_message))
    if mode == VIDEO_TASK_TYPE_TEXT_TO_VIDEO:
        query = query.filter(
            (VideoTask.generation_mode == VIDEO_TASK_TYPE_TEXT_TO_VIDEO)
            | (
                ((VideoTask.generation_mode == "") | (VideoTask.generation_mode.is_(None)))
                & ((VideoTask.reference_images == "") | (VideoTask.reference_images == "[]"))
            )
        )
    elif mode == VIDEO_TASK_TYPE_IMAGE_TO_VIDEO:
        query = query.filter(
            (VideoTask.generation_mode == VIDEO_TASK_TYPE_IMAGE_TO_VIDEO)
            | (
                ((VideoTask.generation_mode == "") | (VideoTask.generation_mode.is_(None)))
                & VideoTask.reference_images.is_not(None)
                & VideoTask.reference_images.notin_(["", "[]"])
            )
        )
    elif mode == VIDEO_TASK_TYPE_FIRST_LAST_FRAME:
        query = query.filter(VideoTask.generation_mode == VIDEO_TASK_TYPE_FIRST_LAST_FRAME)
    return query


def _build_video_analytics_records(
    db: Session,
    *,
    start_date: datetime,
    end_date: datetime,
    status_filter: str | None = None,
    user_id: int | None = None,
    source: str | None = None,
    model: str | None = None,
    mode: str | None = None,
    include_unsafe_tasks: bool = True,
) -> list[AnalyticsRecord]:
    tasks = _video_task_query(
        db,
        start_date=start_date,
        end_date=end_date,
        status_filter=status_filter,
        user_id=user_id,
        source=source,
        model=model,
        mode=mode,
        include_unsafe_tasks=include_unsafe_tasks,
    ).all()
    refunded_task_ids = _get_refunded_video_task_ids(db, [task.id for task in tasks])
    return [
        AnalyticsRecord(
            user_id=task.user_id,
            status=task.status or "pending",
            source=task.source or "web",
            model=task.model or "未设置",
            mode=_video_task_type_for_task(task),
            task_type=_video_task_type_for_task(task),
            credit_cost=0 if task.id in refunded_task_ids else int(task.credit_cost or 0),
            created_at=task.created_at,
            used_fallback_api=bool(task.used_fallback_api),
        )
        for task in tasks
    ]


def get_video_analytics_summary(
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
    include_unsafe_tasks: bool = True,
) -> dict:
    current_start, current_end = _align_range(granularity, start_date, end_date)
    previous_start, previous_end = _previous_range(current_start, current_end, granularity)
    current_records = _build_video_analytics_records(
        db,
        start_date=current_start,
        end_date=current_end,
        status_filter=status_filter,
        user_id=user_id,
        source=source,
        model=model,
        mode=mode,
        include_unsafe_tasks=include_unsafe_tasks,
    )
    previous_records = _build_video_analytics_records(
        db,
        start_date=previous_start,
        end_date=previous_end,
        status_filter=status_filter,
        user_id=user_id,
        source=source,
        model=model,
        mode=mode,
        include_unsafe_tasks=include_unsafe_tasks,
    )
    current_metrics = _task_summary_metrics(current_records)
    previous_metrics = _task_summary_metrics(previous_records)
    current_fallback_metrics = _fallback_summary_metrics(current_records)
    total_users = (
        db.query(func.count(func.distinct(VideoTask.user_id)))
        .join(User, User.id == VideoTask.user_id)
        .filter(*_analytics_user_filter())
        .scalar()
    )
    zero_metric = _metric_payload(0, 0)
    return {
        "granularity": granularity,
        "current_range_label": _format_range_label(current_start, current_end),
        "previous_range_label": _format_range_label(previous_start, previous_end),
        "total_users": int(total_users or 0),
        "tasks_created": _metric_payload(current_metrics["tasks_created"], previous_metrics["tasks_created"]),
        "success_tasks": _metric_payload(current_metrics["success_tasks"], previous_metrics["success_tasks"]),
        "failed_tasks": _metric_payload(current_metrics["failed_tasks"], previous_metrics["failed_tasks"]),
        "credits_consumed": _metric_payload(current_metrics["credits_consumed"], previous_metrics["credits_consumed"]),
        "new_users": zero_metric,
        "active_users": _metric_payload(current_metrics["active_users"], previous_metrics["active_users"]),
        "fallback_task_total": current_fallback_metrics["fallback_task_total"],
        "fallback_success_tasks": current_fallback_metrics["fallback_success_tasks"],
        "fallback_failed_tasks": current_fallback_metrics["fallback_failed_tasks"],
    }


def get_video_analytics_timeseries(
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
    include_unsafe_tasks: bool = True,
) -> dict:
    current_start, current_end = _align_range(granularity, start_date, end_date)
    previous_start, previous_end = _previous_range(current_start, current_end, granularity)
    current_bucket_starts = _iter_bucket_starts(current_start, current_end, granularity)
    previous_bucket_starts = _iter_bucket_starts(previous_start, previous_end, granularity)
    current_records = _build_video_analytics_records(
        db,
        start_date=current_start,
        end_date=current_end,
        status_filter=status_filter,
        user_id=user_id,
        source=source,
        model=model,
        mode=mode,
        include_unsafe_tasks=include_unsafe_tasks,
    )
    previous_records = _build_video_analytics_records(
        db,
        start_date=previous_start,
        end_date=previous_end,
        status_filter=status_filter,
        user_id=user_id,
        source=source,
        model=model,
        mode=mode,
        include_unsafe_tasks=include_unsafe_tasks,
    )
    return {
        "granularity": granularity,
        "current_range_label": _format_range_label(current_start, current_end),
        "previous_range_label": _format_range_label(previous_start, previous_end),
        "current": _build_timeseries_points(
            current_bucket_starts,
            granularity=granularity,
            records=current_records,
            users=[],
        ),
        "previous": _build_timeseries_points(
            previous_bucket_starts,
            granularity=granularity,
            records=previous_records,
            users=[],
        ),
    }


def get_video_analytics_breakdown(
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
    include_unsafe_tasks: bool = True,
) -> dict:
    current_start, current_end = _align_range(granularity, start_date, end_date)
    records = _build_video_analytics_records(
        db,
        start_date=current_start,
        end_date=current_end,
        status_filter=status_filter,
        user_id=user_id,
        source=source,
        model=model,
        mode=mode,
        include_unsafe_tasks=include_unsafe_tasks,
    )
    relevant_user_ids = {record.user_id for record in records}
    users_by_id = {
        user.id: user
        for user in db.query(User).filter(User.id.in_(relevant_user_ids)).all()
    } if relevant_user_ids else {}
    status_breakdown: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "credit_cost": 0})
    source_breakdown: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "credit_cost": 0})
    mode_breakdown: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "credit_cost": 0})
    model_breakdown: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "credit_cost": 0})
    user_task_breakdown: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "credit_cost": 0})
    for record in records:
        task_cost = record.credit_cost
        status_breakdown[record.status or "unknown"]["count"] += 1
        status_breakdown[record.status or "unknown"]["credit_cost"] += task_cost
        source_breakdown[record.source or "web"]["count"] += 1
        source_breakdown[record.source or "web"]["credit_cost"] += task_cost
        mode_breakdown[record.task_type or VIDEO_TASK_TYPE_TEXT_TO_VIDEO]["count"] += 1
        mode_breakdown[record.task_type or VIDEO_TASK_TYPE_TEXT_TO_VIDEO]["credit_cost"] += task_cost
        model_breakdown[record.model or "未设置"]["count"] += 1
        model_breakdown[record.model or "未设置"]["credit_cost"] += task_cost
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
        "model_breakdown": _sorted_breakdown(model_breakdown, limit=10),
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


def get_analytics_payment_revenue(
    db: Session,
    *,
    granularity: str = "day",
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    current_start, current_end = _align_range(granularity, start_date, end_date)

    rows = (
        db.query(
            PaymentOrder.credits,
            PaymentOrder.amount_fen,
            func.count(PaymentOrder.id).label("paid_count"),
            func.coalesce(func.sum(PaymentOrder.amount_fen), 0).label("total_amount_fen"),
        )
        .filter(
            PaymentOrder.status.in_(("paid", "credited")),
            PaymentOrder.paid_at.isnot(None),
            PaymentOrder.paid_at >= current_start,
            PaymentOrder.paid_at <= current_end,
        )
        .group_by(PaymentOrder.credits, PaymentOrder.amount_fen)
        .order_by(PaymentOrder.amount_fen.asc(), PaymentOrder.credits.asc())
        .all()
    )

    items: list[dict] = []
    total_used_count = 0
    total_amount = 0.0
    for row in rows:
        paid_count = int(row.paid_count or 0)
        total_amount_yuan = round(int(row.total_amount_fen or 0) / 100, 2)
        items.append(
            {
                "credit_amount": int(row.credits or 0),
                "unit_price": round(int(row.amount_fen or 0) / 100, 2),
                "used_count": paid_count,
                "total_amount": total_amount_yuan,
            }
        )
        total_used_count += paid_count
        total_amount += total_amount_yuan

    return {
        "range_label": _format_range_label(current_start, current_end),
        "items": items,
        "total_used_count": total_used_count,
        "total_amount": round(total_amount, 2),
    }


def get_analytics_offline_order_revenue(
    db: Session,
    *,
    granularity: str = "day",
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    current_start, current_end = _align_range(granularity, start_date, end_date)

    rows = (
        db.query(
            OfflineOrder.order_type,
            OfflineOrder.credit_amount,
            OfflineOrder.amount_fen,
            func.count(OfflineOrder.id).label("order_count"),
            func.coalesce(
                func.sum(
                    case(
                        (OfflineOrder.order_type == "refund", -OfflineOrder.amount_fen),
                        else_=OfflineOrder.amount_fen,
                    )
                ),
                0,
            ).label("net_amount_fen"),
        )
        .filter(
            OfflineOrder.created_at >= _to_db_datetime(current_start),
            OfflineOrder.created_at <= _to_db_datetime(current_end),
        )
        .group_by(OfflineOrder.order_type, OfflineOrder.credit_amount, OfflineOrder.amount_fen)
        .order_by(OfflineOrder.amount_fen.asc(), OfflineOrder.credit_amount.asc(), OfflineOrder.order_type.asc())
        .all()
    )

    items: list[dict] = []
    total_used_count = 0
    total_amount = 0.0
    for row in rows:
        order_count = int(row.order_count or 0)
        signed_unit_price = round(int(row.amount_fen or 0) / 100, 2)
        total_amount_yuan = round(int(row.net_amount_fen or 0) / 100, 2)
        items.append(
            {
                "credit_amount": int(row.credit_amount or 0),
                "unit_price": -signed_unit_price if row.order_type == "refund" else signed_unit_price,
                "used_count": order_count,
                "total_amount": total_amount_yuan,
            }
        )
        total_used_count += order_count
        total_amount += total_amount_yuan

    return {
        "range_label": _format_range_label(current_start, current_end),
        "items": items,
        "total_used_count": total_used_count,
        "total_amount": round(total_amount, 2),
    }


def _redeem_amount_yuan(credit_amount: int) -> float:
    return float(REDEEM_UNIT_PRICES.get(int(credit_amount or 0), 0.0))


def get_analytics_revenue_timeseries(
    db: Session,
    *,
    granularity: str = "day",
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    current_start, current_end = _align_range(granularity, start_date, end_date)
    bucket_starts = _iter_bucket_starts(current_start, current_end, granularity)
    bucket_map = {
        bucket: {
            "label": _bucket_label(bucket, granularity),
            "bucket_start": bucket,
            "bucket_end": _bucket_end(bucket, granularity),
            "online_amount": 0.0,
            "redeem_amount": 0.0,
            "offline_amount": 0.0,
            "total_amount": 0.0,
        }
        for bucket in bucket_starts
    }

    payment_rows = (
        db.query(PaymentOrder.paid_at, PaymentOrder.amount_fen)
        .filter(
            PaymentOrder.status.in_(("paid", "credited")),
            PaymentOrder.paid_at.isnot(None),
            PaymentOrder.paid_at >= current_start,
            PaymentOrder.paid_at <= current_end,
        )
        .all()
    )
    for paid_at, amount_fen in payment_rows:
        if paid_at is None:
            continue
        bucket = _bucket_start(_to_local_datetime(paid_at), granularity)
        if bucket not in bucket_map:
            continue
        bucket_map[bucket]["online_amount"] += int(amount_fen or 0) / 100

    redeem_rows = (
        db.query(CreditRedeemKey.used_at, CreditRedeemKey.credit_amount)
        .filter(
            CreditRedeemKey.used_at.isnot(None),
            CreditRedeemKey.used_at >= current_start,
            CreditRedeemKey.used_at <= current_end,
        )
        .all()
    )
    for used_at, credit_amount in redeem_rows:
        if used_at is None:
            continue
        bucket = _bucket_start(_to_local_datetime(used_at), granularity)
        if bucket not in bucket_map:
            continue
        bucket_map[bucket]["redeem_amount"] += _redeem_amount_yuan(int(credit_amount or 0))

    offline_rows = (
        db.query(OfflineOrder.created_at, OfflineOrder.order_type, OfflineOrder.amount_fen)
        .filter(
            OfflineOrder.created_at >= _to_db_datetime(current_start),
            OfflineOrder.created_at <= _to_db_datetime(current_end),
        )
        .all()
    )
    for created_at, order_type, amount_fen in offline_rows:
        if created_at is None:
            continue
        bucket = _bucket_start(_to_local_datetime(created_at), granularity)
        if bucket not in bucket_map:
            continue
        signed_amount = int(amount_fen or 0) / 100
        if order_type == "refund":
            signed_amount = -signed_amount
        bucket_map[bucket]["offline_amount"] += signed_amount

    points: list[dict] = []
    total_online_amount = 0.0
    total_redeem_amount = 0.0
    total_offline_amount = 0.0
    for bucket in bucket_starts:
        item = bucket_map[bucket]
        item["online_amount"] = round(item["online_amount"], 2)
        item["redeem_amount"] = round(item["redeem_amount"], 2)
        item["offline_amount"] = round(item["offline_amount"], 2)
        item["total_amount"] = round(
            item["online_amount"] + item["redeem_amount"] + item["offline_amount"],
            2,
        )
        total_online_amount += item["online_amount"]
        total_redeem_amount += item["redeem_amount"]
        total_offline_amount += item["offline_amount"]
        points.append(item)

    return {
        "granularity": granularity,
        "range_label": _format_range_label(current_start, current_end),
        "points": points,
        "total_online_amount": round(total_online_amount, 2),
        "total_redeem_amount": round(total_redeem_amount, 2),
        "total_offline_amount": round(total_offline_amount, 2),
        "total_amount": round(total_online_amount + total_redeem_amount + total_offline_amount, 2),
    }


LEDGER_EXPENSE_TYPES = {"server", "third_party_api", "other"}
LEDGER_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _parse_ledger_month(month: str) -> date:
    normalized = (month or "").strip()
    if not LEDGER_MONTH_RE.match(normalized):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账本月份格式必须为 YYYY-MM")
    year, month_value = normalized.split("-")
    try:
        return date(int(year), int(month_value), 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账本月份无效") from exc


def _format_ledger_month(value: date | datetime) -> str:
    return value.strftime("%Y-%m")


def _ledger_month_range(value: date) -> tuple[datetime, datetime]:
    last_day = monthrange(value.year, value.month)[1]
    return (
        datetime(value.year, value.month, 1, 0, 0, 0),
        datetime(value.year, value.month, last_day, 23, 59, 59, 999999),
    )


def _money_to_fen(amount_yuan: Decimal | int | float | str, *, allow_zero: bool = True) -> int:
    try:
        normalized = Decimal(str(amount_yuan or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="金额格式不正确") from exc
    if normalized < 0 or (not allow_zero and normalized <= 0):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="金额不能为负数")
    return int((normalized * Decimal("100")).to_integral_value(rounding=ROUND_HALF_UP))


def _float_yuan_to_fen(amount_yuan: float | int | Decimal) -> int:
    return _money_to_fen(Decimal(str(amount_yuan or 0)))


def _fen_to_yuan(amount_fen: int | None) -> float:
    return round(int(amount_fen or 0) / 100, 2)


def _json_loads(raw: str | None, fallback):
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _json_dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _normalize_screenshot_urls(urls: list[str] | None) -> list[str]:
    result: list[str] = []
    for url in urls or []:
        normalized = str(url or "").strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result[:20]


def _load_ledger(db: Session, month: str) -> AdminLedger | None:
    ledger_month = _parse_ledger_month(month)
    return (
        db.query(AdminLedger)
        .options(
            joinedload(AdminLedger.expenses).joinedload(AdminLedgerExpense.creator),
            joinedload(AdminLedger.expenses).joinedload(AdminLedgerExpense.updater),
            joinedload(AdminLedger.logs).joinedload(AdminLedgerLog.operator),
            joinedload(AdminLedger.creator),
            joinedload(AdminLedger.updater),
        )
        .filter(AdminLedger.ledger_month == ledger_month)
        .first()
    )


def _build_ledger_income_snapshot(db: Session, ledger_month: date) -> dict:
    start_at, end_at = _ledger_month_range(ledger_month)
    query = {
        "granularity": "day",
        "start_date": start_at,
        "end_date": end_at,
    }
    payment = get_analytics_payment_revenue(db, **query)
    redeem = get_analytics_redeem_revenue(db, **query)
    offline = get_analytics_offline_order_revenue(db, **query)
    online_revenue_fen = _float_yuan_to_fen(payment.get("total_amount", 0))
    redeem_revenue_fen = _float_yuan_to_fen(redeem.get("total_amount", 0))
    offline_revenue_fen = _float_yuan_to_fen(offline.get("total_amount", 0))
    total_income_fen = online_revenue_fen + redeem_revenue_fen + offline_revenue_fen
    return {
        "range_start": start_at.isoformat(),
        "range_end": end_at.isoformat(),
        "online_revenue_fen": online_revenue_fen,
        "redeem_revenue_fen": redeem_revenue_fen,
        "offline_revenue_fen": offline_revenue_fen,
        "total_income_fen": total_income_fen,
        "payment": payment,
        "redeem": redeem,
        "offline": offline,
    }


def _apply_income_snapshot(ledger: AdminLedger, snapshot: dict) -> None:
    ledger.online_revenue_fen = int(snapshot.get("online_revenue_fen") or 0)
    ledger.redeem_revenue_fen = int(snapshot.get("redeem_revenue_fen") or 0)
    ledger.offline_revenue_fen = int(snapshot.get("offline_revenue_fen") or 0)
    ledger.total_income_fen = int(snapshot.get("total_income_fen") or 0)
    ledger.income_snapshot_json = _json_dumps(snapshot)


def _recalculate_ledger_totals(ledger: AdminLedger) -> None:
    total_expense_fen = sum(int(expense.amount_fen or 0) for expense in (ledger.expenses or []))
    ledger.total_expense_fen = total_expense_fen
    ledger.net_income_fen = int(ledger.total_income_fen or 0) - total_expense_fen


def _serialize_ledger_income(ledger: AdminLedger | None, snapshot: dict | None = None) -> dict:
    if ledger:
        online = int(ledger.online_revenue_fen or 0)
        redeem = int(ledger.redeem_revenue_fen or 0)
        offline = int(ledger.offline_revenue_fen or 0)
    else:
        snapshot = snapshot or {}
        online = int(snapshot.get("online_revenue_fen") or 0)
        redeem = int(snapshot.get("redeem_revenue_fen") or 0)
        offline = int(snapshot.get("offline_revenue_fen") or 0)
    return {
        "online_revenue_yuan": _fen_to_yuan(online),
        "redeem_revenue_yuan": _fen_to_yuan(redeem),
        "offline_revenue_yuan": _fen_to_yuan(offline),
        "total_income_yuan": _fen_to_yuan(online + redeem + offline),
    }


def _serialize_ledger_expense(expense: AdminLedgerExpense) -> dict:
    return {
        "id": int(expense.id),
        "business_id": expense.business_id or "",
        "expense_type": expense.expense_type or "other",
        "title": expense.title or "",
        "amount_fen": int(expense.amount_fen or 0),
        "amount_yuan": _fen_to_yuan(expense.amount_fen),
        "content": expense.content or "",
        "description": expense.description or "",
        "screenshot_urls": _json_loads(expense.screenshot_urls_json, []),
        "sort_order": int(expense.sort_order or 0),
        "created_by_username": expense.creator.username if expense.creator else "",
        "updated_by_username": expense.updater.username if expense.updater else "",
        "created_at": expense.created_at,
        "updated_at": expense.updated_at,
    }


def _serialize_ledger_log(log: AdminLedgerLog) -> dict:
    return {
        "id": int(log.id),
        "operator_id": user_external_id(log.operator) if log.operator else "",
        "operator_username": log.operator.username if log.operator else "",
        "action": log.action or "",
        "summary": log.summary or "",
        "before": _json_loads(log.before_json, {}),
        "after": _json_loads(log.after_json, {}),
        "created_at": log.created_at,
    }


def _ledger_snapshot_for_log(ledger: AdminLedger) -> dict:
    expenses = sorted(ledger.expenses or [], key=lambda item: (int(item.sort_order or 0), int(item.id or 0)))
    return {
        "month": _format_ledger_month(ledger.ledger_month),
        "title": ledger.title or "",
        "content": ledger.content or "",
        "description": ledger.description or "",
        "screenshot_urls": _json_loads(ledger.screenshot_urls_json, []),
        "income": _serialize_ledger_income(ledger),
        "total_expense_yuan": _fen_to_yuan(ledger.total_expense_fen),
        "net_income_yuan": _fen_to_yuan(ledger.net_income_fen),
        "expenses": [
            {
                "id": int(expense.id),
                "expense_type": expense.expense_type or "other",
                "title": expense.title or "",
                "amount_yuan": _fen_to_yuan(expense.amount_fen),
                "content": expense.content or "",
                "description": expense.description or "",
                "screenshot_urls": _json_loads(expense.screenshot_urls_json, []),
            }
            for expense in expenses
        ],
    }


def _add_ledger_log(
    db: Session,
    *,
    ledger: AdminLedger,
    operator: User,
    action: str,
    summary: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    db.add(AdminLedgerLog(
        ledger_id=ledger.id,
        operator_id=operator.id,
        action=action,
        summary=summary,
        before_json=_json_dumps(before or {}),
        after_json=_json_dumps(after or {}),
    ))


def _serialize_ledger(ledger: AdminLedger) -> dict:
    expenses = sorted(ledger.expenses or [], key=lambda item: (int(item.sort_order or 0), int(item.id or 0)))
    logs = sorted(ledger.logs or [], key=lambda item: item.created_at or datetime.min, reverse=True)
    return {
        "id": int(ledger.id),
        "business_id": ledger.business_id or "",
        "month": _format_ledger_month(ledger.ledger_month),
        "title": ledger.title or "",
        "content": ledger.content or "",
        "description": ledger.description or "",
        "screenshot_urls": _json_loads(ledger.screenshot_urls_json, []),
        "income": _serialize_ledger_income(ledger),
        "income_snapshot": _json_loads(ledger.income_snapshot_json, {}),
        "total_expense_fen": int(ledger.total_expense_fen or 0),
        "total_expense_yuan": _fen_to_yuan(ledger.total_expense_fen),
        "net_income_fen": int(ledger.net_income_fen or 0),
        "net_income_yuan": _fen_to_yuan(ledger.net_income_fen),
        "expenses": [_serialize_ledger_expense(expense) for expense in expenses],
        "logs": [_serialize_ledger_log(log) for log in logs],
        "exists": True,
        "created_by_username": ledger.creator.username if ledger.creator else "",
        "updated_by_username": ledger.updater.username if ledger.updater else "",
        "created_at": ledger.created_at,
        "updated_at": ledger.updated_at,
    }


def _serialize_ledger_draft(month: str, income_snapshot: dict) -> dict:
    return {
        "id": None,
        "business_id": "",
        "month": month,
        "title": f"{month} 账本",
        "content": "",
        "description": "",
        "screenshot_urls": [],
        "income": _serialize_ledger_income(None, income_snapshot),
        "income_snapshot": income_snapshot,
        "total_expense_fen": 0,
        "total_expense_yuan": 0,
        "net_income_fen": int(income_snapshot.get("total_income_fen") or 0),
        "net_income_yuan": _fen_to_yuan(income_snapshot.get("total_income_fen") or 0),
        "expenses": [],
        "logs": [],
        "exists": False,
        "created_by_username": "",
        "updated_by_username": "",
        "created_at": None,
        "updated_at": None,
    }


def list_admin_ledgers(db: Session, *, page: int = 1, page_size: int = 20) -> dict:
    query = db.query(AdminLedger).options(joinedload(AdminLedger.updater))
    total = query.count()
    ledgers = (
        query
        .order_by(AdminLedger.ledger_month.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "items": [
            {
                "id": int(ledger.id),
                "business_id": ledger.business_id or "",
                "month": _format_ledger_month(ledger.ledger_month),
                "title": ledger.title or "",
                "total_income_yuan": _fen_to_yuan(ledger.total_income_fen),
                "total_expense_yuan": _fen_to_yuan(ledger.total_expense_fen),
                "net_income_yuan": _fen_to_yuan(ledger.net_income_fen),
                "updated_by_username": ledger.updater.username if ledger.updater else "",
                "updated_at": ledger.updated_at,
            }
            for ledger in ledgers
        ],
    }


def get_admin_ledger(db: Session, *, month: str) -> dict:
    ledger = _load_ledger(db, month)
    if ledger:
        return _serialize_ledger(ledger)
    ledger_month = _parse_ledger_month(month)
    return _serialize_ledger_draft(month, _build_ledger_income_snapshot(db, ledger_month))


def _apply_ledger_expenses(db: Session, *, ledger: AdminLedger, expenses: list, operator: User) -> tuple[int, int, int]:
    existing_by_id = {int(expense.id): expense for expense in (ledger.expenses or [])}
    seen_ids: set[int] = set()
    created_count = 0
    updated_count = 0
    for index, payload in enumerate(expenses):
        expense_id = int(payload.id or 0) if getattr(payload, "id", None) else 0
        expense = existing_by_id.get(expense_id) if expense_id else None
        if expense:
            seen_ids.add(expense.id)
            updated_count += 1
            expense.updated_by = operator.id
        else:
            expense = AdminLedgerExpense(
                ledger=ledger,
                created_by=operator.id,
                updated_by=operator.id,
            )
            db.add(expense)
            created_count += 1

        expense_type = (payload.expense_type or "other").strip()
        if expense_type not in LEDGER_EXPENSE_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="支出类型无效")
        expense.expense_type = expense_type
        expense.title = (payload.title or "").strip()[:200]
        expense.amount_fen = _money_to_fen(payload.amount_yuan)
        expense.content = payload.content or ""
        expense.description = payload.description or ""
        expense.screenshot_urls_json = _json_dumps(_normalize_screenshot_urls(payload.screenshot_urls))
        expense.sort_order = index

    deleted_count = 0
    for expense_id, expense in existing_by_id.items():
        if expense_id not in seen_ids:
            if expense in ledger.expenses:
                ledger.expenses.remove(expense)
            db.delete(expense)
            deleted_count += 1
    db.flush()
    return created_count, updated_count, deleted_count


def create_admin_ledger(db: Session, *, payload, operator: User) -> dict:
    ledger_month = _parse_ledger_month(payload.month)
    exists = db.query(AdminLedger.id).filter(AdminLedger.ledger_month == ledger_month).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该月份账本已存在")
    snapshot = _build_ledger_income_snapshot(db, ledger_month)
    ledger = AdminLedger(
        ledger_month=ledger_month,
        title=(payload.title or f"{payload.month} 账本").strip()[:200],
        content=payload.content or "",
        description=payload.description or "",
        screenshot_urls_json=_json_dumps(_normalize_screenshot_urls(payload.screenshot_urls)),
        created_by=operator.id,
        updated_by=operator.id,
    )
    _apply_income_snapshot(ledger, snapshot)
    db.add(ledger)
    db.flush()
    _apply_ledger_expenses(db, ledger=ledger, expenses=payload.expenses or [], operator=operator)
    _recalculate_ledger_totals(ledger)
    db.flush()
    after = _ledger_snapshot_for_log(ledger)
    _add_ledger_log(
        db,
        ledger=ledger,
        operator=operator,
        action="create",
        summary=f"{operator.username} 新增了 {_format_ledger_month(ledger_month)} 账本",
        after=after,
    )
    db.commit()
    return get_admin_ledger(db, month=_format_ledger_month(ledger_month))


def update_admin_ledger(db: Session, *, month: str, payload, operator: User) -> dict:
    ledger = _load_ledger(db, month)
    if not ledger:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账本不存在")
    before = _ledger_snapshot_for_log(ledger)
    ledger.title = (payload.title or "").strip()[:200]
    ledger.content = payload.content or ""
    ledger.description = payload.description or ""
    ledger.screenshot_urls_json = _json_dumps(_normalize_screenshot_urls(payload.screenshot_urls))
    ledger.updated_by = operator.id
    created_count, updated_count, deleted_count = _apply_ledger_expenses(
        db,
        ledger=ledger,
        expenses=payload.expenses or [],
        operator=operator,
    )
    _recalculate_ledger_totals(ledger)
    db.flush()
    after = _ledger_snapshot_for_log(ledger)
    summary_parts = [f"{operator.username} 编辑了 {month} 账本"]
    if created_count:
        summary_parts.append(f"新增支出 {created_count} 项")
    if deleted_count:
        summary_parts.append(f"删除支出 {deleted_count} 项")
    if updated_count:
        summary_parts.append(f"更新支出 {updated_count} 项")
    log_action = "update"
    if created_count:
        log_action = "create"
    elif deleted_count:
        log_action = "delete"
    _add_ledger_log(
        db,
        ledger=ledger,
        operator=operator,
        action=log_action,
        summary="，".join(summary_parts),
        before=before,
        after=after,
    )
    db.commit()
    return get_admin_ledger(db, month=month)


def refresh_admin_ledger_income(db: Session, *, month: str, operator: User) -> dict:
    ledger = _load_ledger(db, month)
    if not ledger:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账本不存在")
    before = _ledger_snapshot_for_log(ledger)
    snapshot = _build_ledger_income_snapshot(db, ledger.ledger_month)
    _apply_income_snapshot(ledger, snapshot)
    _recalculate_ledger_totals(ledger)
    ledger.updated_by = operator.id
    db.flush()
    after = _ledger_snapshot_for_log(ledger)
    _add_ledger_log(
        db,
        ledger=ledger,
        operator=operator,
        action="income_refresh",
        summary=f"{operator.username} 刷新了 {month} 账本收入数据",
        before=before,
        after=after,
    )
    db.commit()
    return get_admin_ledger(db, month=month)


MISSING_INLINE_BASE64_ERROR_MESSAGE = (
    "生图接口返回内容缺少配置路径 candidates.0.content.parts.0.inlineData.data 对应的 base64 数据；"
)
INVALID_REFERENCE_IMAGE_ERROR_MESSAGE = (
    '生图接口返回 HTTP 400: {"error":{"message":"poll rejected: 400 {\\"error_code\\":\\"bad_request\\",'
    '\\"message\\":\\"Bad request to openai: Invalid image file or mode for image 1, please check your image file. '
    'If you believe this is an error, contact us at ***.***.com and include the request ID.\\"}",'
    '"type":"upstream_error","param":"","code":"provider_request_invalid"}}'
)


UPSTREAM_HTTP_STATUS_PATTERN = re.compile(
    r"(?:"
    r"生图接口返回\s*HTTP\s+(\d{3})"
    r"|异步生图(?:提交|轮询)返回\s*HTTP\s+(\d{3})"
    r"|上游\s*API\s*错误\s*\(\s*HTTP\s*(\d{3})\s*\)"
    r"|\(\s*HTTP\s*(\d{3})\s*\)"
    r")",
    re.IGNORECASE,
)
ASYNC_REQUEST_CONTEXT_PATTERN = re.compile(
    r"[（(]\s*第三方taskId=[^）)]+[，,]\s*轮询地址=[^）)]+\s*[）)]",
    re.IGNORECASE,
)
CONTENT_SAFETY_ERROR_PATTERN = re.compile(
    r"unsafe|image_unsafe|content blocked|appear to be unsafe|safety|nsfw|敏感|违规|审核拒绝|内容安全",
    re.IGNORECASE,
)


def _extract_upstream_http_status(message: str) -> int | None:
    matched = UPSTREAM_HTTP_STATUS_PATTERN.search(message)
    if not matched:
        return None
    for group in matched.groups():
        if group:
            return int(group)
    return None


def _is_content_safety_error(message: str) -> bool:
    return is_content_safety_error_text(message)


def _normalize_error_message_for_analytics(error_message: str | None) -> str:
    message = (error_message or "").strip() or "未知错误"
    message = ASYNC_REQUEST_CONTEXT_PATTERN.sub("", message).strip(" ，,;；")
    if "生图接口返回内容缺少配置路径" in message and "对应的 base64 数据" in message:
        return MISSING_INLINE_BASE64_ERROR_MESSAGE
    lower = message.lower()
    if "invalid image file or mode" in lower or (
        "provider_request_invalid" in lower and "poll rejected" in lower
    ):
        return INVALID_REFERENCE_IMAGE_ERROR_MESSAGE
    return message


def _classify_upstream_http_error(message: str, lower: str) -> str | None:
    status_code = _extract_upstream_http_status(message)
    if status_code is None:
        return None

    if _is_content_safety_error(message):
        return "内容安全审查拒绝"
    if "provider_request_invalid" in lower or "bad request to openai" in lower:
        return "上游 HTTP 400-请求参数无效"
    if "invalid image file or mode" in lower:
        return "上游 HTTP 400-参考图无效"
    if "rate limit" in lower or "too many requests" in lower:
        return "上游 HTTP 429-限流"
    if "unauthorized" in lower or "invalid api key" in lower or "authentication" in lower:
        return "上游 HTTP 401-鉴权失败"
    if "forbidden" in lower or "permission" in lower:
        return "上游 HTTP 403-权限不足"
    if "not found" in lower or "model_not_found" in lower:
        return "上游 HTTP 404-资源不存在"
    if "timeout" in lower:
        return f"上游 HTTP {status_code}-超时"
    if "payload too large" in lower or "request entity too large" in lower:
        return "上游 HTTP 413-请求体过大"
    if "unprocessable" in lower or "validation" in lower:
        return "上游 HTTP 422-请求校验失败"
    if "bad gateway" in lower:
        return "上游 HTTP 502-网关异常"
    if "service unavailable" in lower:
        return "上游 HTTP 503-服务不可用"
    if "gateway timeout" in lower:
        return "上游 HTTP 504-网关超时"
    if status_code == 400:
        return "上游 HTTP 400-请求错误"
    if status_code == 401:
        return "上游 HTTP 401-鉴权失败"
    if status_code == 403:
        return "上游 HTTP 403-权限不足"
    if status_code == 404:
        return "上游 HTTP 404-资源不存在"
    if status_code == 408:
        return "上游 HTTP 408-请求超时"
    if status_code == 409:
        return "上游 HTTP 409-状态冲突"
    if status_code == 413:
        return "上游 HTTP 413-请求体过大"
    if status_code == 422:
        return "上游 HTTP 422-请求校验失败"
    if status_code == 429:
        return "上游 HTTP 429-限流"
    if status_code == 500:
        return "上游 HTTP 500-服务内部错误"
    if status_code == 502:
        return "上游 HTTP 502-网关异常"
    if status_code == 503:
        return "上游 HTTP 503-服务不可用"
    if status_code == 504:
        return "上游 HTTP 504-网关超时"
    if 400 <= status_code < 500:
        return f"上游 HTTP {status_code}-客户端错误"
    if 500 <= status_code < 600:
        return f"上游 HTTP {status_code}-服务端错误"
    return f"上游 HTTP {status_code}-其他错误"


def _classify_error_message_for_analytics(error_message: str | None) -> str:
    message = _normalize_error_message_for_analytics(error_message)
    lower = message.lower()

    if _is_content_safety_error(message):
        return "内容安全审查拒绝"
    if "生图接口连接被上游异常断开" in message:
        return "上游异常断开连接"
    if "生图接口连接超时" in message:
        return "上游连接超时"
    if "生图接口响应读取超时" in message:
        return "上游响应读取超时"
    if "生图接口请求发送超时" in message:
        return "上游请求发送超时"
    if "生图接口连接池等待超时" in message:
        return "连接池等待超时"
    if "生图接口请求超时" in message:
        return "上游请求超时"
    if "生图接口连接失败" in message:
        return "上游连接失败"
    if "生图接口响应读取失败" in message:
        return "上游响应读取失败"
    if "生图接口请求发送失败" in message:
        return "上游请求发送失败"
    if "生图接口连接关闭异常" in message:
        return "连接关闭异常"
    if "生图接口协议异常" in message:
        return "上游协议异常"
    if "生图接口网络异常" in message:
        return "上游网络异常"
    if "invalid image file or mode" in lower or "provider_request_invalid" in lower:
        return "参考图无效"
    if "生图接口返回内容缺少配置路径" in message and "对应的 base64 数据" in message:
        return "上游返回缺少图片数据"
    if "异步生图轮询超时" in message:
        return "异步轮询超时"
    if "异步生图轮询响应不是合法 JSON" in message:
        return "异步轮询响应解析失败"
    if "异步生图提交成功，但响应不是合法 JSON" in message:
        return "异步提交响应解析失败"
    if "异步生图提交成功，但未从" in message and "解析到 taskId" in message:
        return "异步提交未返回任务ID"
    if "异步生图提交异常" in message:
        return "异步提交异常"
    if "异步生图轮询异常" in message:
        return "异步轮询异常"
    if "异步生图任务失败" in message:
        return "异步第三方任务失败"
    if "轮询成功，但未能从" in message and "解析结果图" in message:
        return "异步结果图解析失败"
    if "异步生图已完成，但结果图解析失败" in message:
        return "异步结果图解析失败"
    if "生图接口返回了结果图地址，但图片下载失败" in message:
        return "结果图下载失败"
    if "生图接口返回的 base64 数据解析失败" in message:
        return "结果图Base64解析失败"
    upstream_http_category = _classify_upstream_http_error(message, lower)
    if upstream_http_category:
        return upstream_http_category
    if "图片已生成，但保存结果失败" in message:
        return "结果图片保存失败"
    if "图编辑原图不存在或无法读取" in message:
        return "图编辑原图不可读"
    if "图编辑蒙版不存在或无法读取" in message:
        return "图编辑蒙版不可读"
    if "图编辑原图格式无效" in message:
        return "图编辑原图格式无效"
    if "图编辑蒙版格式无效" in message:
        return "图编辑蒙版格式无效"
    if "任务处理超时" in message:
        return "任务处理超时"
    if "任务队列暂不可用" in message or "任务入队失败" in message:
        return "任务入队异常"
    if "生图任务执行异常" in message or "重新生成任务执行异常" in message:
        return "任务执行异常"
    if "关联任务不存在" in message:
        return "关联任务不存在"
    if "生图失败" in message:
        return "生图失败"
    return "其他错误"


def _load_task_attempts_map(db: Session, task_ids: list[int]) -> dict[int, list[TaskApiAttempt]]:
    normalized_task_ids = [int(task_id) for task_id in task_ids if task_id]
    if not normalized_task_ids:
        return {}
    rows = (
        db.query(TaskApiAttempt)
        .filter(TaskApiAttempt.task_id.in_(normalized_task_ids))
        .order_by(
            TaskApiAttempt.task_id.asc(),
            TaskApiAttempt.image_index.asc(),
            TaskApiAttempt.attempt_index.asc(),
            TaskApiAttempt.id.asc(),
        )
        .all()
    )
    attempts_map: dict[int, list[TaskApiAttempt]] = defaultdict(list)
    for row in rows:
        attempts_map[int(row.task_id)].append(row)
    return dict(attempts_map)


def _load_video_task_attempts_map(db: Session, task_ids: list[int]) -> dict[int, list[VideoTaskApiAttempt]]:
    normalized_task_ids = [int(task_id) for task_id in task_ids if task_id]
    if not normalized_task_ids:
        return {}
    rows = (
        db.query(VideoTaskApiAttempt)
        .filter(VideoTaskApiAttempt.task_id.in_(normalized_task_ids))
        .order_by(
            VideoTaskApiAttempt.task_id.asc(),
            VideoTaskApiAttempt.attempt_index.asc(),
            VideoTaskApiAttempt.id.asc(),
        )
        .all()
    )
    attempts_map: dict[int, list[VideoTaskApiAttempt]] = defaultdict(list)
    for row in rows:
        attempts_map[int(row.task_id)].append(row)
    return dict(attempts_map)


def _join_attempt_api_names(attempts) -> str:
    names: list[str] = []
    seen_names: set[str] = set()
    for attempt in attempts:
        name = (attempt.api_config_name or "").strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        names.append(name)
    return "、".join(names)


def _summarize_task_attempts_for_error_row(
    attempts: list[TaskApiAttempt],
    *,
    error_category: str | None = None,
) -> dict | None:
    primary_failed_attempts = [
        attempt
        for attempt in attempts
        if not attempt.is_fallback and (attempt.status or "failed") == "failed"
    ]
    if not primary_failed_attempts:
        return None

    matched_primary: TaskApiAttempt | None = None
    for attempt in primary_failed_attempts:
        row_error_category = _classify_error_message_for_analytics(attempt.error_message)
        if error_category and row_error_category != error_category:
            continue
        matched_primary = attempt
        break
    if matched_primary is None:
        return None

    fallback_attempts = [attempt for attempt in attempts if attempt.is_fallback]
    fallback_success_attempts = [
        attempt for attempt in fallback_attempts if (attempt.status or "failed") == "success"
    ]
    fallback_failed_attempts = [
        attempt for attempt in fallback_attempts if (attempt.status or "failed") != "success"
    ]
    if not fallback_attempts:
        fallback_status = "unused"
    elif fallback_success_attempts and fallback_failed_attempts:
        fallback_status = "partial"
    elif fallback_success_attempts:
        fallback_status = "success"
    else:
        fallback_status = "failed"

    fallback_error_message = next(
        (
            (attempt.error_message or "").strip()
            for attempt in fallback_failed_attempts
            if (attempt.error_message or "").strip()
        ),
        "",
    )
    return {
        "primary_api_config_name": (matched_primary.api_config_name or "").strip(),
        "primary_http_status": matched_primary.http_status,
        "primary_error_message": (matched_primary.error_message or "").strip(),
        "fallback_api_config_name": _join_attempt_api_names(fallback_attempts),
        "fallback_status": fallback_status,
        "fallback_error_message": fallback_error_message,
    }


def _summarize_video_task_attempts_for_error_row(
    attempts: list[VideoTaskApiAttempt],
    *,
    error_category: str | None = None,
) -> dict | None:
    primary_failed_attempts = [
        attempt
        for attempt in attempts
        if not attempt.is_fallback and (attempt.status or "failed") == "failed"
    ]
    if not primary_failed_attempts:
        return None

    matched_primary: VideoTaskApiAttempt | None = None
    for attempt in primary_failed_attempts:
        row_error_category = _classify_error_message_for_analytics(attempt.error_message)
        if error_category and row_error_category != error_category:
            continue
        matched_primary = attempt
        break
    if matched_primary is None:
        return None

    fallback_attempts = [attempt for attempt in attempts if attempt.is_fallback]
    fallback_success_attempts = [
        attempt for attempt in fallback_attempts if (attempt.status or "failed") == "success"
    ]
    fallback_failed_attempts = [
        attempt for attempt in fallback_attempts if (attempt.status or "failed") != "success"
    ]
    if not fallback_attempts:
        fallback_status = "unused"
    elif fallback_success_attempts and fallback_failed_attempts:
        fallback_status = "partial"
    elif fallback_success_attempts:
        fallback_status = "success"
    else:
        fallback_status = "failed"

    fallback_error_message = next(
        (
            (attempt.error_message or "").strip()
            for attempt in fallback_failed_attempts
            if (attempt.error_message or "").strip()
        ),
        "",
    )
    return {
        "primary_api_config_name": (matched_primary.api_config_name or "").strip(),
        "primary_http_status": matched_primary.http_status,
        "primary_error_message": (matched_primary.error_message or "").strip(),
        "fallback_api_config_name": _join_attempt_api_names(fallback_attempts),
        "fallback_status": fallback_status,
        "fallback_error_message": fallback_error_message,
    }


def get_error_analytics(
    db: Session,
    *,
    task_kind: str = ERROR_ANALYTICS_TASK_KIND_IMAGE,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    source: str | None = None,
    model: str | None = None,
    error_category: str | None = None,
    used_fallback_api: bool | None = None,
    include_unsafe_tasks: bool = True,
) -> dict:
    current_start, current_end = _align_range("day", start_date, end_date)
    fallback_task_total = 0
    fallback_success_tasks = 0
    fallback_failed_tasks = 0
    if task_kind == ERROR_ANALYTICS_TASK_KIND_VIDEO:
        if used_fallback_api is True:
            query = (
                db.query(VideoTask.id, VideoTask.status, VideoTaskApiAttempt.error_message)
                .join(VideoTask, VideoTask.id == VideoTaskApiAttempt.task_id)
                .join(User, User.id == VideoTask.user_id)
                .filter(
                    VideoTask.created_at >= _to_db_datetime(current_start),
                    VideoTask.created_at <= _to_db_datetime(current_end),
                    VideoTask.used_fallback_api.is_(True),
                    VideoTaskApiAttempt.is_fallback.is_(False),
                    VideoTaskApiAttempt.status == "failed",
                    User.role != "superadmin",
                    _non_whitelisted_user_filter(),
                )
            )
            if not include_unsafe_tasks:
                query = query.filter(~build_content_safety_error_clause(VideoTaskApiAttempt.error_message))
        else:
            query = (
                db.query(VideoTask.error_message)
                .join(User, User.id == VideoTask.user_id)
                .filter(
                    VideoTask.created_at >= _to_db_datetime(current_start),
                    VideoTask.created_at <= _to_db_datetime(current_end),
                    VideoTask.status == "failed",
                    User.role != "superadmin",
                    _non_whitelisted_user_filter(),
                )
            )
            if used_fallback_api is False:
                query = query.filter(VideoTask.used_fallback_api.is_(False))
            if not include_unsafe_tasks:
                query = query.filter(~build_content_safety_error_clause(VideoTask.error_message))
        if source:
            query = query.filter(VideoTask.source == source)
        if model:
            query = query.filter(VideoTask.model == model)
    else:
        if used_fallback_api is True:
            query = (
                db.query(Task.id, Task.status, TaskApiAttempt.error_message)
                .join(Task, Task.id == TaskApiAttempt.task_id)
                .join(User, User.id == Task.user_id)
                .filter(
                    Task.created_at >= _to_db_datetime(current_start),
                    Task.created_at <= _to_db_datetime(current_end),
                    Task.used_fallback_api.is_(True),
                    TaskApiAttempt.is_fallback.is_(False),
                    TaskApiAttempt.status == "failed",
                    User.role != "superadmin",
                    _non_whitelisted_user_filter(),
                    _exclude_example_template_seed_task_clause(),
                )
            )
            if not include_unsafe_tasks:
                query = query.filter(~build_content_safety_error_clause(TaskApiAttempt.error_message))
        else:
            query = (
                db.query(Task.error_message)
                .join(User, User.id == Task.user_id)
                .filter(
                    Task.created_at >= _to_db_datetime(current_start),
                    Task.created_at <= _to_db_datetime(current_end),
                    Task.status == "failed",
                    User.role != "superadmin",
                    _non_whitelisted_user_filter(),
                    _exclude_example_template_seed_task_clause(),
                )
            )
            if used_fallback_api is False:
                query = query.filter(Task.used_fallback_api.is_(False))
            if not include_unsafe_tasks:
                query = query.filter(~build_content_safety_error_clause(Task.error_message))
        if source:
            query = query.filter(Task.source == source)
        if model:
            query = query.filter(Task.model == model)
    rows = query.all()

    raw_error_count_map: dict[str, int] = defaultdict(int)
    category_count_map: dict[str, int] = defaultdict(int)
    category_sample_map: dict[str, str] = {}
    filtered_total_failed_tasks = 0
    matched_fallback_task_status_map: dict[int, str] = {}
    for row in rows:
        normalized_message = _normalize_error_message_for_analytics(row.error_message)
        row_error_category = _classify_error_message_for_analytics(normalized_message)
        if error_category is not None and row_error_category != error_category:
            continue
        filtered_total_failed_tasks += 1
        raw_error_count_map[normalized_message] += 1
        category_count_map[row_error_category] += 1
        category_sample_map.setdefault(row_error_category, normalized_message)
        if used_fallback_api is True and row.id is not None:
            matched_fallback_task_status_map[int(row.id)] = str(row.status or "")

    if used_fallback_api is True:
        fallback_task_total = len(matched_fallback_task_status_map)
        fallback_success_tasks = sum(
            1 for status in matched_fallback_task_status_map.values() if status == "success"
        )
        fallback_failed_tasks = sum(
            1 for status in matched_fallback_task_status_map.values() if status == "failed"
        )

    items = [
        {
            "error_category": error_category,
            "error_message": category_sample_map.get(error_category, ""),
            "count": count,
        }
        for error_category, count in sorted(
            category_count_map.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    return {
        "range_label": _format_range_label(current_start, current_end),
        "total_failed_tasks": filtered_total_failed_tasks,
        "fallback_task_total": fallback_task_total,
        "fallback_success_tasks": fallback_success_tasks,
        "fallback_failed_tasks": fallback_failed_tasks,
        "distinct_error_categories": len(items),
        "distinct_error_messages": len(raw_error_count_map),
        "items": items,
    }


def get_error_category_timeseries(
    db: Session,
    *,
    task_kind: str = ERROR_ANALYTICS_TASK_KIND_IMAGE,
    granularity: str = "day",
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    source: str | None = None,
    model: str | None = None,
    used_fallback_api: bool | None = None,
    limit: int = 6,
    include_unsafe_tasks: bool = True,
) -> dict:
    current_start, current_end = _align_range(granularity, start_date, end_date)
    bucket_starts = _iter_bucket_starts(current_start, current_end, granularity)
    if task_kind == ERROR_ANALYTICS_TASK_KIND_VIDEO:
        if used_fallback_api is True:
            query = (
                db.query(VideoTask.created_at, VideoTaskApiAttempt.error_message)
                .join(VideoTask, VideoTask.id == VideoTaskApiAttempt.task_id)
                .join(User, User.id == VideoTask.user_id)
                .filter(
                    VideoTask.created_at >= _to_db_datetime(current_start),
                    VideoTask.created_at <= _to_db_datetime(current_end),
                    VideoTask.used_fallback_api.is_(True),
                    VideoTaskApiAttempt.is_fallback.is_(False),
                    VideoTaskApiAttempt.status == "failed",
                    User.role != "superadmin",
                    _non_whitelisted_user_filter(),
                )
            )
            if not include_unsafe_tasks:
                query = query.filter(~build_content_safety_error_clause(VideoTaskApiAttempt.error_message))
        else:
            query = (
                db.query(VideoTask.created_at, VideoTask.error_message)
                .join(User, User.id == VideoTask.user_id)
                .filter(
                    VideoTask.created_at >= _to_db_datetime(current_start),
                    VideoTask.created_at <= _to_db_datetime(current_end),
                    VideoTask.status == "failed",
                    User.role != "superadmin",
                    _non_whitelisted_user_filter(),
                )
            )
            if used_fallback_api is False:
                query = query.filter(VideoTask.used_fallback_api.is_(False))
            if not include_unsafe_tasks:
                query = query.filter(~build_content_safety_error_clause(VideoTask.error_message))
        if source:
            query = query.filter(VideoTask.source == source)
        if model:
            query = query.filter(VideoTask.model == model)
    else:
        if used_fallback_api is True:
            query = (
                db.query(Task.created_at, TaskApiAttempt.error_message)
                .join(Task, Task.id == TaskApiAttempt.task_id)
                .join(User, User.id == Task.user_id)
                .filter(
                    Task.created_at >= _to_db_datetime(current_start),
                    Task.created_at <= _to_db_datetime(current_end),
                    Task.used_fallback_api.is_(True),
                    TaskApiAttempt.is_fallback.is_(False),
                    TaskApiAttempt.status == "failed",
                    User.role != "superadmin",
                    _non_whitelisted_user_filter(),
                    _exclude_example_template_seed_task_clause(),
                )
            )
            if not include_unsafe_tasks:
                query = query.filter(~build_content_safety_error_clause(TaskApiAttempt.error_message))
        else:
            query = (
                db.query(Task.created_at, Task.error_message)
                .join(User, User.id == Task.user_id)
                .filter(
                    Task.created_at >= _to_db_datetime(current_start),
                    Task.created_at <= _to_db_datetime(current_end),
                    Task.status == "failed",
                    User.role != "superadmin",
                    _non_whitelisted_user_filter(),
                    _exclude_example_template_seed_task_clause(),
                )
            )
            if used_fallback_api is False:
                query = query.filter(Task.used_fallback_api.is_(False))
            if not include_unsafe_tasks:
                query = query.filter(~build_content_safety_error_clause(Task.error_message))
        if source:
            query = query.filter(Task.source == source)
        if model:
            query = query.filter(Task.model == model)
    rows = query.all()

    category_totals: dict[str, int] = defaultdict(int)
    bucket_category_counts: dict[datetime, dict[str, int]] = {
        bucket: defaultdict(int) for bucket in bucket_starts
    }

    for row in rows:
        if not row.created_at:
            continue
        bucket = _bucket_start(_to_local_datetime(row.created_at), granularity)
        if bucket not in bucket_category_counts:
            continue
        error_category = _classify_error_message_for_analytics(row.error_message)
        category_totals[error_category] += 1
        bucket_category_counts[bucket][error_category] += 1

    ranked_categories = sorted(
        category_totals.items(),
        key=lambda item: (-item[1], item[0]),
    )
    top_categories = [name for name, _count in ranked_categories[:max(limit, 1)]]

    points = []
    for bucket in bucket_starts:
        category_counts = bucket_category_counts[bucket]
        points.append(
            {
                "label": _bucket_label(bucket, granularity),
                "bucket_start": bucket,
                "bucket_end": _bucket_end(bucket, granularity),
                "total_failed_tasks": sum(category_counts.values()),
                "categories": {name: category_counts.get(name, 0) for name in top_categories},
            }
        )

    return {
        "granularity": granularity,
        "range_label": _format_range_label(current_start, current_end),
        "series": [
            {"error_category": name, "total_count": category_totals[name]}
            for name in top_categories
        ],
        "points": points,
    }


def get_error_tasks(
    db: Session,
    *,
    task_kind: str = ERROR_ANALYTICS_TASK_KIND_IMAGE,
    page: int = 1,
    page_size: int = 20,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    source: str | None = None,
    model: str | None = None,
    error_category: str | None = None,
    used_fallback_api: bool | None = None,
    include_unsafe_tasks: bool = True,
) -> dict:
    cos_config = get_optional_cos_config(db)
    if task_kind == ERROR_ANALYTICS_TASK_KIND_VIDEO:
        if used_fallback_api is True:
            query = (
                db.query(VideoTask, User)
                .join(User, User.id == VideoTask.user_id)
                .filter(
                    VideoTask.used_fallback_api.is_(True),
                    User.role != "superadmin",
                    _non_whitelisted_user_filter(),
                )
            )
        else:
            query = (
                db.query(VideoTask, User)
                .join(User, User.id == VideoTask.user_id)
                .filter(
                    VideoTask.status == "failed",
                    User.role != "superadmin",
                    _non_whitelisted_user_filter(),
                )
            )
            if used_fallback_api is False:
                query = query.filter(VideoTask.used_fallback_api.is_(False))
        if start_date:
            query = query.filter(VideoTask.created_at >= _to_db_datetime(start_date))
        if end_date:
            query = query.filter(VideoTask.created_at <= _to_db_datetime(end_date))
        if source:
            query = query.filter(VideoTask.source == source)
        if model:
            query = query.filter(VideoTask.model == model)

        rows = query.order_by(VideoTask.created_at.desc(), VideoTask.id.desc()).all()
        items: list[dict] = []
        attempts_map = _load_video_task_attempts_map(db, [int(task.id) for task, _user in rows]) if used_fallback_api is True else {}
        for task, user in rows:
            attempt_summary = {
                "primary_api_config_name": "",
                "primary_http_status": None,
                "fallback_api_config_name": "",
                "fallback_status": "unused",
                "fallback_error_message": "",
            }
            if used_fallback_api is True:
                resolved_summary = _summarize_video_task_attempts_for_error_row(
                    attempts_map.get(int(task.id), []),
                    error_category=error_category,
                )
                if resolved_summary is None:
                    continue
                attempt_summary = resolved_summary
                row_error_message = resolved_summary["primary_error_message"] or str(task.provider_error_message or task.error_message or "")
            else:
                row_error_message = str(task.provider_error_message or task.error_message or "")
                if not include_unsafe_tasks and _is_content_safety_error(row_error_message):
                    continue
                normalized_message = _normalize_error_message_for_analytics(row_error_message)
                row_error_category = _classify_error_message_for_analytics(normalized_message)
                if error_category and row_error_category != error_category:
                    continue
            if used_fallback_api is True and not include_unsafe_tasks and _is_content_safety_error(row_error_message):
                continue
            task_type = _video_task_type_for_task(task)
            items.append({
                "task_id": task.business_id or "",
                "user_id": user_external_id(user),
                "username": user.username or "",
                "avatar_url": resolve_user_avatar_url(user, cos_config=cos_config),
                "task_type": task_type,
                "model": task.model or "",
                "source": task.source or "web",
                "mode": task_type,
                "prompt": task.prompt or "",
                "status": task.status or "failed",
                "error_message": row_error_message or task.error_message or "",
                "credit_cost": int(task.credit_cost or 0),
                "credit_refunded": bool(is_video_task_credit_refunded(db, task)) if task.id else False,
                "used_fallback_api": bool(task.used_fallback_api),
                "primary_api_config_name": attempt_summary["primary_api_config_name"],
                "primary_http_status": attempt_summary["primary_http_status"],
                "fallback_api_config_name": attempt_summary["fallback_api_config_name"],
                "fallback_status": attempt_summary["fallback_status"],
                "fallback_error_message": attempt_summary["fallback_error_message"],
                "created_at": task.created_at,
            })
    else:
        if used_fallback_api is True:
            query = (
                db.query(Task, User)
                .join(User, User.id == Task.user_id)
                .filter(
                    Task.used_fallback_api.is_(True),
                    User.role != "superadmin",
                    _non_whitelisted_user_filter(),
                    _exclude_example_template_seed_task_clause(),
                )
            )
        else:
            query = (
                db.query(Task, User)
                .join(User, User.id == Task.user_id)
                .filter(
                    Task.status == "failed",
                    User.role != "superadmin",
                    _non_whitelisted_user_filter(),
                    _exclude_example_template_seed_task_clause(),
                )
            )
            if used_fallback_api is False:
                query = query.filter(Task.used_fallback_api.is_(False))
        if start_date:
            query = query.filter(Task.created_at >= _to_db_datetime(start_date))
        if end_date:
            query = query.filter(Task.created_at <= _to_db_datetime(end_date))
        if source:
            query = query.filter(Task.source == source)
        if model:
            query = query.filter(Task.model == model)

        rows = query.order_by(Task.created_at.desc(), Task.id.desc()).all()
        items = []
        scene_type_map = get_task_scene_type_map(db)
        attempts_map = _load_task_attempts_map(db, [int(task.id) for task, _user in rows]) if used_fallback_api is True else {}
        for task, user in rows:
            attempt_summary = {
                "primary_api_config_name": "",
                "primary_http_status": None,
                "fallback_api_config_name": "",
                "fallback_status": "unused",
                "fallback_error_message": "",
            }
            if used_fallback_api is True:
                resolved_summary = _summarize_task_attempts_for_error_row(
                    attempts_map.get(int(task.id), []),
                    error_category=error_category,
                )
                if resolved_summary is None:
                    continue
                attempt_summary = resolved_summary
                row_error_message = resolved_summary["primary_error_message"] or str(task.provider_error_message or task.error_message or "")
            else:
                row_error_message = str(task.provider_error_message or task.error_message or "")
                if not include_unsafe_tasks and _is_content_safety_error(row_error_message):
                    continue
                normalized_message = _normalize_error_message_for_analytics(row_error_message)
                row_error_category = _classify_error_message_for_analytics(normalized_message)
                if error_category and row_error_category != error_category:
                    continue
            if used_fallback_api is True and not include_unsafe_tasks and _is_content_safety_error(row_error_message):
                continue
            items.append({
                "task_id": task_external_id(task),
                "user_id": user_external_id(user),
                "username": user.username or "",
                "avatar_url": resolve_user_avatar_url(user, cos_config=cos_config),
                "task_type": resolve_task_type_for_task(task, scene_type_map=scene_type_map),
                "model": task.model or "",
                "source": task.source or "web",
                "mode": task.mode or "generate",
                "prompt": task.prompt or "",
                "status": task.status or "failed",
                "error_message": row_error_message or task.error_message or "",
                "credit_cost": int(task.credit_cost or 0),
                "credit_refunded": bool(is_task_generation_failure_credit_refunded(db, task.id)) if task.id else False,
                "used_fallback_api": bool(task.used_fallback_api),
                "primary_api_config_name": attempt_summary["primary_api_config_name"],
                "primary_http_status": attempt_summary["primary_http_status"],
                "fallback_api_config_name": attempt_summary["fallback_api_config_name"],
                "fallback_status": attempt_summary["fallback_status"],
                "fallback_error_message": attempt_summary["fallback_error_message"],
                "created_at": task.created_at,
            })

    total = len(items)
    start_index = max(page - 1, 0) * page_size
    page_items = items[start_index:start_index + page_size]
    return {"total": total, "items": page_items}
