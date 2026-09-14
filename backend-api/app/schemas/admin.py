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
    avatar_url: str = ""
    role: str
    status: str
    is_whitelisted: bool = False
    credits: int = 0
    consumed_credits: int = 0
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AllocateCreditsRequest(BaseModel):
    amount: int
    description: str = ""


class ResetCreditsRequest(BaseModel):
    description: str = ""


class CreateRedeemKeysBatchRequest(BaseModel):
    count: int
    credit_amount: int


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
