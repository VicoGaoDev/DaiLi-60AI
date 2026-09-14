import secrets
import string
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.models.credit_redeem_key import CreditRedeemKey
from app.models.user import User
from app.services.business_id_service import user_external_id
from app.services.user_credit_service import change_user_credit_balance, get_user_credit_balance
from app.utils.datetime_utils import now_local

REDEEM_KEY_ALPHABET = string.ascii_uppercase + string.digits
REDEEM_KEY_LENGTH = 16
REDEEM_KEY_STATUS_ENABLED = "enabled"
REDEEM_KEY_STATUS_DISABLED = "disabled"
REDEEM_LOG_DESCRIPTION_PREFIX = "兑换积分码"


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
        "is_used": bool(row.used_at or row.used_by_user_id),
        "used_at": row.used_at,
        "used_by_user_id": user_external_id(used_by) if used_by else None,
        "used_by_username": used_by.username if used_by else "",
        "used_by_user_email": used_by.email if used_by and used_by.email else "",
        "created_by_user_id": user_external_id(creator) if creator else None,
        "created_by_username": creator.username if creator else "",
        "created_at": row.created_at,
    }


def create_redeem_key_batch(db: Session, *, count: int, credit_amount: int, admin_user: User) -> dict:
    if count <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="生成数量必须大于 0")
    if count > 1000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="单次最多生成 1000 个兑换码")
    if credit_amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="积分值必须大于 0")

    batch_no = _generate_batch_no()
    rows: list[CreditRedeemKey] = []
    existing_keys: set[str] = set()
    attempts = 0
    max_attempts = count * 20

    while len(rows) < count:
        attempts += 1
        if attempts > max_attempts:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="兑换码生成失败，请重试")
        candidate = _generate_redeem_key()
        if candidate in existing_keys:
            continue
        exists = db.query(CreditRedeemKey.id).filter(CreditRedeemKey.redeem_key == candidate).first()
        if exists:
            continue
        existing_keys.add(candidate)
        row = CreditRedeemKey(
            redeem_key=candidate,
            credit_amount=credit_amount,
            batch_no=batch_no,
            status=REDEEM_KEY_STATUS_ENABLED,
            created_by=admin_user.id,
        )
        db.add(row)
        rows.append(row)

    db.commit()

    for row in rows:
        db.refresh(row)

    return {
        "batch_no": batch_no,
        "credit_amount": credit_amount,
        "count": len(rows),
        "items": [_serialize_redeem_key(row) for row in rows],
    }


def list_redeem_keys(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    batch_no: str | None = None,
    redeem_key: str | None = None,
    credit_amount: int | None = None,
    status_filter: str | None = None,
    is_used: bool | None = None,
    used_by: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    query = (
        db.query(CreditRedeemKey)
        .options(
            joinedload(CreditRedeemKey.used_by_user),
            joinedload(CreditRedeemKey.creator),
        )
    )
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
        query = (
            query.join(CreditRedeemKey.used_by_user, isouter=True)
            .filter((User.username.ilike(keyword)) | (User.email.ilike(keyword)))
        )
    if start_date:
        query = query.filter(CreditRedeemKey.used_at >= start_date)
    if end_date:
        query = query.filter(CreditRedeemKey.used_at <= end_date)

    total = query.count()
    rows = (
        query.order_by(CreditRedeemKey.created_at.desc(), CreditRedeemKey.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"total": total, "items": [_serialize_redeem_key(row) for row in rows]}


def update_redeem_key_status(db: Session, *, key_id: int, new_status: str) -> dict:
    if new_status not in {REDEEM_KEY_STATUS_ENABLED, REDEEM_KEY_STATUS_DISABLED}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="兑换码状态不合法")

    row = (
        db.query(CreditRedeemKey)
        .options(
            joinedload(CreditRedeemKey.used_by_user),
            joinedload(CreditRedeemKey.creator),
        )
        .filter(CreditRedeemKey.id == key_id)
        .first()
    )
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

    row = (
        db.query(CreditRedeemKey)
        .options(joinedload(CreditRedeemKey.used_by_user))
        .filter(CreditRedeemKey.redeem_key == normalized_key)
        .with_for_update()
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="兑换码不存在")
    if row.used_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该兑换码已被使用")
    if row.status != REDEEM_KEY_STATUS_ENABLED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该兑换码已被禁用")

    row.used_by_user_id = user.id
    row.used_at = now_local()
    db.add(row)
    change_user_credit_balance(
        db,
        user.id,
        delta=int(row.credit_amount or 0),
        log_type="allocate",
        description=f"{REDEEM_LOG_DESCRIPTION_PREFIX} {row.redeem_key}",
        operator_id=None,
    )
    db.commit()
    db.refresh(row)

    return {
        "message": "兑换成功",
        "credit_amount": int(row.credit_amount or 0),
        "credits": get_user_credit_balance(db, user.id),
        "redeem_key": row.redeem_key,
        "used_at": row.used_at,
    }
