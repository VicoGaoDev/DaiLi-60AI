import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.auth import (
    BindEmailRequest,
    BindPhoneRequest,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegistrationEmailCheckRequest,
    RegistrationPhoneCheckRequest,
    UserBrief,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    UpdateProfileRequest,
    RedeemCreditKeyRequest,
    RedeemCreditKeyResponse,
    CreatePromoCodeRequest,
    UpdatePromoCodeRequest,
    PromoCodeListResponse,
    PromoReferralListResponse,
    PromoReferralActivityListResponse,
    PromoCodeValidationResponse,
    InviteRewardOverviewResponse,
    InviteRewardReferralListResponse,
    InviteRewardLogListResponse,
)
from app.services.business_id_service import get_user_by_business_id, user_external_id
from app.services.auth_service import (
    authenticate_user,
    bind_email,
    bind_phone,
    change_password,
    ensure_login_email_registered,
    ensure_login_phone_registered,
    ensure_registration_email_available,
    ensure_registration_phone_available,
    register_user,
    reset_password_with_contact_code,
    update_username,
)
from app.services.promo_service import (
    create_promo_code,
    get_my_promo_codes,
    get_my_promo_referrals,
    get_my_promo_referral_activities,
    get_valid_promo_code,
    update_promo_code_platform,
)
from app.services.referral_reward_service import (
    get_invite_reward_overview,
    get_user_by_invite_code,
    is_personal_invite_code,
    list_invite_reward_logs,
    list_invite_reward_referrals,
    normalize_invite_code,
)
from app.services.credit_redeem_service import redeem_credit_key
from app.models.prompt_history import PromptHistory
from app.models.prompt_optimize_task import PromptOptimizeTask
from app.services.admin_service import get_credit_logs
from app.services.prompt_optimize_service import PROMPT_OPTIMIZE_MODE
from app.services.user_credit_service import get_user_credit_balance
from app.services.cos_service import build_object_key, upload_bytes_to_cos
from app.services.image_delivery_service import get_optional_cos_config, resolve_avatar_url

router = APIRouter(prefix="/api/auth", tags=["认证"])
audit_logger = logging.getLogger("app.audit")
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
AVATAR_MAX_SIZE = 1 * 1024 * 1024  # 1 MB


def _user_brief(db: Session, user: User) -> UserBrief:
    return UserBrief(
        id=user_external_id(user),
        business_id=user.business_id,
        username=user.username,
        email=user.email,
        phone=user.phone,
        password_set=bool(user.password_set),
        role=user.role,
        avatar_url=resolve_avatar_url(user.avatar_url, cos_config=get_optional_cos_config(db)),
        credits=get_user_credit_balance(db, user.id),
        is_whitelisted=bool(user.is_whitelisted),
    )


@router.post("/register/email-check")
def check_registration_email(body: RegistrationEmailCheckRequest, db: Session = Depends(get_db)):
    ensure_registration_email_available(db, body.email)
    return {"available": True}


@router.post("/register/phone-check")
def check_registration_phone(body: RegistrationPhoneCheckRequest, db: Session = Depends(get_db)):
    ensure_registration_phone_available(db, body.phone)
    return {"available": True}


@router.post("/login/phone-check")
def check_login_phone(body: RegistrationPhoneCheckRequest, db: Session = Depends(get_db)):
    ensure_login_phone_registered(db, body.phone)
    return {"registered": True}


@router.post("/login/email-check")
def check_login_email(body: RegistrationEmailCheckRequest, db: Session = Depends(get_db)):
    ensure_login_email_registered(db, body.email)
    return {"registered": True}


@router.post("/register", response_model=LoginResponse)
async def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    token, user = await register_user(
        db,
        username=body.username,
        password=body.password,
        promo_code=body.promo_code,
        verification_id=body.verification_id,
        verification_code=body.verification_code,
        email=body.email,
        phone=body.phone,
    )
    request.state.user_id = user_external_id(user)
    account = (body.email or body.phone or "").strip().lower()
    audit_logger.info(
        "user registered",
        extra={
            "event": "auth.register.success",
            "account": account,
            "client_ip": request.client.host if request.client else "",
            "user_agent": request.headers.get("user-agent", ""),
            "user_id": user_external_id(user),
        },
    )
    return LoginResponse(token=token, user=_user_brief(db, user))


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    normalized_account = (body.account or "").strip()
    try:
        token, user = authenticate_user(db, normalized_account, body.password)
    except HTTPException:
        audit_logger.warning(
            "login failed",
            extra={
                "event": "auth.login.failed",
                "account": normalized_account,
                "client_ip": request.client.host if request.client else "",
                "user_agent": request.headers.get("user-agent", ""),
            },
        )
        raise
    request.state.user_id = user_external_id(user)
    audit_logger.info(
        "login succeeded",
        extra={
            "event": "auth.login.success",
            "account": normalized_account,
            "client_ip": request.client.host if request.client else "",
            "user_agent": request.headers.get("user-agent", ""),
            "user_id": user_external_id(user),
        },
    )
    return LoginResponse(token=token, user=_user_brief(db, user))


@router.post("/bind/email", response_model=UserBrief)
async def bind_user_email(
    body: BindEmailRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = await bind_email(
        db,
        user,
        body.email,
        body.verification_id,
        body.verification_code,
    )
    audit_logger.info(
        "email bound",
        extra={
            "event": "auth.bind.email.success",
            "account": (body.email or "").strip().lower(),
            "client_ip": request.client.host if request.client else "",
            "user_agent": request.headers.get("user-agent", ""),
            "user_id": user_external_id(user),
        },
    )
    return _user_brief(db, user)


@router.post("/bind/phone", response_model=UserBrief)
async def bind_user_phone(
    body: BindPhoneRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = await bind_phone(
        db,
        user,
        body.phone,
        body.verification_id,
        body.verification_code,
    )
    audit_logger.info(
        "phone bound",
        extra={
            "event": "auth.bind.phone.success",
            "account": (body.phone or "").strip(),
            "client_ip": request.client.host if request.client else "",
            "user_agent": request.headers.get("user-agent", ""),
            "user_id": user_external_id(user),
        },
    )
    return _user_brief(db, user)


@router.post("/change-password")
def change_pwd(
    body: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    change_password(db, user, body.old_password, body.new_password)
    audit_logger.info(
        "password changed",
        extra={
            "event": "auth.password.changed",
            "client_ip": request.client.host if request.client else "",
            "user_agent": request.headers.get("user-agent", ""),
            "user_id": user_external_id(user),
        },
    )
    return {"message": "密码修改成功"}


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user = await reset_password_with_contact_code(
        db,
        email=body.email,
        phone=body.phone,
        verification_id=body.verification_id,
        verification_code=body.verification_code,
        new_password=body.new_password,
    )
    request.state.user_id = user_external_id(user)
    account = (body.email or body.phone or "").strip().lower()
    audit_logger.info(
        "password reset by contact code",
        extra={
            "event": "auth.password.reset",
            "account": account,
            "client_ip": request.client.host if request.client else "",
            "user_agent": request.headers.get("user-agent", ""),
            "user_id": user_external_id(user),
        },
    )
    return {"message": "密码重置成功"}


@router.get("/me", response_model=UserBrief)
def get_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _user_brief(db, user)


@router.post("/redeem-key", response_model=RedeemCreditKeyResponse)
def redeem_key(
    body: RedeemCreditKeyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return redeem_credit_key(db, redeem_key=body.key, user=user)


@router.put("/profile", response_model=UserBrief)
def update_profile(
    body: UpdateProfileRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = update_username(db, user, body.username)
    audit_logger.info(
        "profile updated",
        extra={
            "event": "auth.profile.updated",
            "client_ip": request.client.host if request.client else "",
            "user_agent": request.headers.get("user-agent", ""),
            "user_id": user_external_id(user),
        },
    )
    return _user_brief(db, user)


def _request_frontend_base_url(request: Request) -> str:
    base_url = (request.headers.get("origin") or "").strip()
    if not base_url:
        base_url = f"{request.url.scheme}://{request.url.netloc}"
    return base_url


@router.get("/promo-codes/me", response_model=PromoCodeListResponse)
def list_my_promo_codes(
    request: Request,
    month: Optional[str] = Query(None, description="返利统计月份，格式 YYYY-MM，默认当前月"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_my_promo_codes(db, user, base_url=_request_frontend_base_url(request), month=month)


@router.post("/promo-codes", response_model=PromoCodeListResponse)
def create_my_promo_code(
    body: CreatePromoCodeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    create_promo_code(db, user, body.platform_name)
    return get_my_promo_codes(db, user, base_url=_request_frontend_base_url(request))


@router.patch("/promo-codes/{promo_code_id}", response_model=PromoCodeListResponse)
def update_my_promo_code(
    promo_code_id: int,
    body: UpdatePromoCodeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    update_promo_code_platform(db, user, promo_code_id, body.platform_name)
    return get_my_promo_codes(db, user, base_url=_request_frontend_base_url(request))


@router.get("/promo-referrals", response_model=PromoReferralListResponse)
def list_my_promo_referrals(
    keyword: Optional[str] = Query(None),
    platform_name: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_my_promo_referrals(
        db,
        user,
        keyword=keyword,
        platform_name=platform_name,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/promo-referral-activities", response_model=PromoReferralActivityListResponse)
def list_my_promo_referral_activities(
    keyword: Optional[str] = Query(None),
    platform_name: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_my_promo_referral_activities(
        db,
        user,
        keyword=keyword,
        platform_name=platform_name,
        start_date=start_date,
        end_date=end_date,
    )


def _validate_registration_invite_code(db: Session, code: str) -> PromoCodeValidationResponse:
    normalized_code = normalize_invite_code(code)
    if is_personal_invite_code(normalized_code):
        invite_owner = get_user_by_invite_code(db, normalized_code)
        if invite_owner:
            return PromoCodeValidationResponse(valid=True, code=normalized_code, platform_name="个人邀请")
    promo = get_valid_promo_code(db, normalized_code)
    return PromoCodeValidationResponse(valid=True, code=promo.code, platform_name=promo.platform_name)


@router.get("/promo-codes/validate", response_model=PromoCodeValidationResponse)
def validate_promo_code(
    code: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    return _validate_registration_invite_code(db, code)


@router.get("/invite-codes/validate", response_model=PromoCodeValidationResponse)
def validate_invite_code(
    code: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    return _validate_registration_invite_code(db, code)


@router.get("/invite-rewards/me", response_model=InviteRewardOverviewResponse)
def get_my_invite_reward_overview(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payload = get_invite_reward_overview(db, user, base_url=_request_frontend_base_url(request))
    db.commit()
    return payload


@router.get("/invite-rewards/referrals", response_model=InviteRewardReferralListResponse)
def get_my_invite_reward_referrals(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_invite_reward_referrals(db, user, page=page, page_size=page_size)


@router.get("/invite-rewards/logs", response_model=InviteRewardLogListResponse)
def get_my_invite_reward_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_invite_reward_logs(db, user, page=page, page_size=page_size)


@router.get("/credit-logs")
def my_credit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    direction: Optional[str] = Query(None, pattern="^(increase|decrease)$"),
    mode: Optional[str] = Query(None, pattern="^(text_generate|image_edit|inpaint|smart_cutout|promptReverse|promptOptimize|manual|redeem|purchase)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    is_admin = user.role in ("admin", "superadmin")
    effective_user_id = user.id
    if is_admin and user_id:
        target_user = get_user_by_business_id(db, user_id)
        if not target_user:
            raise HTTPException(status_code=404, detail="用户不存在")
        effective_user_id = target_user.id
    return get_credit_logs(db, user_id=effective_user_id, page=page, page_size=page_size,
                           start_date=start_date, end_date=end_date, direction=direction, mode=mode)


@router.get("/prompt-history")
def list_prompt_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    prompt_history_rows = (
        db.query(PromptHistory)
        .filter(
            PromptHistory.user_id == user.id,
            PromptHistory.mode != PROMPT_OPTIMIZE_MODE,
        )
        .order_by(PromptHistory.created_at.desc())
        .limit(10)
        .all()
    )
    prompt_optimize_rows = (
        db.query(PromptOptimizeTask)
        .filter(PromptOptimizeTask.user_id == user.id)
        .order_by(PromptOptimizeTask.created_at.desc(), PromptOptimizeTask.id.desc())
        .limit(10)
        .all()
    )
    items = [
        {
            "id": r.id,
            "prompt": r.prompt,
            "mode": r.mode or "generate",
            "source_image": r.source_image or "",
            "created_at": r.created_at,
        }
        for r in prompt_history_rows
    ] + [
        {
            "id": row.id,
            "prompt": (row.optimized_prompt or row.original_prompt or "").strip(),
            "mode": PROMPT_OPTIMIZE_MODE,
            "source_image": row.source_image or "",
            "created_at": row.created_at,
        }
        for row in prompt_optimize_rows
    ]
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items[:10]


@router.delete("/prompt-history/{item_id}")
def delete_prompt_history(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.query(PromptHistory).filter(
        PromptHistory.id == item_id,
        PromptHistory.user_id == user.id,
        PromptHistory.mode != PROMPT_OPTIMIZE_MODE,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(row)
    db.commit()
    return {"message": "已删除"}


@router.delete("/prompt-optimize-tasks/{item_id}")
def delete_prompt_optimize_task(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.query(PromptOptimizeTask).filter(
        PromptOptimizeTask.id == item_id,
        PromptOptimizeTask.user_id == user.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(row)
    db.commit()
    return {"message": "已删除"}


@router.post("/avatar", response_model=UserBrief)
async def upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="仅支持 JPG/PNG/WEBP/GIF 格式")

    data = await file.read()
    if len(data) > AVATAR_MAX_SIZE:
        raise HTTPException(status_code=400, detail="头像图片不能超过 1 MB")

    content_type = file.content_type or "image/jpeg"
    key = build_object_key("avatar", file.filename or "avatar.jpg", content_type)
    user.avatar_url = upload_bytes_to_cos(
        db,
        data=data,
        key=key,
        content_type=content_type,
        cache_control="public, max-age=31536000",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_brief(db, user)
