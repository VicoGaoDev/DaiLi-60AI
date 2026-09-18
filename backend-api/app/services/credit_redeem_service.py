import secrets
import string
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.credit_redeem_key import CreditRedeemKey
from app.models.user import User
from app.services.business_id_service import get_user_by_business_id, user_external_id
from app.services.user_credit_service import AGENT_POOL_CREDIT_TYPE, DEFAULT_CREDIT_TYPE, change_user_credit_balance, create_agent_pool_credit_account, get_user_credit_account, get_user_credit_balance
from app.utils.datetime_utils import now_local

REDEEM_KEY_ALPHABET = string.ascii_uppercase + string.digits
REDEEM_KEY_LENGTH = 16
REDEEM_KEY_STATUS_ENABLED = "enabled"
REDEEM_KEY_STATUS_DISABLED = "disabled"
REDEEM_KEY_SOURCE_SYSTEM = "system"
REDEEM_KEY_SOURCE_AGENT = "agent"
REDEEM_LOG_DESCRIPTION_PREFIX = "兑换积分码"
AGENT_POOL_REDEEM_DEDUCT_DESCRIPTION_PREFIX = "用户兑换兑换码"


def _generate_redeem_key() -> str:
    return "".join(secrets.choice(REDEEM_KEY_ALPHABET) for _ in range(REDEEM_KEY_LENGTH))


def _generate_batch_no() -> str:
    return f"RK{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.randbelow(1000):03d}"


def _serialize_redeem_key(row: CreditRedeemKey) -> dict:
    used_by = row.used_by_user
    creator = row.creator
    return {
        "id": row.id,
        "redeem_key": row.redeem_key,
        "credit_amount": int(row.credit_amount or 0),
        "batch_no": row.batch_no,
        "status": row.status,
        "source": row.source or REDEEM_KEY_SOURCE_SYSTEM,
        "is_locked": bool(row.is_locked),
        "is_used": bool(row.used_at or row.used_by_user_id),
        "used_at": row.used_at,
        "used_by_user_id": user_external_id(used_by) if used_by else None,
        "used_by_username": used_by.username if used_by else "",
        "used_by_user_email": used_by.email if used_by and used_by.email else "",
        "created_by_user_id": user_external_id(creator) if creator else None,
        "created_by_username": creator.username if creator else "",
        "created_at": row.created_at,
    }


def get_agent_unused_redeem_credit_sum(db: Session, agent_id: int, *, exclude_key_id: int | None = None) -> int:
    query = db.query(func.coalesce(func.sum(CreditRedeemKey.credit_amount), 0)).filter(
        CreditRedeemKey.created_by == agent_id,
        CreditRedeemKey.source == REDEEM_KEY_SOURCE_AGENT,
        CreditRedeemKey.status == REDEEM_KEY_STATUS_ENABLED,
        CreditRedeemKey.used_at.is_(None),
        CreditRedeemKey.used_by_user_id.is_(None),
    )
    if exclude_key_id is not None:
        query = query.filter(CreditRedeemKey.id != exclude_key_id)
    return int(query.scalar() or 0)


def assert_agent_pool_covers_unused(db: Session, agent: User, *, extra: int = 0, pool_remain_override: int | None = None, exclude_key_id: int | None = None) -> None:
    if agent.role != "agent":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="目标用户不是代理人")
    pool = get_user_credit_account(db, agent.id, credit_type=AGENT_POOL_CREDIT_TYPE, create_if_missing=False)
    pool_remain = int(pool.remain_credit or 0) if pool else 0
    if pool_remain_override is not None:
        pool_remain = int(pool_remain_override)
    unused = get_agent_unused_redeem_credit_sum(db, agent.id, exclude_key_id=exclude_key_id)
    if pool_remain < unused + int(extra or 0):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="代理积分池不足，无法覆盖未兑启用码")


def _validate_batch(count: int, credit_amount: int) -> None:
    if count <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="生成数量必须大于 0")
    if count > 1000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="单次最多生成 1000 个兑换码")
    if credit_amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="积分值必须大于 0")


def _create_redeem_key_rows(db: Session, *, count: int, credit_amount: int, creator_id: int, source: str):
    batch_no = _generate_batch_no()
    rows = []
    existing_keys = set()
    attempts = 0
    while len(rows) < count:
        attempts += 1
        if attempts > count * 20:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="兑换码生成失败，请重试")
        candidate = _generate_redeem_key()
        if candidate in existing_keys or db.query(CreditRedeemKey.id).filter(CreditRedeemKey.redeem_key == candidate).first():
            continue
        existing_keys.add(candidate)
        row = CreditRedeemKey(redeem_key=candidate, credit_amount=credit_amount, batch_no=batch_no, status=REDEEM_KEY_STATUS_ENABLED, source=source, created_by=creator_id)
        db.add(row)
        rows.append(row)
    return batch_no, rows


def create_redeem_key_batch(db: Session, *, count: int, credit_amount: int, admin_user: User, source: str = REDEEM_KEY_SOURCE_SYSTEM) -> dict:
    _validate_batch(count, credit_amount)
    if source != REDEEM_KEY_SOURCE_SYSTEM:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="管理员只能生成系统兑换码")
    batch_no, rows = _create_redeem_key_rows(db, count=count, credit_amount=credit_amount, creator_id=admin_user.id, source=REDEEM_KEY_SOURCE_SYSTEM)
    db.commit()
    for row in rows:
        db.refresh(row)
    return {"batch_no": batch_no, "credit_amount": credit_amount, "count": len(rows), "items": [_serialize_redeem_key(row) for row in rows]}


def create_agent_redeem_key_batch(db: Session, *, count: int, credit_amount: int, agent: User) -> dict:
    _validate_batch(count, credit_amount)
    create_agent_pool_credit_account(db, agent)
    pool = get_user_credit_account(db, agent.id, credit_type=AGENT_POOL_CREDIT_TYPE, for_update=True)
    assert_agent_pool_covers_unused(db, agent, extra=count * credit_amount, pool_remain_override=int(pool.remain_credit or 0) if pool else 0)
    batch_no, rows = _create_redeem_key_rows(db, count=count, credit_amount=credit_amount, creator_id=agent.id, source=REDEEM_KEY_SOURCE_AGENT)
    db.commit()
    for row in rows:
        db.refresh(row)
    return {"batch_no": batch_no, "credit_amount": credit_amount, "count": len(rows), "items": [_serialize_redeem_key(row) for row in rows]}


def list_redeem_keys(db: Session, *, page: int = 1, page_size: int = 20, batch_no: str | None = None, redeem_key: str | None = None, credit_amount: int | None = None, status_filter: str | None = None, is_used: bool | None = None, used_by: str | None = None, created_by: str | None = None, source: str | None = None, start_date: datetime | None = None, end_date: datetime | None = None) -> dict:
    query = db.query(CreditRedeemKey).options(joinedload(CreditRedeemKey.used_by_user), joinedload(CreditRedeemKey.creator))
    if batch_no:
        query = query.filter(CreditRedeemKey.batch_no.ilike(f"%{batch_no.strip()}%"))
    if redeem_key:
        query = query.filter(CreditRedeemKey.redeem_key.ilike(f"%{redeem_key.strip().upper()}%"))
    if credit_amount is not None:
        query = query.filter(CreditRedeemKey.credit_amount == int(credit_amount))
    if status_filter:
        query = query.filter(CreditRedeemKey.status == status_filter)
    if is_used is True:
        query = query.filter(CreditRedeemKey.used_at.is_not(None))
    elif is_used is False:
        query = query.filter(CreditRedeemKey.used_at.is_(None))
    if used_by:
        keyword = f"%{used_by.strip()}%"
        query = query.join(CreditRedeemKey.used_by_user, isouter=True).filter((User.username.ilike(keyword)) | (User.email.ilike(keyword)))
    if created_by:
        creator = get_user_by_business_id(db, created_by.strip())
        if creator:
            query = query.filter(CreditRedeemKey.created_by == creator.id)
        else:
            keyword = f"%{created_by.strip()}%"
            creator_ids = db.query(User.id).filter((User.username.ilike(keyword)) | (User.email.ilike(keyword)))
            query = query.filter(CreditRedeemKey.created_by.in_(creator_ids))
    if source:
        query = query.filter(CreditRedeemKey.source == source)
    if start_date:
        query = query.filter(CreditRedeemKey.used_at >= start_date)
    if end_date:
        query = query.filter(CreditRedeemKey.used_at <= end_date)
    total = query.count()
    rows = query.order_by(CreditRedeemKey.created_at.desc(), CreditRedeemKey.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "items": [_serialize_redeem_key(row) for row in rows]}


def update_redeem_key_status(db: Session, *, key_id: int, new_status: str) -> dict:
    if new_status not in {REDEEM_KEY_STATUS_ENABLED, REDEEM_KEY_STATUS_DISABLED}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="兑换码状态不合法")
    row = db.query(CreditRedeemKey).options(joinedload(CreditRedeemKey.used_by_user), joinedload(CreditRedeemKey.creator)).filter(CreditRedeemKey.id == key_id).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="兑换码不存在")
    if row.used_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已使用兑换码不允许修改状态")
    row.status = new_status
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_redeem_key(row)


def redeem_credit_key(db: Session, *, redeem_key: str, user: User) -> dict:
    normalized_key = (redeem_key or "").strip().upper()
    if not normalized_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入兑换码")
    row = db.query(CreditRedeemKey).options(joinedload(CreditRedeemKey.used_by_user)).filter(CreditRedeemKey.redeem_key == normalized_key).with_for_update().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="兑换码不存在")
    if row.used_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该兑换码已被使用")
    if row.status != REDEEM_KEY_STATUS_ENABLED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该兑换码已被禁用")
    amount = int(row.credit_amount or 0)
    if (row.source or REDEEM_KEY_SOURCE_SYSTEM) == REDEEM_KEY_SOURCE_AGENT:
        if row.created_by == user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="代理人不能兑换自己发出的兑换码")
        if not row.created_by:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="代理兑换码缺少发行人")
        change_user_credit_balance(db, row.created_by, delta=-amount, log_type="agent_pool_deduct", description=f"{AGENT_POOL_REDEEM_DEDUCT_DESCRIPTION_PREFIX} {row.redeem_key}", operator_id=user.id, credit_type=AGENT_POOL_CREDIT_TYPE)
    row.used_by_user_id = user.id
    row.used_at = now_local()
    db.add(row)
    change_user_credit_balance(db, user.id, delta=amount, log_type="allocate", description=f"{REDEEM_LOG_DESCRIPTION_PREFIX} {row.redeem_key}", operator_id=None, credit_type=DEFAULT_CREDIT_TYPE)
    db.commit()
    db.refresh(row)
    return {"message": "兑换成功", "credit_amount": amount, "credits": get_user_credit_balance(db, user.id), "redeem_key": row.redeem_key, "used_at": row.used_at}
