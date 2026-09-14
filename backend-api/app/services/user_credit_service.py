from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.credit_log import CreditLog
from app.models.user import User
from app.models.user_credit import (
    DEFAULT_CREDIT_EXPIRE_AT,
    DEFAULT_USER_CREDIT_STATUS,
    UserCredit,
)

DEFAULT_CREDIT_TYPE = 0


def ensure_user_credit_account(
    db: Session,
    user_id: int,
    *,
    credit_type: int = DEFAULT_CREDIT_TYPE,
    remain_credit: int = 0,
) -> UserCredit:
    account = (
        db.query(UserCredit)
        .filter(UserCredit.user_id == user_id, UserCredit.type == credit_type)
        .first()
    )
    if account:
        return account
    account = UserCredit(
        user_id=user_id,
        type=credit_type,
        remain_credit=remain_credit,
        used_credit=0,
        status=DEFAULT_USER_CREDIT_STATUS,
        expire_time=DEFAULT_CREDIT_EXPIRE_AT,
    )
    db.add(account)
    db.flush()
    return account


def get_user_credit_account(
    db: Session,
    user_id: int,
    *,
    credit_type: int = DEFAULT_CREDIT_TYPE,
    for_update: bool = False,
    create_if_missing: bool = True,
) -> UserCredit | None:
    query = db.query(UserCredit).filter(
        UserCredit.user_id == user_id,
        UserCredit.type == credit_type,
    )
    if for_update:
        query = query.with_for_update()
    account = query.first()
    if account or not create_if_missing:
        return account
    if for_update:
        # Avoid duplicate rows under contention by retrying after flush.
        account = ensure_user_credit_account(db, user_id, credit_type=credit_type)
        return (
            db.query(UserCredit)
            .filter(UserCredit.user_id == user_id, UserCredit.type == credit_type)
            .with_for_update()
            .first()
        )
    return ensure_user_credit_account(db, user_id, credit_type=credit_type)


def get_user_credit_balance(
    db: Session,
    user_id: int,
    *,
    credit_type: int = DEFAULT_CREDIT_TYPE,
) -> int:
    account = get_user_credit_account(
        db,
        user_id,
        credit_type=credit_type,
        create_if_missing=False,
    )
    if not account or account.status != DEFAULT_USER_CREDIT_STATUS:
        return 0
    return int(account.remain_credit or 0)


def get_user_credits_map(
    db: Session,
    user_ids: list[int],
    *,
    credit_type: int = DEFAULT_CREDIT_TYPE,
) -> dict[int, int]:
    normalized_ids = [int(user_id) for user_id in user_ids if user_id]
    if not normalized_ids:
        return {}
    rows = (
        db.query(UserCredit)
        .filter(UserCredit.user_id.in_(normalized_ids), UserCredit.type == credit_type)
        .all()
    )
    balance_map = {
        row.user_id: int(row.remain_credit or 0)
        if row.status == DEFAULT_USER_CREDIT_STATUS
        else 0
        for row in rows
    }
    for user_id in normalized_ids:
        balance_map.setdefault(user_id, 0)
    return balance_map


def apply_user_credit_delta(
    db: Session,
    user_id: int,
    *,
    delta: int,
    credit_type: int = DEFAULT_CREDIT_TYPE,
    allow_negative: bool = False,
    restore_used_credit: bool = False,
) -> UserCredit:
    account = get_user_credit_account(
        db,
        user_id,
        credit_type=credit_type,
        for_update=True,
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="积分账户不存在")
    if account.status != DEFAULT_USER_CREDIT_STATUS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前积分账户不可用")

    next_remain_credit = int(account.remain_credit or 0) + int(delta)
    next_used_credit = int(account.used_credit or 0)
    if int(delta) < 0:
        next_used_credit += abs(int(delta))
    elif restore_used_credit:
        next_used_credit = max(next_used_credit - int(delta), 0)

    if not allow_negative and next_remain_credit < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="扣减后积分不能为负数")

    account.remain_credit = next_remain_credit
    account.used_credit = next_used_credit
    db.add(account)
    db.flush()
    return account


def change_user_credit_balance(
    db: Session,
    user_id: int,
    *,
    delta: int,
    log_type: str,
    description: str = "",
    operator_id: int | None = None,
    task_id: int | None = None,
    credit_type: int = DEFAULT_CREDIT_TYPE,
    allow_negative: bool = False,
    restore_used_credit: bool = False,
) -> UserCredit:
    account = apply_user_credit_delta(
        db,
        user_id,
        delta=delta,
        credit_type=credit_type,
        allow_negative=allow_negative,
        restore_used_credit=restore_used_credit,
    )
    db.add(
        CreditLog(
            user_id=user_id,
            amount=int(delta),
            type=log_type,
            description=description,
            operator_id=operator_id,
            task_id=task_id,
        )
    )
    db.flush()
    return account


def create_default_credit_account(db: Session, user: User, *, remain_credit: int = 0) -> UserCredit:
    return ensure_user_credit_account(
        db,
        user.id,
        credit_type=DEFAULT_CREDIT_TYPE,
        remain_credit=remain_credit,
    )
