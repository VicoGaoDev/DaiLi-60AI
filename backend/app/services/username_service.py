import secrets

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.user import User


RESERVED_USERNAMES = frozenset(
    {
        "80ai",
        "admin",
        "administrator",
        "banana",
        "moderator",
        "operator",
        "root",
        "service",
        "support",
        "superadmin",
        "sysadmin",
        "system",
        "webmaster",
    }
)


def normalize_username(username: str) -> str:
    normalized = (username or "").strip()
    if len(normalized) < 2 or len(normalized) > 20:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名需 2-20 个字符")
    if normalized.casefold() in RESERVED_USERNAMES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该用户名为系统保留，不可使用")
    return normalized


def ensure_username_available(
    db: Session,
    username: str,
    *,
    exclude_user_id: int | None = None,
) -> str:
    normalized = normalize_username(username)
    query = db.query(User.id).filter(
        func.lower(func.trim(User.username)) == normalized.lower(),
    )
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)
    if query.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")
    return normalized


def generate_phone_username(db: Session, phone: str) -> str:
    tail = (phone or "")[-4:] or secrets.token_hex(2)
    candidate = tail
    for _ in range(30):
        existing = db.query(User.id).filter(
            func.lower(func.trim(User.username)) == candidate.lower(),
        ).first()
        if not existing and candidate.casefold() not in RESERVED_USERNAMES:
            return candidate
        candidate = f"{tail}{secrets.randbelow(900) + 100}"
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="用户名生成失败，请稍后重试")
