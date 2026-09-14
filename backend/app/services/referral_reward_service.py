from __future__ import annotations

import secrets
import logging
from datetime import datetime, timedelta
from urllib.parse import urlencode

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.referral_reward_grant import ReferralRewardGrant
from app.models.user import User
from app.models.user_promo_code import UserPromoCode
from app.services.business_id_service import user_external_id
from app.services.user_credit_service import change_user_credit_balance, get_user_credit_account
from app.services.wecom_notify_service import format_wecom_user_label, send_wecom_markdown
from app.utils.datetime_utils import now_local

INVITE_CODE_PREFIX = "U"
INVITE_CODE_LENGTH = 8
INVITE_CODE_RANDOM_LENGTH = INVITE_CODE_LENGTH - len(INVITE_CODE_PREFIX)
INVITE_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
REFERRAL_REWARD_RATE = 15
REFERRAL_REWARD_MAX_GRANTS_PER_INVITEE = 3
REFERRAL_SOURCE_PAYMENT = "payment"
REFERRAL_SOURCE_REDEEM = "redeem"
logger = logging.getLogger(__name__)


def _today_window() -> tuple[datetime, datetime]:
    today_start = now_local().replace(hour=0, minute=0, second=0, microsecond=0)
    return today_start, today_start + timedelta(days=1)


def normalize_invite_code(code: str | None) -> str:
    return "".join((code or "").strip().upper().split())


def is_personal_invite_code(code: str | None) -> bool:
    normalized = normalize_invite_code(code)
    return (
        len(normalized) == INVITE_CODE_LENGTH
        and normalized.startswith(INVITE_CODE_PREFIX)
        and all(char in INVITE_CODE_ALPHABET for char in normalized[1:])
    )


def _generate_candidate_invite_code() -> str:
    suffix = "".join(secrets.choice(INVITE_CODE_ALPHABET) for _ in range(INVITE_CODE_RANDOM_LENGTH))
    return f"{INVITE_CODE_PREFIX}{suffix}"


def _invite_code_exists(db: Session, code: str) -> bool:
    return (
        db.query(User.id).filter(User.invite_code == code).first() is not None
        or db.query(UserPromoCode.id).filter(UserPromoCode.code == code).first() is not None
    )


def generate_unique_invite_code(db: Session) -> str:
    while True:
        code = _generate_candidate_invite_code()
        if not _invite_code_exists(db, code):
            return code


def ensure_user_invite_code(db: Session, user: User) -> str:
    existing_code = normalize_invite_code(user.invite_code)
    if is_personal_invite_code(existing_code) and not _promo_code_exists(db, existing_code):
        return existing_code
    user.invite_code = generate_unique_invite_code(db)
    db.add(user)
    db.flush()
    return user.invite_code


def backfill_user_invite_codes(db: Session) -> int:
    changed = 0
    users = db.query(User).order_by(User.id.asc()).all()
    for user in users:
        existing_code = normalize_invite_code(user.invite_code)
        if is_personal_invite_code(existing_code) and not _promo_code_exists(db, existing_code):
            continue
        user.invite_code = generate_unique_invite_code(db)
        db.add(user)
        db.flush()
        changed += 1
    return changed


def _promo_code_exists(db: Session, code: str) -> bool:
    return db.query(UserPromoCode.id).filter(UserPromoCode.code == code).first() is not None


def get_user_by_invite_code(db: Session, raw_code: str | None) -> User | None:
    code = normalize_invite_code(raw_code)
    if not is_personal_invite_code(code):
        return None
    return db.query(User).filter(User.invite_code == code, User.status == "active").first()


def validate_personal_invite_code(db: Session, raw_code: str | None) -> User:
    user = get_user_by_invite_code(db, raw_code)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邀请码无效或已停用")
    return user


def _mask_email(email: str | None) -> str:
    normalized = (email or "").strip()
    if not normalized or "@" not in normalized:
        return "-"
    name, domain = normalized.split("@", 1)
    if len(name) <= 2:
        return f"{name[:1]}***@{domain}"
    return f"{name[:2]}***@{domain}"


def build_invite_link(base_url: str, invite_code: str) -> str:
    normalized_base = (base_url or "").strip().rstrip("/")
    if not normalized_base:
        normalized_base = "/"
    separator = "&" if "?" in normalized_base else "?"
    return f"{normalized_base}{separator}{urlencode({'invite': invite_code})}"


def get_invite_reward_overview(db: Session, user: User, *, base_url: str) -> dict:
    invite_code = ensure_user_invite_code(db, user)
    today_start, tomorrow_start = _today_window()
    total_referrals = (
        db.query(func.count(User.id))
        .filter(User.referrer_id == user.id, User.used_promo_code_id.is_(None))
        .scalar()
        or 0
    )
    today_referrals = (
        db.query(func.count(User.id))
        .filter(
            User.referrer_id == user.id,
            User.used_promo_code_id.is_(None),
            User.created_at >= today_start,
            User.created_at < tomorrow_start,
        )
        .scalar()
        or 0
    )
    total_reward_credits = (
        db.query(func.coalesce(func.sum(ReferralRewardGrant.reward_credits), 0))
        .join(User, User.id == ReferralRewardGrant.invitee_id)
        .filter(ReferralRewardGrant.referrer_id == user.id)
        .filter(User.used_promo_code_id.is_(None))
        .scalar()
        or 0
    )
    today_reward_credits = (
        db.query(func.coalesce(func.sum(ReferralRewardGrant.reward_credits), 0))
        .join(User, User.id == ReferralRewardGrant.invitee_id)
        .filter(
            ReferralRewardGrant.referrer_id == user.id,
            User.used_promo_code_id.is_(None),
            ReferralRewardGrant.created_at >= today_start,
            ReferralRewardGrant.created_at < tomorrow_start,
        )
        .scalar()
        or 0
    )
    reward_grant_count = (
        db.query(func.count(ReferralRewardGrant.id))
        .join(User, User.id == ReferralRewardGrant.invitee_id)
        .filter(ReferralRewardGrant.referrer_id == user.id)
        .filter(User.used_promo_code_id.is_(None))
        .scalar()
        or 0
    )
    rewarded_invitee_count = (
        db.query(func.count(func.distinct(ReferralRewardGrant.invitee_id)))
        .join(User, User.id == ReferralRewardGrant.invitee_id)
        .filter(ReferralRewardGrant.referrer_id == user.id)
        .filter(User.used_promo_code_id.is_(None))
        .scalar()
        or 0
    )
    return {
        "invite_code": invite_code,
        "invite_link": build_invite_link(base_url, invite_code),
        "reward_rate": REFERRAL_REWARD_RATE,
        "max_reward_count": REFERRAL_REWARD_MAX_GRANTS_PER_INVITEE,
        "summary": {
            "total_referrals": int(total_referrals),
            "today_referrals": int(today_referrals),
            "rewarded_invitees": int(rewarded_invitee_count),
            "reward_grant_count": int(reward_grant_count),
            "total_reward_credits": int(total_reward_credits),
            "today_reward_credits": int(today_reward_credits),
        },
    }


def list_invite_reward_referrals(db: Session, user: User, *, page: int = 1, page_size: int = 10) -> dict:
    normalized_page = max(int(page or 1), 1)
    normalized_page_size = max(1, min(int(page_size or 10), 100))
    query = (
        db.query(User)
        .filter(User.referrer_id == user.id, User.used_promo_code_id.is_(None))
    )
    total = int(query.count() or 0)
    rows = (
        query
        .order_by(User.created_at.desc(), User.id.desc())
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
        .all()
    )
    invitee_ids = [row.id for row in rows]
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
                ReferralRewardGrant.referrer_id == user.id,
                ReferralRewardGrant.invitee_id.in_(invitee_ids),
            )
            .group_by(ReferralRewardGrant.invitee_id)
            .all()
        )
        reward_map = {
            int(invitee_id): {
                "reward_count": int(reward_count or 0),
                "total_reward_credits": int(total_reward_credits or 0),
                "last_reward_at": last_reward_at,
            }
            for invitee_id, reward_count, total_reward_credits, last_reward_at in reward_rows
        }

    items = []
    for row in rows:
        rewards = reward_map.get(row.id, {})
        items.append(
            {
                "user_id": user_external_id(row),
                "username": row.username,
                "email_masked": _mask_email(row.email),
                "reward_count": int(rewards.get("reward_count") or 0),
                "total_reward_credits": int(rewards.get("total_reward_credits") or 0),
                "last_reward_at": rewards.get("last_reward_at"),
                "registered_at": row.created_at,
            }
        )
    return {
        "total": total,
        "items": items,
        "page": normalized_page,
        "page_size": normalized_page_size,
    }


def list_invite_reward_logs(db: Session, user: User, *, page: int = 1, page_size: int = 10) -> dict:
    normalized_page = max(int(page or 1), 1)
    normalized_page_size = max(1, min(int(page_size or 10), 100))
    query = (
        db.query(ReferralRewardGrant, User)
        .join(User, User.id == ReferralRewardGrant.invitee_id)
        .filter(ReferralRewardGrant.referrer_id == user.id, User.used_promo_code_id.is_(None))
    )
    total = int(query.count() or 0)
    rows = (
        query
        .order_by(ReferralRewardGrant.created_at.desc(), ReferralRewardGrant.id.desc())
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
        .all()
    )
    items = []
    for grant, invitee in rows:
        items.append(
            {
                "id": grant.id,
                "invitee_user_id": user_external_id(invitee),
                "invitee_username": invitee.username,
                "invitee_email_masked": _mask_email(invitee.email),
                "source_type": grant.source_type,
                "source_id": grant.source_id,
                "source_credits": int(grant.source_credits or 0),
                "reward_rate": int(grant.reward_rate or 0),
                "reward_credits": int(grant.reward_credits or 0),
                "reward_index": int(grant.reward_index or 0),
                "created_at": grant.created_at,
            }
        )
    return {
        "total": total,
        "items": items,
        "page": normalized_page,
        "page_size": normalized_page_size,
    }


def apply_referral_reward(
    db: Session,
    *,
    invitee_id: int,
    source_type: str,
    source_id: str,
    source_credits: int,
) -> ReferralRewardGrant | None:
    normalized_source_type = (source_type or "").strip()
    normalized_source_id = (source_id or "").strip()
    credits = int(source_credits or 0)
    if normalized_source_type != REFERRAL_SOURCE_PAYMENT:
        return None
    if not normalized_source_id or credits <= 0:
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
    if invitee.used_promo_code_id:
        return None

    referrer = db.query(User).filter(User.id == invitee.referrer_id, User.status == "active").first()
    if not referrer:
        return None

    existing_source = (
        db.query(ReferralRewardGrant)
        .filter(
            ReferralRewardGrant.referrer_id == referrer.id,
            ReferralRewardGrant.source_type == normalized_source_type,
            ReferralRewardGrant.source_id == normalized_source_id,
        )
        .first()
    )
    if existing_source:
        return None

    rewarded_count = (
        db.query(func.count(ReferralRewardGrant.id))
        .filter(
            ReferralRewardGrant.referrer_id == referrer.id,
            ReferralRewardGrant.invitee_id == invitee.id,
        )
        .scalar()
        or 0
    )
    if int(rewarded_count) >= REFERRAL_REWARD_MAX_GRANTS_PER_INVITEE:
        return None

    reward_credits = credits * REFERRAL_REWARD_RATE // 100
    if reward_credits <= 0:
        return None

    reward_index = int(rewarded_count) + 1
    grant = ReferralRewardGrant(
        referrer_id=referrer.id,
        invitee_id=invitee.id,
        source_type=normalized_source_type,
        source_id=normalized_source_id,
        source_credits=credits,
        reward_rate=REFERRAL_REWARD_RATE,
        reward_credits=reward_credits,
        reward_index=reward_index,
    )
    db.add(grant)
    db.flush()
    change_user_credit_balance(
        db,
        referrer.id,
        delta=reward_credits,
        log_type="allocate",
        description=_build_reward_description(invitee, normalized_source_type, normalized_source_id, reward_index),
    )
    _send_referral_reward_notification(
        db,
        referrer=referrer,
        invitee=invitee,
        grant=grant,
    )
    return grant


def apply_referral_reward_safely(
    db: Session,
    *,
    invitee_id: int,
    source_type: str,
    source_id: str,
    source_credits: int,
) -> ReferralRewardGrant | None:
    try:
        with db.begin_nested():
            return apply_referral_reward(
                db,
                invitee_id=invitee_id,
                source_type=source_type,
                source_id=source_id,
                source_credits=source_credits,
            )
    except Exception:
        logger.exception(
            "failed to apply referral reward",
            extra={
                "event": "referral_reward.apply_failed",
                "invitee_id": invitee_id,
                "source_type": source_type,
                "source_id": source_id,
            },
        )
        return None


def _build_reward_description(invitee: User, source_type: str, source_id: str, reward_index: int) -> str:
    source_label = "在线购买" if source_type == REFERRAL_SOURCE_PAYMENT else "兑换码兑换"
    username = (invitee.username or "").strip() or f"ID {invitee.id}"
    return f"邀请奖励：{username} 第 {reward_index} 次{source_label}返利 {source_id}"


def _build_user_label(user: User) -> str:
    return format_wecom_user_label(user)


def _source_type_label(source_type: str) -> str:
    return "在线购买" if source_type == REFERRAL_SOURCE_PAYMENT else "兑换码兑换"


def _send_referral_reward_notification(
    db: Session,
    *,
    referrer: User,
    invitee: User,
    grant: ReferralRewardGrant,
) -> None:
    credit_account = get_user_credit_account(db, referrer.id, create_if_missing=False)
    remain_credit = int(credit_account.remain_credit or 0) if credit_account else 0
    used_credit = int(credit_account.used_credit or 0) if credit_account else 0
    send_wecom_markdown(
        "## 🎉 邀请奖励已发放\n"
        f"> 👤 邀请人: **{_build_user_label(referrer)}**\n"
        f"> 🙋 被邀请用户: **{_build_user_label(invitee)}**\n"
        f"> 🏷️ 奖励来源: **{_source_type_label(grant.source_type)}**\n"
        f"> 🔖 来源编号: `{grant.source_id}`\n"
        f"> ⚡ 对方到账积分: **{int(grant.source_credits or 0)}**\n"
        f"> 🎁 奖励比例: **{int(grant.reward_rate or 0)}%**\n"
        f"> 🎁 发放奖励积分: **{int(grant.reward_credits or 0)}**\n"
        f"> 🔁 第 **{int(grant.reward_index or 0)}** 次奖励\n"
        f"> ⚡ 邀请人已使用积分: **{used_credit}**\n"
        f"> ⚡ 邀请人剩余积分: **{remain_credit}**\n"
        f"> ⏰ 发放时间: {now_local().strftime('%Y-%m-%d %H:%M:%S')}"
    )
