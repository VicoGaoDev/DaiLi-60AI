from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.promo_reward_grant import PromoRewardGrant
from app.models.user import User
from app.services.wecom_notify_service import format_wecom_user_label, send_wecom_markdown
from app.utils.datetime_utils import now_local, to_local_naive

PROMO_REBATE_MAX_GRANTS = 5
PROMO_REBATE_RATE_FIRST = 40
PROMO_REBATE_RATE_SECOND = 30
PROMO_REBATE_RATE_NEXT = 15
PROMO_REBATE_SOURCE_PAYMENT = "payment"
PROMO_REBATE_DEFAULT_START_AT = datetime(2026, 8, 19)
logger = logging.getLogger(__name__)


_MONTH_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")


def _today_window() -> tuple[datetime, datetime]:
    today_start = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
    return today_start, today_start + timedelta(days=1)


def current_reward_month() -> str:
    now = now_local()
    return f"{now.year:04d}-{now.month:02d}"


def parse_reward_month(month: str | None) -> tuple[str, datetime, datetime] | None:
    normalized = (month or "").strip()
    if not normalized:
        return None
    matched = _MONTH_PATTERN.fullmatch(normalized)
    if not matched:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="月份格式应为 YYYY-MM")
    year = int(matched.group(1))
    month_value = int(matched.group(2))
    if month_value < 1 or month_value > 12:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="月份格式应为 YYYY-MM")
    start = datetime(year, month_value, 1)
    if month_value == 12:
        exclusive_end = datetime(year + 1, 1, 1)
    else:
        exclusive_end = datetime(year, month_value + 1, 1)
    return f"{year:04d}-{month_value:02d}", start, exclusive_end


def fen_to_yuan(amount_fen: int | None) -> float:
    return round(int(amount_fen or 0) / 100, 2)


def promo_rebate_rate_for_index(reward_index: int) -> int | None:
    if reward_index < 1 or reward_index > PROMO_REBATE_MAX_GRANTS:
        return None
    if reward_index == 1:
        return PROMO_REBATE_RATE_FIRST
    if reward_index == 2:
        return PROMO_REBATE_RATE_SECOND
    return PROMO_REBATE_RATE_NEXT


def promo_reward_rule_payload() -> dict:
    return {
        "first_rate": PROMO_REBATE_RATE_FIRST,
        "second_rate": PROMO_REBATE_RATE_SECOND,
        "next_rate": PROMO_REBATE_RATE_NEXT,
        "first_count": 1,
        "max_reward_count": PROMO_REBATE_MAX_GRANTS,
        "start_at": promo_rebate_start_at(),
    }


def promo_rebate_start_at() -> datetime:
    raw_value = (settings.PROMO_REBATE_START_AT or "").strip()
    if not raw_value:
        return PROMO_REBATE_DEFAULT_START_AT
    try:
        return to_local_naive(datetime.fromisoformat(raw_value))
    except ValueError:
        logger.warning("Invalid PROMO_REBATE_START_AT, fallback to default: %s", raw_value)
        return PROMO_REBATE_DEFAULT_START_AT


def is_promo_rebate_eligible_invitee(invitee: User) -> bool:
    if not invitee.created_at:
        return False
    return to_local_naive(invitee.created_at) >= promo_rebate_start_at()


def get_promo_reward_summary(db: Session, owner: User, *, month: str | None = None) -> dict:
    today_start, tomorrow_start = _today_window()
    month_window = parse_reward_month(month)
    total_reward_amount_fen = (
        db.query(func.coalesce(func.sum(PromoRewardGrant.reward_amount_fen), 0))
        .filter(PromoRewardGrant.referrer_id == owner.id)
        .scalar()
        or 0
    )
    today_reward_amount_fen = (
        db.query(func.coalesce(func.sum(PromoRewardGrant.reward_amount_fen), 0))
        .filter(
            PromoRewardGrant.referrer_id == owner.id,
            PromoRewardGrant.created_at >= today_start,
            PromoRewardGrant.created_at < tomorrow_start,
        )
        .scalar()
        or 0
    )
    reward_grant_count = (
        db.query(func.count(PromoRewardGrant.id))
        .filter(PromoRewardGrant.referrer_id == owner.id)
        .scalar()
        or 0
    )
    rewarded_invitees = (
        db.query(func.count(func.distinct(PromoRewardGrant.invitee_id)))
        .filter(PromoRewardGrant.referrer_id == owner.id)
        .scalar()
        or 0
    )
    month_reward_amount_fen = 0
    month_reward_grant_count = 0
    selected_month = ""
    if month_window:
        selected_month, month_start, month_end = month_window
        month_reward_amount_fen = (
            db.query(func.coalesce(func.sum(PromoRewardGrant.reward_amount_fen), 0))
            .filter(
                PromoRewardGrant.referrer_id == owner.id,
                PromoRewardGrant.created_at >= month_start,
                PromoRewardGrant.created_at < month_end,
            )
            .scalar()
            or 0
        )
        month_reward_grant_count = (
            db.query(func.count(PromoRewardGrant.id))
            .filter(
                PromoRewardGrant.referrer_id == owner.id,
                PromoRewardGrant.created_at >= month_start,
                PromoRewardGrant.created_at < month_end,
            )
            .scalar()
            or 0
        )
    return {
        **promo_reward_rule_payload(),
        "rewarded_invitees": int(rewarded_invitees),
        "reward_grant_count": int(reward_grant_count),
        "total_reward_amount_fen": int(total_reward_amount_fen),
        "total_reward_amount_yuan": fen_to_yuan(total_reward_amount_fen),
        "today_reward_amount_fen": int(today_reward_amount_fen),
        "today_reward_amount_yuan": fen_to_yuan(today_reward_amount_fen),
        "month": selected_month,
        "month_reward_grant_count": int(month_reward_grant_count),
        "month_reward_amount_fen": int(month_reward_amount_fen),
        "month_reward_amount_yuan": fen_to_yuan(month_reward_amount_fen),
    }


def _apply_grant_time_filter(query, start_date: datetime | None, end_date: datetime | None):
    if start_date is not None:
        query = query.filter(PromoRewardGrant.created_at >= start_date)
    if end_date is not None:
        query = query.filter(PromoRewardGrant.created_at <= end_date)
    return query


def get_promo_reward_period_summary(
    db: Session,
    owner: User,
    *,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    amount_query = db.query(func.coalesce(func.sum(PromoRewardGrant.reward_amount_fen), 0)).filter(
        PromoRewardGrant.referrer_id == owner.id
    )
    count_query = db.query(func.count(PromoRewardGrant.id)).filter(PromoRewardGrant.referrer_id == owner.id)
    invitee_query = db.query(func.count(func.distinct(PromoRewardGrant.invitee_id))).filter(
        PromoRewardGrant.referrer_id == owner.id
    )
    amount_query = _apply_grant_time_filter(amount_query, start_date, end_date)
    count_query = _apply_grant_time_filter(count_query, start_date, end_date)
    invitee_query = _apply_grant_time_filter(invitee_query, start_date, end_date)
    period_reward_amount_fen = amount_query.scalar() or 0
    return {
        "period_rewarded_invitees": int(invitee_query.scalar() or 0),
        "period_reward_grant_count": int(count_query.scalar() or 0),
        "period_reward_amount_fen": int(period_reward_amount_fen),
        "period_reward_amount_yuan": fen_to_yuan(period_reward_amount_fen),
    }


def list_promo_reward_aggregates_by_invitee(
    db: Session,
    owner: User,
    *,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict[int, dict]:
    query = (
        db.query(
            PromoRewardGrant.invitee_id,
            func.count(PromoRewardGrant.id),
            func.coalesce(func.sum(PromoRewardGrant.reward_amount_fen), 0),
            func.max(PromoRewardGrant.created_at),
        )
        .filter(PromoRewardGrant.referrer_id == owner.id)
    )
    query = _apply_grant_time_filter(query, start_date, end_date)
    rows = query.group_by(PromoRewardGrant.invitee_id).all()
    return {
        int(invitee_id): {
            "reward_count": int(count or 0),
            "total_reward_amount_fen": int(amount_fen or 0),
            "total_reward_amount_yuan": fen_to_yuan(amount_fen),
            "last_reward_at": last_reward_at,
        }
        for invitee_id, count, amount_fen, last_reward_at in rows
        if invitee_id
    }


def list_promo_reward_grants_by_source_id(db: Session, owner: User, source_ids: list[str]) -> dict[str, PromoRewardGrant]:
    normalized_ids = [item for item in source_ids if item]
    if not normalized_ids:
        return {}
    grants = (
        db.query(PromoRewardGrant)
        .filter(
            PromoRewardGrant.referrer_id == owner.id,
            PromoRewardGrant.source_type == PROMO_REBATE_SOURCE_PAYMENT,
            PromoRewardGrant.source_id.in_(normalized_ids),
        )
        .all()
    )
    return {str(grant.source_id): grant for grant in grants if grant.source_id}


def apply_promo_reward(
    db: Session,
    *,
    invitee_id: int,
    source_type: str,
    source_id: str,
    source_credits: int,
    source_amount_fen: int,
) -> PromoRewardGrant | None:
    normalized_source_type = (source_type or "").strip()
    normalized_source_id = (source_id or "").strip()
    credits = int(source_credits or 0)
    amount_fen = int(source_amount_fen or 0)
    if normalized_source_type != PROMO_REBATE_SOURCE_PAYMENT:
        return None
    if not normalized_source_id or amount_fen <= 0:
        return None

    invitee = (
        db.query(User)
        .filter(User.id == invitee_id)
        .with_for_update()
        .populate_existing()
        .first()
    )
    if not invitee or not invitee.referrer_id or int(invitee.referrer_id) == int(invitee.id):
        return None
    if not invitee.used_promo_code_id:
        return None
    if not is_promo_rebate_eligible_invitee(invitee):
        return None

    referrer = db.query(User).filter(User.id == invitee.referrer_id, User.status == "active").first()
    if not referrer or not referrer.is_whitelisted:
        return None

    existing_source = (
        db.query(PromoRewardGrant)
        .filter(
            PromoRewardGrant.referrer_id == referrer.id,
            PromoRewardGrant.source_type == normalized_source_type,
            PromoRewardGrant.source_id == normalized_source_id,
        )
        .first()
    )
    if existing_source:
        return None

    rewarded_count = (
        db.query(func.count(PromoRewardGrant.id))
        .filter(
            PromoRewardGrant.referrer_id == referrer.id,
            PromoRewardGrant.invitee_id == invitee.id,
        )
        .scalar()
        or 0
    )
    reward_index = int(rewarded_count) + 1
    reward_rate = promo_rebate_rate_for_index(reward_index)
    if reward_rate is None:
        return None

    reward_amount_fen = amount_fen * reward_rate // 100
    if reward_amount_fen <= 0:
        return None

    grant = PromoRewardGrant(
        referrer_id=referrer.id,
        invitee_id=invitee.id,
        promo_code_id=int(invitee.used_promo_code_id) if invitee.used_promo_code_id else None,
        source_type=normalized_source_type,
        source_id=normalized_source_id,
        source_credits=credits,
        source_amount_fen=amount_fen,
        reward_rate=reward_rate,
        reward_amount_fen=reward_amount_fen,
        reward_index=reward_index,
    )
    db.add(grant)
    db.flush()
    _send_promo_reward_notification(
        referrer=referrer,
        invitee=invitee,
        grant=grant,
    )
    return grant


def apply_promo_reward_safely(
    db: Session,
    *,
    invitee_id: int,
    source_type: str,
    source_id: str,
    source_credits: int,
    source_amount_fen: int,
) -> PromoRewardGrant | None:
    try:
        with db.begin_nested():
            return apply_promo_reward(
                db,
                invitee_id=invitee_id,
                source_type=source_type,
                source_id=source_id,
                source_credits=source_credits,
                source_amount_fen=source_amount_fen,
            )
    except Exception:
        logger.exception(
            "failed to apply promo reward",
            extra={
                "event": "promo_reward.apply_failed",
                "invitee_id": invitee_id,
                "source_type": source_type,
                "source_id": source_id,
            },
        )
        return None


def _build_user_label(user: User) -> str:
    return format_wecom_user_label(user)


def _send_promo_reward_notification(
    *,
    referrer: User,
    invitee: User,
    grant: PromoRewardGrant,
) -> None:
    send_wecom_markdown(
        "## 💰 推广现金返利已记账\n"
        f"> 👤 推广人: **{_build_user_label(referrer)}**\n"
        f"> 🙋 被推广用户: **{_build_user_label(invitee)}**\n"
        f"> 🔖 订单号: `{grant.source_id}`\n"
        f"> 💵 订单金额: **¥{fen_to_yuan(grant.source_amount_fen):.2f}**\n"
        f"> 🎁 返利比例: **{int(grant.reward_rate or 0)}%**\n"
        f"> 🎁 记账返利: **¥{fen_to_yuan(grant.reward_amount_fen):.2f}**\n"
        f"> 🔁 第 **{int(grant.reward_index or 0)}** 次返利\n"
        f"> ⏰ 记账时间: {now_local().strftime('%Y-%m-%d %H:%M:%S')}\n"
        "> ℹ️ 仅统计金额，平台不支持提现"
    )
