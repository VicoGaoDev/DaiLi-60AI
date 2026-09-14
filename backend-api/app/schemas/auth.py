from datetime import datetime

from pydantic import BaseModel


class LoginRequest(BaseModel):
    account: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: "UserBrief"


class UserBrief(BaseModel):
    id: str
    business_id: str
    username: str
    email: str | None = None
    role: str
    avatar_url: str = ""
    credits: int = 0

    model_config = {"from_attributes": True}


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: str
    verification_code: str
    verification_id: str
    new_password: str


class UpdateProfileRequest(BaseModel):
    username: str


class RedeemCreditKeyRequest(BaseModel):
    key: str


class RedeemCreditKeyResponse(BaseModel):
    message: str
    credit_amount: int
    credits: int
    redeem_key: str
    used_at: datetime | None = None
