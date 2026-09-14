import re

from fastapi import HTTPException, status
import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.services.business_id_service import user_external_id
from app.services.user_credit_service import change_user_credit_balance
from app.utils.security import create_access_token, hash_password, verify_password

EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
CLOUDBASE_AUTH_PATH = "/auth"
NEW_USER_TRIAL_CREDITS = 6


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _validate_email(email: str) -> str:
    normalized = _normalize_email(email)
    if not normalized or not EMAIL_REGEX.match(normalized):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱格式不正确")
    if len(normalized) > 255:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱长度不能超过255个字符")
    return normalized


def _validate_username(username: str) -> str:
    normalized = (username or "").strip()
    if len(normalized) < 2 or len(normalized) > 20:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名需 2-20 个字符")
    return normalized


def register_user(db: Session, username: str, email: str, password: str) -> tuple[str, User]:
    normalized_username = _validate_username(username)
    normalized_email = _validate_email(email)
    if len(password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码至少6位")

    existing = db.query(User).filter(User.email == normalized_email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已注册")

    user = User(
        username=normalized_username,
        email=normalized_email,
        email_verified=True,
        password_hash=hash_password(password),
        role="user",
        status="active",
    )
    db.add(user)
    db.flush()
    change_user_credit_balance(
        db,
        user.id,
        delta=NEW_USER_TRIAL_CREDITS,
        log_type="allocate",
        description="新用户注册试用积分",
    )
    db.commit()
    db.refresh(user)
    token = create_access_token(user_external_id(user), user.role)
    return token, user


def authenticate_user(db: Session, account: str, password: str) -> tuple[str, User]:
    normalized_account = (account or "").strip()
    if not normalized_account:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入邮箱或用户名")

    if "@" in normalized_account:
        user = db.query(User).filter(User.email == _normalize_email(normalized_account)).first()
    else:
        matched_users = db.query(User).filter(User.username == normalized_account).all()
        if len(matched_users) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该用户名对应多个账号，请使用邮箱登录",
            )
        user = matched_users[0] if matched_users else None

    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱/用户名或密码错误")
    if user.status == "disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    token = create_access_token(user_external_id(user), user.role)
    return token, user


def change_password(db: Session, user: User, old_password: str, new_password: str):
    if not verify_password(old_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码错误")
    if len(new_password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码至少6位")

    user.password_hash = hash_password(new_password)
    db.commit()


def _map_cloudbase_error(error_text: str) -> str:
    text = (error_text or "").lower()
    if "invalid_verification_code" in text or "verification" in text and "invalid" in text:
        return "验证码错误或已过期，请重新获取"
    if "user_not_found" in text or "not_found" in text:
        return "该邮箱未注册"
    if "weak password" in text or "password" in text:
        return "新密码不符合要求，请使用至少 6 位密码"
    if "resource_exhausted" in text or "rate" in text or "too many" in text:
        return "操作过于频繁，请稍后再试"
    return "密码重置验证失败，请稍后重试"


async def _cloudbase_request(path: str, payload: dict) -> dict:
    env_id = settings.CLOUDBASE_ENV_ID.strip()
    if not env_id:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="CloudBase 环境 ID 未配置")

    region = (settings.CLOUDBASE_REGION or "ap-shanghai").strip()
    origin = f"https://{env_id}.{region}.tcb-api.tencentcloudapi.com"
    url = f"{origin}{CLOUDBASE_AUTH_PATH}{path}?client_id={env_id}"
    try:
        async with httpx.AsyncClient(timeout=settings.CLOUDBASE_AUTH_TIMEOUT) as client:
            response = await client.post(url, json=payload)
            data = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="CloudBase 验证服务暂时不可用") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="CloudBase 验证服务响应异常") from exc

    if response.status_code >= 400 or data.get("error"):
        error_text = " ".join(
            str(data.get(key) or "")
            for key in ("error", "error_description", "message", "details")
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_map_cloudbase_error(error_text))
    return data


async def reset_password_with_email_code(
    db: Session,
    email: str,
    verification_id: str,
    verification_code: str,
    new_password: str,
) -> User:
    normalized_email = _validate_email(email)
    code = (verification_code or "").strip()
    verify_id = (verification_id or "").strip()
    if len(new_password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码至少6位")
    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入正确的 6 位验证码")
    if not verify_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先获取邮箱验证码")

    user = db.query(User).filter(User.email == normalized_email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该邮箱未注册")
    if user.status == "disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    verify_res = await _cloudbase_request(
        "/v1/verification/verify",
        {"verification_id": verify_id, "verification_code": code},
    )
    verification_token = verify_res.get("verification_token")
    if not verification_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误或已过期，请重新获取")

    await _cloudbase_request(
        "/v1/reset",
        {
            "email": normalized_email,
            "new_password": new_password,
            "verification_token": verification_token,
        },
    )

    user.password_hash = hash_password(new_password)
    user.email_verified = True
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_username(db: Session, user: User, username: str) -> User:
    normalized_username = _validate_username(username)
    if user.username == normalized_username:
        return user
    user.username = normalized_username
    db.commit()
    db.refresh(user)
    return user
