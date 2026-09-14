import secrets
import string

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_api_key import UserApiKey
from app.utils.datetime_utils import now_local

API_KEY_PREFIX = "sk-"
API_KEY_RANDOM_LENGTH = 32
API_KEY_ALPHABET = string.ascii_letters + string.digits


def generate_user_api_key(db: Session) -> str:
    for _ in range(10):
        random_part = "".join(secrets.choice(API_KEY_ALPHABET) for _ in range(API_KEY_RANDOM_LENGTH))
        api_key = f"{API_KEY_PREFIX}{random_part}"
        exists = db.query(UserApiKey.id).filter(UserApiKey.api_key == api_key).first()
        if not exists:
            return api_key
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="API Key 生成失败")


def _normalize_key_name(value: str | None) -> str:
    return (value or "").strip()[:100]


def _fill_key_display_fields(row: UserApiKey) -> None:
    row.key_prefix = row.api_key[:6]
    row.key_last4 = row.api_key[-4:]


def list_user_api_keys(db: Session, user: User) -> list[UserApiKey]:
    return (
        db.query(UserApiKey)
        .filter(UserApiKey.user_id == user.id, UserApiKey.is_delete.is_(False))
        .order_by(UserApiKey.created_at.desc(), UserApiKey.id.desc())
        .all()
    )


def create_user_api_key(
    db: Session,
    user: User,
    *,
    key_name: str = "",
    expire_time=None,
) -> UserApiKey:
    api_key = generate_user_api_key(db)
    row = UserApiKey(
        user_id=user.id,
        subs_type="",
        expire_time=expire_time,
        api_key=api_key,
        key_name=_normalize_key_name(key_name) or "默认 API Key",
        status="enabled",
        is_delete=False,
    )
    _fill_key_display_fields(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_user_api_key_or_404(db: Session, user: User, key_id: int) -> UserApiKey:
    row = (
        db.query(UserApiKey)
        .filter(UserApiKey.id == key_id, UserApiKey.user_id == user.id, UserApiKey.is_delete.is_(False))
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API Key 不存在")
    return row


def update_user_api_key(
    db: Session,
    user: User,
    key_id: int,
    *,
    key_name: str | None = None,
    status_value: str | None = None,
    expire_time=None,
    expire_time_provided: bool = False,
) -> UserApiKey:
    row = get_user_api_key_or_404(db, user, key_id)
    if key_name is not None:
        row.key_name = _normalize_key_name(key_name)
    if status_value is not None:
        row.status = status_value
    if expire_time_provided:
        row.expire_time = expire_time
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def soft_delete_user_api_key(db: Session, user: User, key_id: int) -> None:
    row = get_user_api_key_or_404(db, user, key_id)
    row.is_delete = True
    db.add(row)
    db.commit()


def reset_user_api_key(db: Session, user: User, key_id: int) -> UserApiKey:
    row = get_user_api_key_or_404(db, user, key_id)
    row.api_key = generate_user_api_key(db)
    _fill_key_display_fields(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def authenticate_user_api_key(db: Session, api_key: str) -> User:
    normalized_api_key = (api_key or "").strip()
    if not normalized_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key 不能为空")
    row = (
        db.query(UserApiKey)
        .filter(UserApiKey.api_key == normalized_api_key, UserApiKey.is_delete.is_(False))
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key 无效")
    if row.status != "enabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API Key 已禁用")
    if row.expire_time is not None and row.expire_time <= now_local():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API Key 已过期")
    user = row.user
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    if user.status == "disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")
    return user
