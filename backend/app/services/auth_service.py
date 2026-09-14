import logging
import re
import secrets

from fastapi import HTTPException, status
import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.services.promo_service import PROMO_CODE_REWARD_CREDITS, get_valid_promo_code
from app.services.referral_reward_service import (
    generate_unique_invite_code,
    get_user_by_invite_code,
    is_personal_invite_code,
    normalize_invite_code,
)
from app.services.business_id_service import user_external_id
from app.services.user_credit_service import change_user_credit_balance
from app.services.username_service import ensure_username_available, generate_phone_username, normalize_username
from app.utils.security import create_access_token, hash_password, verify_password

EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_REGEX = re.compile(r"^1\d{10}$")
CLOUDBASE_AUTH_PATH = "/auth"
NEW_USER_TRIAL_CREDITS = 6
PHONE_USER_TRIAL_CREDITS = 20
BANNED_EMAIL_DOMAIN_SUFFIXES = {
    "minafter.com",
    "mediaholy.com",
    "mailto.plus",
    "yopmail.com",
    "yopmail.net",
    "yopmail.fr",
    "yopmail.org",
    "cool.fr.nf",
    "jetable.org",
    "tempmail.com",
    "tempmail.org",
    "tempmail.cn",
    "temp-mail.org",
    "temp-mail.io",
    "10minutemail.com",
    "10minutemail.net",
    "10minemail.com",
    "eopyy.com",
    "mailinator.com",
    "mailinator.net",
    "mailinator.org",
    "mailin8r.com",
    "mailinator.us",
    "outlook.com",
    "guerrillamail.com",
    "guerrillamail.info",
    "guerrillamail.biz",
    "guerrillamail.de",
    "guerrillamail.net",
    "sharklasers.com",
    "grr.la",
    "spam4.me",
    "guerrillamailblock.com",
    "dispostable.com",
    "mail.tm",
    "mailsac.com",
    "mailnesia.com",
    "throwawaymail.com",
    "fakeinbox.com",
    "emailondeck.com",
    "maildrop.cc",
    "trashmail.com",
    "getnada.com",
    "spamgourmet.com",
    "zoemail.org",
    "besttempmail.com",
    "mailsbay.com",
    "justdefinition.com",
    "mowan666.com",
    "swagpapa.com",
    "pdf-cutter.com",
    "pdfmerge.xyz",
    "rulersonline.com",
    "ziptools.site",
    "imagecompressor.io",
    "tempmailbox.top",
    "linshiyouxiang.net",
    "randmail.dzz10.cn",
    "aoksend.com",
    "linshi-email.com",
    "moakt.com",
    "zzzmail.top",
    "linsmail.com",
    "suijimail.cn",
    "duanxinmail.com",
    "simplelogin.io",
    "addy.io",
    "anonaddy.com",
    "forwardemail.net",
    "test.com",
    "probe.com",
}

logger = logging.getLogger(__name__)

RESERVED_EMAIL_DOMAIN_SUFFIXES = {
    "80ai.net",
    "80ai.cn",
    "80ai.com",
    "80ai.org",
    "80ai.top",
}


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    return digits


def _to_cloudbase_phone(phone: str) -> str:
    return f"+86 {phone}"


def _is_phone_account(account: str) -> bool:
    normalized = (account or "").strip()
    if "@" in normalized:
        return False
    return bool(PHONE_REGEX.fullmatch(_normalize_phone(normalized)))


def _user_has_email(user: User) -> bool:
    return bool((user.email or "").strip())


def _user_has_phone(user: User) -> bool:
    return bool((user.phone or "").strip())


def _random_password() -> str:
    return f"Aa1!{secrets.token_hex(8)}"


def _is_banned_email_domain(domain: str) -> bool:
    return any(
        domain == blocked_suffix or domain.endswith(f".{blocked_suffix}")
        for blocked_suffix in BANNED_EMAIL_DOMAIN_SUFFIXES
    )


def _is_reserved_email_domain(domain: str) -> bool:
    return any(
        domain == reserved_suffix or domain.endswith(f".{reserved_suffix}")
        for reserved_suffix in RESERVED_EMAIL_DOMAIN_SUFFIXES
    )


def _validate_email(email: str) -> str:
    normalized = _normalize_email(email)
    if not normalized or not EMAIL_REGEX.match(normalized):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱格式不正确")
    if len(normalized) > 255:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱长度不能超过255个字符")
    return normalized


def _validate_registration_email(email: str) -> str:
    normalized = _validate_email(email)
    domain = normalized.rsplit("@", 1)[-1]
    if _is_reserved_email_domain(domain):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱域名为官方保留域名，暂不支持注册",
        )
    if _is_banned_email_domain(domain):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱域名暂不支持注册，请使用常用邮箱地址",
        )
    return normalized


def _validate_phone(phone: str) -> str:
    normalized = _normalize_phone(phone)
    if not PHONE_REGEX.fullmatch(normalized):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="手机号格式不正确")
    return normalized


def ensure_registration_email_available(
    db: Session,
    email: str,
    *,
    exclude_user_id: int | None = None,
    occupied_detail: str = "该邮箱已注册或已被其他账号绑定",
) -> str:
    normalized = _validate_registration_email(email)
    query = db.query(User.id).filter(func.lower(func.trim(User.email)) == normalized)
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)
    if query.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=occupied_detail)
    return normalized


def ensure_registration_phone_available(
    db: Session,
    phone: str,
    *,
    exclude_user_id: int | None = None,
    occupied_detail: str = "该手机号已注册，请直接登录",
) -> str:
    normalized = _validate_phone(phone)
    query = db.query(User.id).filter(User.phone == normalized)
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)
    if query.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=occupied_detail)
    return normalized


def ensure_login_phone_registered(db: Session, phone: str) -> str:
    normalized = _validate_phone(phone)
    user = db.query(User).filter(User.phone == normalized).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该手机号未注册")
    if user.status == "disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")
    return normalized


def ensure_login_email_registered(db: Session, email: str) -> str:
    normalized = _validate_email(email)
    user = db.query(User).filter(func.lower(func.trim(User.email)) == normalized).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该邮箱未注册")
    if user.status == "disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")
    return normalized


def _resolve_registration_invite(db: Session, promo_code: str | None, *, email: str | None, phone: str | None):
    normalized_invite_code = normalize_invite_code(promo_code)
    promo = None
    personal_referrer = None
    if normalized_invite_code:
        if is_personal_invite_code(normalized_invite_code):
            personal_referrer = get_user_by_invite_code(db, normalized_invite_code)
            if not personal_referrer:
                promo = get_valid_promo_code(db, normalized_invite_code)
        else:
            promo = get_valid_promo_code(db, normalized_invite_code)
    referrer_id = personal_referrer.id if personal_referrer else (promo.user_id if promo else None)
    if personal_referrer:
        same_email = bool(email) and (personal_referrer.email or "").strip().lower() == email
        same_phone = bool(phone) and (personal_referrer.phone or "").strip() == phone
        if same_email or same_phone:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能使用自己的邀请码注册")
    return promo, referrer_id


def _grant_registration_credits(db: Session, user: User, promo, trial_credits: int) -> None:
    change_user_credit_balance(
        db,
        user.id,
        delta=trial_credits,
        log_type="allocate",
        description="手机号注册试用积分" if trial_credits == PHONE_USER_TRIAL_CREDITS else "新用户注册试用积分",
    )
    if promo:
        change_user_credit_balance(
            db,
            user.id,
            delta=PROMO_CODE_REWARD_CREDITS,
            log_type="allocate",
            description=f"使用推广码 {promo.code} 注册奖励积分",
        )


async def register_user(
    db: Session,
    username: str | None = None,
    password: str | None = None,
    promo_code: str | None = None,
    verification_id: str = "",
    verification_code: str = "",
    email: str | None = None,
    phone: str | None = None,
) -> tuple[str, User]:
    has_email = bool((email or "").strip())
    has_phone = bool((phone or "").strip())
    if has_email == has_phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请使用邮箱或手机号注册")

    normalized_email = ensure_registration_email_available(db, email) if has_email else None
    normalized_phone = ensure_registration_phone_available(db, phone) if has_phone else None
    if not password or len(password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码至少6位")
    if normalized_email:
        if not (username or "").strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入用户名")
        normalized_username = ensure_username_available(db, username or "")
    else:
        normalized_username = generate_phone_username(db, normalized_phone or "")
    account_password = password
    password_set = True

    verification_token = await _verify_cloudbase_code(
        verification_id,
        verification_code,
        contact="邮箱" if normalized_email else "手机号",
    )
    await _signup_cloudbase_account(
        password=account_password,
        verification_token=verification_token,
        email=normalized_email,
        phone=normalized_phone,
    )

    promo, referrer_id = _resolve_registration_invite(
        db,
        promo_code,
        email=normalized_email,
        phone=normalized_phone,
    )
    user = User(
        username=normalized_username,
        email=normalized_email,
        email_verified=bool(normalized_email),
        phone=normalized_phone,
        phone_verified=bool(normalized_phone),
        password_hash=hash_password(account_password),
        password_set=password_set,
        role="user",
        status="active",
        invite_code=generate_unique_invite_code(db),
        referrer_id=referrer_id,
        used_promo_code_id=promo.id if promo else None,
    )
    db.add(user)
    db.flush()
    _grant_registration_credits(
        db,
        user,
        promo,
        PHONE_USER_TRIAL_CREDITS if normalized_phone else NEW_USER_TRIAL_CREDITS,
    )
    db.commit()
    db.refresh(user)
    token = create_access_token(user_external_id(user), user.role)
    return token, user


def authenticate_user(db: Session, account: str, password: str) -> tuple[str, User]:
    normalized_account = (account or "").strip()
    if not normalized_account:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入邮箱、用户名或手机号")

    if _is_phone_account(normalized_account):
        user = db.query(User).filter(User.phone == _normalize_phone(normalized_account)).first()
    elif "@" in normalized_account:
        user = db.query(User).filter(User.email == _normalize_email(normalized_account)).first()
    else:
        matched_users = db.query(User).filter(User.username == normalized_account).all()
        if len(matched_users) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该用户名对应多个账号，请使用邮箱或手机号登录",
            )
        user = matched_users[0] if matched_users else None

    if not user or not user.password_set or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误")
    if user.status == "disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    token = create_access_token(user_external_id(user), user.role)
    return token, user


def change_password(db: Session, user: User, old_password: str | None, new_password: str):
    if len(new_password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码至少6位")
    if user.password_set:
        if not old_password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入原密码")
        if not verify_password(old_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码错误")
    user.password_hash = hash_password(new_password)
    user.password_set = True
    db.commit()


def _cloudbase_error_text(data: dict) -> str:
    parts: list[str] = []
    for key in ("error", "error_code", "error_description", "message", "details", "code"):
        value = data.get(key)
        if value:
            parts.append(str(value))
    return " ".join(parts)


def _is_cloudbase_already_registered(error_text: str) -> bool:
    text = (error_text or "").lower()
    return any(
        needle in text
        for needle in (
            "already exists",
            "already exist",
            "already registered",
            "already used",
            "duplicate",
            "is_user",
            "email_exists",
            "phone_exists",
            "user_exists",
            "已存在",
            "已注册",
            "被占用",
            "已被注册",
        )
    )


def _map_cloudbase_error(error_text: str, action: str = "reset", contact: str = "邮箱") -> str:
    text = (error_text or "").lower()
    if "invalid_verification_code" in text or ("verification" in text and "invalid" in text):
        return "验证码错误或已过期，请重新获取"
    if "invalid_phone" in text or "incorrect phone" in text or "incorrect number" in text:
        return "手机号格式不正确"
    if _is_cloudbase_already_registered(error_text):
        return f"该{contact}已注册"
    if "user_not_found" in text or "not_found" in text:
        return f"该{contact}未注册"
    if "weak password" in text or "password" in text:
        return "新密码不符合要求，请使用至少 6 位密码"
    if "resource_exhausted" in text or "rate" in text or "too many" in text:
        return "操作过于频繁，请稍后再试"
    if action == "verify":
        return "验证码错误或已过期，请重新获取"
    if action == "signup":
        return "注册验证失败，请稍后重试"
    return "密码重置验证失败，请稍后重试"


async def _cloudbase_request(path: str, payload: dict, action: str = "reset", contact: str = "邮箱") -> dict:
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
        error_text = _cloudbase_error_text(data)
        logger.warning(
            "cloudbase %s failed: status=%s path=%s error=%s",
            action,
            response.status_code,
            path,
            error_text or data,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_map_cloudbase_error(error_text, action, contact),
        )
    return data


async def _verify_cloudbase_code(
    verification_id: str,
    verification_code: str,
    *,
    contact: str = "邮箱",
) -> str:
    code = (verification_code or "").strip()
    verify_id = (verification_id or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入正确的 6 位验证码")
    if not verify_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"请先获取{contact}验证码")

    verify_res = await _cloudbase_request(
        "/v1/verification/verify",
        {"verification_id": verify_id, "verification_code": code},
        action="verify",
        contact=contact,
    )
    verification_token = verify_res.get("verification_token")
    if not verification_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误或已过期，请重新获取")
    return str(verification_token)


async def _signup_cloudbase_account(
    *,
    verification_token: str,
    password: str | None = None,
    email: str | None = None,
    phone: str | None = None,
) -> None:
    payload: dict[str, str] = {
        "verification_token": verification_token,
    }
    if password:
        payload["password"] = password
    contact = "邮箱"
    if email:
        payload["email"] = email
    if phone:
        payload["phone_number"] = _to_cloudbase_phone(phone)
        contact = "手机号"
    try:
        await _cloudbase_request("/v1/signup", payload, action="signup", contact=contact)
    except HTTPException as exc:
        if exc.status_code == 400 and (
            exc.detail in {f"该{contact}已注册", "该邮箱已注册", "该手机号已注册"}
            or _is_cloudbase_already_registered(str(exc.detail))
        ):
            return
        raise


async def reset_password_with_contact_code(
    db: Session,
    *,
    email: str | None = None,
    phone: str | None = None,
    verification_id: str,
    verification_code: str,
    new_password: str,
) -> User:
    has_email = bool((email or "").strip())
    has_phone = bool((phone or "").strip())
    if has_email == has_phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请使用邮箱或手机号找回密码")
    if len(new_password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码至少6位")

    if has_email:
        normalized_email = _validate_email(email or "")
        normalized_phone = None
        contact = "邮箱"
        user = db.query(User).filter(User.email == normalized_email).first()
        missing_detail = "该邮箱未注册"
    else:
        normalized_email = None
        normalized_phone = _validate_phone(phone or "")
        contact = "手机号"
        user = db.query(User).filter(User.phone == normalized_phone).first()
        missing_detail = "该手机号未注册"

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=missing_detail)
    if user.status == "disabled":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    verification_token = await _verify_cloudbase_code(verification_id, verification_code, contact=contact)
    reset_payload: dict[str, str] = {
        "new_password": new_password,
        "verification_token": verification_token,
    }
    if normalized_email:
        reset_payload["email"] = normalized_email
    else:
        reset_payload["phone_number"] = _to_cloudbase_phone(normalized_phone or "")

    try:
        await _cloudbase_request("/v1/reset", reset_payload, contact=contact)
    except HTTPException as exc:
        if exc.detail != f"该{contact}未注册":
            raise

    user.password_hash = hash_password(new_password)
    if normalized_email:
        user.email_verified = True
    if normalized_phone:
        user.phone_verified = True
    user.password_set = True
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


async def bind_email(
    db: Session,
    user: User,
    email: str,
    verification_id: str,
    verification_code: str,
) -> User:
    if _user_has_email(user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已绑定邮箱")
    normalized_email = ensure_registration_email_available(
        db,
        email,
        exclude_user_id=user.id,
        occupied_detail="该邮箱已注册或已被其他账号绑定",
    )
    verification_token = await _verify_cloudbase_code(verification_id, verification_code, contact="邮箱")
    await _signup_cloudbase_account(
        email=normalized_email,
        verification_token=verification_token,
    )
    user.email = normalized_email
    user.email_verified = True
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


async def bind_phone(
    db: Session,
    user: User,
    phone: str,
    verification_id: str,
    verification_code: str,
) -> User:
    if _user_has_phone(user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已绑定手机号")
    normalized_phone = ensure_registration_phone_available(
        db,
        phone,
        exclude_user_id=user.id,
        occupied_detail="该手机号已被其他账号使用",
    )
    verification_token = await _verify_cloudbase_code(verification_id, verification_code, contact="手机号")
    await _signup_cloudbase_account(
        phone=normalized_phone,
        verification_token=verification_token,
    )
    user.phone = normalized_phone
    user.phone_verified = True
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_username(db: Session, user: User, username: str) -> User:
    normalized_username = normalize_username(username)
    if user.username == normalized_username:
        return user
    normalized_username = ensure_username_available(db, normalized_username, exclude_user_id=user.id)
    user.username = normalized_username
    db.commit()
    db.refresh(user)
    return user
