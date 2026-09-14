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
    phone: str | None = None
    password_set: bool = True
    role: str
    avatar_url: str = ""
    credits: int = 0
    is_whitelisted: bool = False

    model_config = {"from_attributes": True}


class RegisterRequest(BaseModel):
    verification_code: str
    verification_id: str
    username: str | None = None
    password: str | None = None
    email: str | None = None
    phone: str | None = None
    promo_code: str | None = None


class RegistrationEmailCheckRequest(BaseModel):
    email: str


class RegistrationPhoneCheckRequest(BaseModel):
    phone: str


class BindEmailRequest(BaseModel):
    email: str
    verification_code: str
    verification_id: str


class BindPhoneRequest(BaseModel):
    phone: str
    verification_code: str
    verification_id: str


class ChangePasswordRequest(BaseModel):
    old_password: str | None = None
    new_password: str


class ForgotPasswordRequest(BaseModel):
    verification_code: str
    verification_id: str
    new_password: str
    email: str | None = None
    phone: str | None = None


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


class CreatePromoCodeRequest(BaseModel):
    platform_name: str


class UpdatePromoCodeRequest(BaseModel):
    platform_name: str


class PromoCodeItem(BaseModel):
    id: int
    code: str
    platform_name: str
    status: str
    created_at: datetime | None = None
    referral_count: int = 0
    promo_link: str = ""


class PromoCodeSummary(BaseModel):
    total_referrals: int = 0
    used_code_count: int = 0
    rewarded_registrations: int = 0
    rewarded_invitees: int = 0
    reward_grant_count: int = 0
    total_reward_amount_fen: int = 0
    total_reward_amount_yuan: float = 0
    today_reward_amount_fen: int = 0
    today_reward_amount_yuan: float = 0
    month: str = ""
    month_reward_grant_count: int = 0
    month_reward_amount_fen: int = 0
    month_reward_amount_yuan: float = 0
    period_referrals: int = 0
    period_rewarded_invitees: int = 0
    period_reward_grant_count: int = 0
    period_reward_amount_fen: int = 0
    period_reward_amount_yuan: float = 0
    period_start: datetime | None = None
    period_end: datetime | None = None
    first_rate: int = 40
    second_rate: int = 30
    next_rate: int = 15
    first_count: int = 1
    max_reward_count: int = 5
    start_at: datetime | None = None


class PromoCodeListResponse(BaseModel):
    summary: PromoCodeSummary
    items: list[PromoCodeItem]


class PromoReferralItem(BaseModel):
    user_id: str
    username: str
    email_masked: str = "-"
    email: str | None = None
    promo_code: str = ""
    platform_name: str = ""
    reward_credits: int = 0
    reward_count: int = 0
    total_reward_amount_yuan: float = 0
    last_reward_at: datetime | None = None
    registered_at: datetime | None = None


class PromoReferralListResponse(BaseModel):
    total: int
    items: list[PromoReferralItem]


class PromoReferralActivityItem(BaseModel):
    user_id: str
    username: str
    email_masked: str = "-"
    activity_type: str
    credits: int = 0
    amount_fen: int | None = None
    amount_yuan: float | None = None
    reward_rate: int | None = None
    reward_index: int | None = None
    reward_amount_fen: int | None = None
    reward_amount_yuan: float | None = None
    redeem_key: str = ""
    order_no: str = ""
    occurred_at: datetime | None = None


class PromoReferralActivityListResponse(BaseModel):
    total: int
    items: list[PromoReferralActivityItem]


class PromoCodeValidationResponse(BaseModel):
    valid: bool
    code: str = ""
    platform_name: str = ""


class InviteRewardSummary(BaseModel):
    total_referrals: int = 0
    today_referrals: int = 0
    rewarded_invitees: int = 0
    reward_grant_count: int = 0
    total_reward_credits: int = 0
    today_reward_credits: int = 0


class InviteRewardOverviewResponse(BaseModel):
    invite_code: str
    invite_link: str
    reward_rate: int = 15
    max_reward_count: int = 3
    summary: InviteRewardSummary


class InviteRewardReferralItem(BaseModel):
    user_id: str
    username: str
    email_masked: str = "-"
    reward_count: int = 0
    total_reward_credits: int = 0
    last_reward_at: datetime | None = None
    registered_at: datetime | None = None


class InviteRewardReferralListResponse(BaseModel):
    total: int
    items: list[InviteRewardReferralItem]
    page: int = 1
    page_size: int = 20


class InviteRewardLogItem(BaseModel):
    id: int
    invitee_user_id: str
    invitee_username: str
    invitee_email_masked: str = "-"
    source_type: str
    source_id: str
    source_credits: int = 0
    reward_rate: int = 15
    reward_credits: int = 0
    reward_index: int = 0
    created_at: datetime | None = None


class InviteRewardLogListResponse(BaseModel):
    total: int
    items: list[InviteRewardLogItem]
    page: int = 1
    page_size: int = 20
