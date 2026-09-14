from decimal import Decimal

from pydantic import BaseModel, Field
from datetime import datetime


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "user"


class UserOut(BaseModel):
    id: str
    username: str
    email: str | None = None
    phone: str | None = None
    avatar_url: str = ""
    role: str
    status: str
    is_whitelisted: bool = False
    credits: int = 0
    consumed_credits: int = 0
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AdminUserListOut(BaseModel):
    items: list[UserOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    has_more: bool = False
    first_admin_id: str | None = None
    whitelisted_total: int = 0


class AllocateCreditsRequest(BaseModel):
    amount: int
    description: str = ""


class ResetCreditsRequest(BaseModel):
    description: str = ""


class CreateRedeemKeysBatchRequest(BaseModel):
    count: int
    credit_amount: int


class CreateOfflineOrderRequest(BaseModel):
    user_id: str
    order_type: str = "purchase"
    credit_amount: int = Field(ge=1)
    amount_yuan: Decimal = Field(gt=0)
    remark: str = ""


class UpdateRedeemKeyStatusRequest(BaseModel):
    status: str


class RedeemKeyOut(BaseModel):
    id: int
    redeem_key: str
    credit_amount: int
    batch_no: str
    status: str
    is_used: bool
    used_at: datetime | None = None
    used_by_user_id: str | None = None
    used_by_username: str = ""
    used_by_user_email: str = ""
    created_by_user_id: str | None = None
    created_by_username: str = ""
    created_at: datetime | None = None


class RedeemKeyBatchOut(BaseModel):
    batch_no: str
    credit_amount: int
    count: int
    items: list[RedeemKeyOut]


class CreditLogOut(BaseModel):
    id: int
    user_id: str
    username: str = ""
    amount: int
    type: str
    mode: str = ""
    description: str = ""
    operator_name: str = ""
    task_id: str | None = None
    created_at: datetime | None = None


class PaymentOrderAdminOut(BaseModel):
    id: int
    order_no: str
    out_trade_no: str
    alipay_trade_no: str = ""
    user_id: str
    username: str = ""
    user_email: str = ""
    plan_key: str = ""
    subject: str = ""
    amount_fen: int
    amount_yuan: float
    credits: int
    status: str
    trade_status: str = ""
    buyer_id: str = ""
    paid_at: datetime | None = None
    credited_at: datetime | None = None
    closed_at: datetime | None = None
    failed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OfflineOrderOut(BaseModel):
    id: int
    business_id: str
    user_id: str
    username: str = ""
    user_email: str = ""
    order_type: str
    credit_amount: int
    amount_fen: int
    amount_yuan: float
    remark: str = ""
    created_by: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UpdateStatusRequest(BaseModel):
    status: str  # "active" | "disabled"


class UpdateRoleRequest(BaseModel):
    role: str  # "user" | "admin"


class UpdateWhitelistRequest(BaseModel):
    is_whitelisted: bool


class ResetPasswordRequest(BaseModel):
    new_password: str


class StatsOut(BaseModel):
    total_users: int
    total_tasks: int
    total_credit_cost: int
    total_remain_credits: int
    active_users: int


class VideoStatsOut(BaseModel):
    total_users: int
    total_tasks: int
    total_credit_cost: int
    active_users: int
    success_tasks: int
    failed_tasks: int


class AnalyticsMetricOut(BaseModel):
    current: int
    previous: int
    delta: int
    delta_pct: float | None = None


class AnalyticsSummaryOut(BaseModel):
    granularity: str
    current_range_label: str
    previous_range_label: str
    total_users: int
    tasks_created: AnalyticsMetricOut
    success_tasks: AnalyticsMetricOut
    failed_tasks: AnalyticsMetricOut
    credits_consumed: AnalyticsMetricOut
    new_users: AnalyticsMetricOut
    active_users: AnalyticsMetricOut
    fallback_task_total: int = 0
    fallback_success_tasks: int = 0
    fallback_failed_tasks: int = 0


class AnalyticsTimeseriesPointOut(BaseModel):
    label: str
    bucket_start: datetime | None = None
    bucket_end: datetime | None = None
    tasks_created: int = 0
    success_tasks: int = 0
    failed_tasks: int = 0
    credits_consumed: int = 0
    new_users: int = 0
    active_users: int = 0


class AnalyticsTimeseriesOut(BaseModel):
    granularity: str
    current_range_label: str
    previous_range_label: str
    current: list[AnalyticsTimeseriesPointOut]
    previous: list[AnalyticsTimeseriesPointOut]


class AnalyticsBreakdownItemOut(BaseModel):
    name: str
    count: int = 0
    credit_cost: int = 0


class AnalyticsModelCompareItemOut(BaseModel):
    name: str
    count: int = 0
    success_count: int = 0
    failed_count: int = 0
    success_rate: float = 0
    credit_cost: int = 0
    avg_credit_cost: float = 0
    duration_count: int = 0
    avg_duration_seconds: float = 0


class AnalyticsApiAttemptPerformanceItemOut(BaseModel):
    api_config_id: int | None = None
    name: str
    call_count: int = 0
    task_duration_count: int = 0
    avg_task_duration_seconds: float = 0
    download_count: int = 0
    avg_result_download_ms: float = 0


class AnalyticsBreakdownOut(BaseModel):
    range_label: str
    status_breakdown: list[AnalyticsBreakdownItemOut]
    source_breakdown: list[AnalyticsBreakdownItemOut]
    mode_breakdown: list[AnalyticsBreakdownItemOut]
    canvas_breakdown: list[AnalyticsBreakdownItemOut] = Field(default_factory=list)
    model_breakdown: list[AnalyticsBreakdownItemOut]
    model_compare: list[AnalyticsModelCompareItemOut] = Field(default_factory=list)
    api_attempt_performance: list[AnalyticsApiAttemptPerformanceItemOut] = Field(default_factory=list)
    top_users_by_tasks: list[AnalyticsBreakdownItemOut]
    top_users_by_credit: list[AnalyticsBreakdownItemOut]


class AnalyticsRedeemRevenueItemOut(BaseModel):
    credit_amount: int
    unit_price: float
    used_count: int
    total_amount: float


class AnalyticsRedeemRevenueOut(BaseModel):
    range_label: str
    items: list[AnalyticsRedeemRevenueItemOut]
    total_used_count: int
    total_amount: float


class AnalyticsRevenueTimeseriesPointOut(BaseModel):
    label: str
    bucket_start: datetime | None = None
    bucket_end: datetime | None = None
    online_amount: float = 0
    redeem_amount: float = 0
    offline_amount: float = 0
    total_amount: float = 0


class AnalyticsRevenueTimeseriesOut(BaseModel):
    granularity: str
    range_label: str
    points: list[AnalyticsRevenueTimeseriesPointOut]
    total_online_amount: float = 0
    total_redeem_amount: float = 0
    total_offline_amount: float = 0
    total_amount: float = 0


class ErrorAnalyticsItemOut(BaseModel):
    error_category: str
    error_message: str
    count: int = 0


class ErrorAnalyticsOut(BaseModel):
    range_label: str
    total_failed_tasks: int
    fallback_task_total: int = 0
    fallback_success_tasks: int = 0
    fallback_failed_tasks: int = 0
    distinct_error_categories: int
    distinct_error_messages: int
    items: list[ErrorAnalyticsItemOut]


class ErrorCategoryTimeseriesPointOut(BaseModel):
    label: str
    bucket_start: datetime | None = None
    bucket_end: datetime | None = None
    total_failed_tasks: int = 0
    categories: dict[str, int]


class ErrorCategoryTimeseriesSeriesOut(BaseModel):
    error_category: str
    total_count: int = 0


class ErrorCategoryTimeseriesOut(BaseModel):
    granularity: str
    range_label: str
    series: list[ErrorCategoryTimeseriesSeriesOut]
    points: list[ErrorCategoryTimeseriesPointOut]


class ErrorTaskItemOut(BaseModel):
    task_id: str
    user_id: str = ""
    username: str = ""
    avatar_url: str = ""
    task_type: str = "text_generate"
    model: str = ""
    source: str = "web"
    mode: str = "generate"
    prompt: str = ""
    status: str = "failed"
    error_message: str = ""
    credit_cost: int = 0
    credit_refunded: bool = False
    used_fallback_api: bool = False
    primary_api_config_name: str = ""
    primary_http_status: int | None = None
    fallback_api_config_name: str = ""
    fallback_status: str = "unused"
    fallback_error_message: str = ""
    created_at: datetime | None = None


class ErrorTaskListOut(BaseModel):
    total: int
    items: list[ErrorTaskItemOut]


class DailyReportTestOut(BaseModel):
    sent: bool
    report_date: str
    range_start: datetime
    range_end: datetime
    revenue_fen: int
    revenue_yuan: float
    total_revenue_yuan: float
    paid_order_count: int
    offline_order_revenue_fen: int
    offline_order_revenue_yuan: float
    offline_order_count: int
    redeem_revenue_yuan: float
    redeem_used_count: int
    task_total_count: int
    task_success_count: int
    task_failed_count: int
    credit_consumed: int


class DailyReportRangeRequest(BaseModel):
    start_date: datetime
    end_date: datetime


class ApiAlertApiStatOut(BaseModel):
    api_config_id: int | None = None
    api_config_name: str
    image_count: int
    success_count: int
    success_rate: float
    avg_duration_seconds: float | None = None
    would_alert: bool
    alert_reasons: list[str] = Field(default_factory=list)


class ApiAlertOverallOut(BaseModel):
    image_count: int
    success_count: int
    success_rate: float
    api_count: int
    would_alert: bool


class ApiAlertTestOut(BaseModel):
    dry_run: bool
    sent_per_api: bool
    sent_overall: bool
    range_start: datetime
    range_end: datetime
    slot_start: datetime
    overall: ApiAlertOverallOut
    apis: list[ApiAlertApiStatOut]


class AdminLedgerExpenseIn(BaseModel):
    id: int | None = None
    expense_type: str = "other"
    title: str = ""
    amount_yuan: Decimal = Field(ge=0)
    content: str = ""
    description: str = ""
    screenshot_urls: list[str] = Field(default_factory=list)


class AdminLedgerCreateRequest(BaseModel):
    month: str
    title: str = ""
    content: str = ""
    description: str = ""
    screenshot_urls: list[str] = Field(default_factory=list)
    expenses: list[AdminLedgerExpenseIn] = Field(default_factory=list)


class AdminLedgerUpdateRequest(BaseModel):
    title: str = ""
    content: str = ""
    description: str = ""
    screenshot_urls: list[str] = Field(default_factory=list)
    expenses: list[AdminLedgerExpenseIn] = Field(default_factory=list)


class AdminLedgerIncomeOut(BaseModel):
    online_revenue_yuan: float = 0
    redeem_revenue_yuan: float = 0
    offline_revenue_yuan: float = 0
    total_income_yuan: float = 0


class AdminLedgerExpenseOut(BaseModel):
    id: int
    business_id: str
    expense_type: str
    title: str
    amount_fen: int
    amount_yuan: float
    content: str = ""
    description: str = ""
    screenshot_urls: list[str] = Field(default_factory=list)
    sort_order: int = 0
    created_by_username: str = ""
    updated_by_username: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AdminLedgerLogOut(BaseModel):
    id: int
    operator_id: str
    operator_username: str = ""
    action: str
    summary: str
    before: dict = Field(default_factory=dict)
    after: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class AdminLedgerOut(BaseModel):
    id: int | None = None
    business_id: str = ""
    month: str
    title: str = ""
    content: str = ""
    description: str = ""
    screenshot_urls: list[str] = Field(default_factory=list)
    income: AdminLedgerIncomeOut
    income_snapshot: dict = Field(default_factory=dict)
    total_expense_fen: int = 0
    total_expense_yuan: float = 0
    net_income_fen: int = 0
    net_income_yuan: float = 0
    expenses: list[AdminLedgerExpenseOut] = Field(default_factory=list)
    logs: list[AdminLedgerLogOut] = Field(default_factory=list)
    exists: bool = True
    created_by_username: str = ""
    updated_by_username: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AdminLedgerListItemOut(BaseModel):
    id: int
    business_id: str
    month: str
    title: str
    total_income_yuan: float
    total_expense_yuan: float
    net_income_yuan: float
    updated_by_username: str = ""
    updated_at: datetime | None = None


class AdminPromoCodeItemOut(BaseModel):
    id: int
    code: str
    platform_name: str
    status: str
    created_at: datetime | None = None
    referral_count: int = 0
    promo_link: str = ""


class AdminPromoReferralItemOut(BaseModel):
    user_id: str
    username: str
    email_masked: str = "-"
    promo_code: str = ""
    platform_name: str = ""
    reward_credits: int = 0
    reward_count: int = 0
    total_reward_amount_yuan: float = 0
    last_reward_at: datetime | None = None
    registered_at: datetime | None = None


class AdminPromoReferralActivityItemOut(BaseModel):
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


class AdminPromoSummaryOut(BaseModel):
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


class AdminUserPromoDashboardOut(BaseModel):
    user_id: str
    username: str
    summary: AdminPromoSummaryOut
    promo_codes: list[AdminPromoCodeItemOut]
    referrals: list[AdminPromoReferralItemOut]
    activities: list[AdminPromoReferralActivityItemOut] = []
