from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.credit_redeem_key import CreditRedeemKey
from app.models.payment_order import PaymentOrder
from app.models.user import User
from app.models.user_promo_code import UserPromoCode
from app.services.business_id_service import user_external_id
from app.services.promo_reward_service import (
    fen_to_yuan,
    get_promo_reward_period_summary,
    get_promo_reward_summary,
    list_promo_reward_aggregates_by_invitee,
    list_promo_reward_grants_by_source_id,
    parse_reward_month,
)
from app.utils.datetime_utils import to_local_naive

PROMO_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PROMO_CODE_LENGTH = 8
PROMO_CODE_REWARD_CREDITS = 20


def normalize_promo_code(code: str | None) -> str:
    return "".join((code or "").strip().upper().split())


def build_promo_link(base_url: str, promo_code: str) -> str:
    normalized_base = (base_url or "").strip().rstrip("/")
    if not normalized_base:
        normalized_base = "/"
    code = normalize_promo_code(promo_code)
    if not code:
        return normalized_base
    separator = "&" if "?" in normalized_base else "?"
    return f"{normalized_base}{separator}{urlencode({'promo': code})}"


def ensure_promo_access(user: User) -> None:
    if not user.is_whitelisted:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅白名单用户可使用推广码功能")


def _generate_unique_promo_code(db: Session) -> str:
    while True:
        code = "".join(secrets.choice(PROMO_CODE_ALPHABET) for _ in range(PROMO_CODE_LENGTH))
        exists = (
            db.query(UserPromoCode.id).filter(UserPromoCode.code == code).first()
            or db.query(User.id).filter(User.invite_code == code).first()
        )
        if not exists:
            return code


def get_valid_promo_code(db: Session, raw_code: str | None) -> UserPromoCode | None:
    code = normalize_promo_code(raw_code)
    if not code:
        return None
    promo = (
        db.query(UserPromoCode)
        .join(User, User.id == UserPromoCode.user_id)
        .filter(
            UserPromoCode.code == code,
            UserPromoCode.status == "enabled",
            User.is_whitelisted.is_(True),
            User.status == "active",
        )
        .first()
    )
    if not promo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="推广码无效或已停用")
    return promo


def create_promo_code(db: Session, user: User, platform_name: str) -> UserPromoCode:
    ensure_promo_access(user)
    normalized_platform = (platform_name or "").strip()
    if not normalized_platform:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入平台名称")
    if len(normalized_platform) > 50:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="平台名称不能超过50个字符")

    promo = UserPromoCode(
        user_id=user.id,
        code=_generate_unique_promo_code(db),
        platform_name=normalized_platform,
        status="enabled",
    )
    db.add(promo)
    db.commit()
    db.refresh(promo)
    return promo


def update_promo_code_platform(db: Session, user: User, promo_code_id: int, platform_name: str) -> UserPromoCode:
    ensure_promo_access(user)
    normalized_platform = (platform_name or "").strip()
    if not normalized_platform:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入平台名称")
    if len(normalized_platform) > 50:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="平台名称不能超过50个字符")

    promo = (
        db.query(UserPromoCode)
        .filter(UserPromoCode.id == promo_code_id, UserPromoCode.user_id == user.id)
        .first()
    )
    if not promo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="推广码不存在")
    promo.platform_name = normalized_platform
    db.add(promo)
    db.commit()
    db.refresh(promo)
    return promo


def _build_promo_codes_payload(db: Session, owner: User, *, base_url: str = "", month: str | None = None) -> dict:
    promo_codes = (
        db.query(UserPromoCode)
        .filter(UserPromoCode.user_id == owner.id)
        .order_by(UserPromoCode.created_at.desc(), UserPromoCode.id.desc())
        .all()
    )

    promo_ids = [promo.id for promo in promo_codes]
    referral_counts: dict[int, int] = {}
    if promo_ids:
        rows = (
            db.query(User.used_promo_code_id, func.count(User.id))
            .filter(User.used_promo_code_id.in_(promo_ids))
            .group_by(User.used_promo_code_id)
            .all()
        )
        referral_counts = {int(promo_id): int(count) for promo_id, count in rows if promo_id}

    total_referrals = (
        db.query(func.count(User.id))
        .filter(User.referrer_id == owner.id)
        .scalar()
        or 0
    )
    used_code_count = sum(1 for promo in promo_codes if referral_counts.get(promo.id, 0) > 0)
    reward_summary = get_promo_reward_summary(db, owner, month=month)

    return {
        "summary": {
            "total_referrals": int(total_referrals),
            "used_code_count": int(used_code_count),
            "rewarded_registrations": int(total_referrals),
            **reward_summary,
        },
        "items": [
            {
                "id": promo.id,
                "code": promo.code,
                "platform_name": promo.platform_name,
                "status": promo.status,
                "created_at": promo.created_at,
                "referral_count": referral_counts.get(promo.id, 0),
                "promo_link": build_promo_link(base_url, promo.code) if base_url else "",
            }
            for promo in promo_codes
        ],
    }


def _mask_email(email: str | None) -> str:
    normalized = (email or "").strip()
    if not normalized or "@" not in normalized:
        return "-"
    name, domain = normalized.split("@", 1)
    if len(name) <= 2:
        return f"{name[:1]}***@{domain}"
    return f"{name[:2]}***@{domain}"


def _normalize_filter_dates(
    start_date: datetime | None,
    end_date: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    return (
        to_local_naive(start_date) if start_date is not None else None,
        to_local_naive(end_date) if end_date is not None else None,
    )


def resolve_promo_filter_window(
    *,
    month: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> tuple[datetime | None, datetime | None]:
    normalized_start, normalized_end = _normalize_filter_dates(start_date, end_date)
    if normalized_start is not None or normalized_end is not None:
        return normalized_start, normalized_end
    parsed = parse_reward_month(month)
    if not parsed:
        return None, None
    _, month_start, month_exclusive_end = parsed
    return month_start, month_exclusive_end - timedelta(microseconds=1)


def _get_referred_user_rows(
    db: Session,
    owner: User,
    *,
    keyword: str | None = None,
    platform_name: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[tuple[User, UserPromoCode | None]]:
    query = (
        db.query(User, UserPromoCode)
        .outerjoin(UserPromoCode, UserPromoCode.id == User.used_promo_code_id)
        .filter(User.referrer_id == owner.id)
    )
    normalized_keyword = (keyword or "").strip().lower()
    if normalized_keyword:
        like_keyword = f"%{normalized_keyword}%"
        query = query.filter(
            func.lower(User.username).like(like_keyword)
            | func.lower(func.coalesce(User.email, "")).like(like_keyword)
        )
    normalized_platform = (platform_name or "").strip()
    if normalized_platform:
        query = query.filter(UserPromoCode.platform_name == normalized_platform)
    normalized_start, normalized_end = _normalize_filter_dates(start_date, end_date)
    if normalized_start is not None:
        query = query.filter(User.created_at >= normalized_start)
    if normalized_end is not None:
        query = query.filter(User.created_at <= normalized_end)
    return query.order_by(User.created_at.desc(), User.id.desc()).all()


def _build_promo_referrals_payload(
    db: Session,
    owner: User,
    *,
    keyword: str | None = None,
    platform_name: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    rows = _get_referred_user_rows(
        db,
        owner,
        keyword=keyword,
        platform_name=platform_name,
        start_date=start_date,
        end_date=end_date,
    )
    reward_map = list_promo_reward_aggregates_by_invitee(
        db,
        owner,
        start_date=start_date,
        end_date=end_date,
    )

    return {
        "total": len(rows),
        "items": [
            {
                "user_id": user_external_id(invitee),
                "username": invitee.username,
                "email_masked": _mask_email(invitee.email),
                "email": invitee.email,
                "promo_code": promo.code if promo else "",
                "platform_name": promo.platform_name if promo else "",
                "reward_credits": PROMO_CODE_REWARD_CREDITS,
                "reward_count": int(reward_map.get(invitee.id, {}).get("reward_count") or 0),
                "total_reward_amount_yuan": float(
                    reward_map.get(invitee.id, {}).get("total_reward_amount_yuan") or 0
                ),
                "last_reward_at": reward_map.get(invitee.id, {}).get("last_reward_at"),
                "registered_at": invitee.created_at,
            }
            for invitee, promo in rows
        ],
    }


def get_my_promo_codes(db: Session, user: User, *, base_url: str = "", month: str | None = None) -> dict:
    ensure_promo_access(user)
    return _build_promo_codes_payload(db, user, base_url=base_url, month=month)


def get_my_promo_referrals(
    db: Session,
    user: User,
    *,
    keyword: str | None = None,
    platform_name: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    ensure_promo_access(user)
    return _build_promo_referrals_payload(
        db,
        user,
        keyword=keyword,
        platform_name=platform_name,
        start_date=start_date,
        end_date=end_date,
    )


def _build_promo_referral_activities_payload(
    db: Session,
    owner: User,
    *,
    keyword: str | None = None,
    platform_name: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    filter_invitees_by_date: bool = True,
) -> dict:
    referred_rows = _get_referred_user_rows(
        db,
        owner,
        keyword=keyword,
        platform_name=platform_name,
        start_date=start_date if filter_invitees_by_date else None,
        end_date=end_date if filter_invitees_by_date else None,
    )
    referred_users = [invitee for invitee, _ in referred_rows]
    referred_user_ids = [invitee.id for invitee in referred_users]
    if not referred_user_ids:
        return {"total": 0, "items": []}

    payments_query = db.query(PaymentOrder).filter(PaymentOrder.user_id.in_(referred_user_ids))
    payments_query = payments_query.filter(PaymentOrder.credited_at.is_not(None))
    redeem_query = db.query(CreditRedeemKey).filter(CreditRedeemKey.used_by_user_id.in_(referred_user_ids))
    redeem_query = redeem_query.filter(CreditRedeemKey.used_at.is_not(None))
    normalized_start, normalized_end = _normalize_filter_dates(start_date, end_date)
    if normalized_start is not None:
        payments_query = payments_query.filter(PaymentOrder.credited_at >= normalized_start)
        redeem_query = redeem_query.filter(CreditRedeemKey.used_at >= normalized_start)
    if normalized_end is not None:
        payments_query = payments_query.filter(PaymentOrder.credited_at <= normalized_end)
        redeem_query = redeem_query.filter(CreditRedeemKey.used_at <= normalized_end)

    user_map = {invitee.id: invitee for invitee in referred_users}
    payment_orders = payments_query.order_by(PaymentOrder.credited_at.desc(), PaymentOrder.id.desc()).all()
    grant_map = list_promo_reward_grants_by_source_id(
        db,
        owner,
        [str(order.order_no or "") for order in payment_orders],
    )
    items: list[dict] = []
    for order in payment_orders:
        invitee = user_map.get(order.user_id)
        if not invitee:
            continue
        grant = grant_map.get(str(order.order_no or ""))
        items.append(
            {
                "user_id": user_external_id(invitee),
                "username": invitee.username,
                "email_masked": _mask_email(invitee.email),
                "activity_type": "purchase",
                "credits": int(order.credits or 0),
                "amount_fen": int(order.amount_fen or 0),
                "amount_yuan": round(int(order.amount_fen or 0) / 100, 2),
                "reward_rate": int(grant.reward_rate) if grant else None,
                "reward_index": int(grant.reward_index) if grant else None,
                "reward_amount_fen": int(grant.reward_amount_fen) if grant else None,
                "reward_amount_yuan": fen_to_yuan(grant.reward_amount_fen) if grant else None,
                "redeem_key": "",
                "order_no": order.order_no,
                "occurred_at": order.credited_at,
            }
        )
    for redeem in redeem_query.order_by(CreditRedeemKey.used_at.desc(), CreditRedeemKey.id.desc()).all():
        invitee = user_map.get(redeem.used_by_user_id)
        if not invitee:
            continue
        items.append(
            {
                "user_id": user_external_id(invitee),
                "username": invitee.username,
                "email_masked": _mask_email(invitee.email),
                "activity_type": "redeem",
                "credits": int(redeem.credit_amount or 0),
                "amount_fen": None,
                "amount_yuan": None,
                "reward_rate": None,
                "reward_index": None,
                "reward_amount_fen": None,
                "reward_amount_yuan": None,
                "redeem_key": redeem.redeem_key,
                "order_no": "",
                "occurred_at": redeem.used_at,
            }
        )

    items.sort(key=lambda item: item.get("occurred_at") or datetime.min, reverse=True)
    return {"total": len(items), "items": items}


def get_my_promo_referral_activities(
    db: Session,
    user: User,
    *,
    keyword: str | None = None,
    platform_name: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    ensure_promo_access(user)
    return _build_promo_referral_activities_payload(
        db,
        user,
        keyword=keyword,
        platform_name=platform_name,
        start_date=start_date,
        end_date=end_date,
    )


def get_user_promo_dashboard_for_admin(
    db: Session,
    owner: User,
    *,
    require_whitelist: bool = True,
    month: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    if require_whitelist and not owner.is_whitelisted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该用户不是白名单用户")
    period_start, period_end = resolve_promo_filter_window(
        month=month,
        start_date=start_date,
        end_date=end_date,
    )
    promo_payload = _build_promo_codes_payload(db, owner, month=month)
    referrals_payload = _build_promo_referrals_payload(
        db,
        owner,
        start_date=period_start,
        end_date=period_end,
    )
    activities_payload = _build_promo_referral_activities_payload(
        db,
        owner,
        start_date=period_start,
        end_date=period_end,
        filter_invitees_by_date=False,
    )
    period_stats = get_promo_reward_period_summary(
        db,
        owner,
        start_date=period_start,
        end_date=period_end,
    )
    return {
        "user_id": user_external_id(owner),
        "username": owner.username,
        "summary": {
            **promo_payload["summary"],
            **period_stats,
            "period_referrals": int(referrals_payload["total"]),
            "period_start": period_start,
            "period_end": period_end,
        },
        "promo_codes": promo_payload["items"],
        "referrals": referrals_payload["items"],
        "activities": activities_payload["items"],
    }
