import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.config import settings
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    UserBrief,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    UpdateProfileRequest,
    RedeemCreditKeyRequest,
    RedeemCreditKeyResponse,
)
from app.services.business_id_service import get_user_by_business_id, user_external_id
from app.services.auth_service import (
    authenticate_user,
    change_password,
    register_user,
    reset_password_with_email_code,
    update_username,
)
from app.services.credit_redeem_service import redeem_credit_key
from app.models.prompt_history import PromptHistory
from app.services.admin_service import get_credit_logs
from app.services.user_credit_service import get_user_credit_balance

router = APIRouter(prefix="/api/auth", tags=["认证"])
audit_logger = logging.getLogger("app.audit")
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
AVATAR_MAX_SIZE = 1 * 1024 * 1024  # 1 MB


def _user_brief(db: Session, user: User) -> UserBrief:
    return UserBrief(
        id=user_external_id(user), business_id=user.business_id, username=user.username, email=user.email, role=user.role,
        avatar_url=user.avatar_url or "", credits=get_user_credit_balance(db, user.id),
    )


@router.post("/register", response_model=LoginResponse)
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    token, user = register_user(db, body.username, body.email, body.password)
    request.state.user_id = user_external_id(user)
    audit_logger.info(
        "user registered",
        extra={
            "event": "auth.register.success",
            "account": body.email.strip().lower(),
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
    user = await reset_password_with_email_code(
        db,
        body.email,
        body.verification_id,
        body.verification_code,
        body.new_password,
    )
    request.state.user_id = user_external_id(user)
    audit_logger.info(
        "password reset by email code",
        extra={
            "event": "auth.password.reset",
            "account": body.email.strip().lower(),
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


@router.get("/credit-logs")
def my_credit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    direction: Optional[str] = Query(None, pattern="^(increase|decrease)$"),
    mode: Optional[str] = Query(None, pattern="^(text_generate|image_edit|inpaint|promptReverse|manual|redeem)$"),
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
    rows = (
        db.query(PromptHistory)
        .filter(PromptHistory.user_id == user.id)
        .order_by(PromptHistory.created_at.desc())
        .limit(10)
        .all()
    )
    return [
        {
            "id": r.id,
            "prompt": r.prompt,
            "mode": r.mode or "generate",
            "source_image": r.source_image or "",
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.delete("/prompt-history/{item_id}")
def delete_prompt_history(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.query(PromptHistory).filter(
        PromptHistory.id == item_id, PromptHistory.user_id == user.id
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

    ext = Path(file.filename or "avatar.jpg").suffix or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = Path(settings.UPLOAD_DIR) / "avatar" / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    user.avatar_url = f"/uploads/avatar/{filename}"
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_brief(db, user)
