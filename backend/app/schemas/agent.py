from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.admin import RedeemKeyOut


class AgentOverviewOut(BaseModel):
    pool_credits: int = 0
    unused_redeem_credits: int = 0
    issuable_credits: int = 0
    redeemed_credits: int = 0
    username: str = ""
    user_id: str = ""


class AgentCreditLogOut(BaseModel):
    id: int
    amount: int
    type: str
    redeem_key: str = ""
    description: str = ""
    operator_name: str = ""
    created_at: datetime | None = None


class AgentCreditLogListOut(BaseModel):
    total: int = 0
    redeemed_credits: int = 0
    items: list[AgentCreditLogOut] = Field(default_factory=list)


class AgentRedeemKeyListOut(BaseModel):
    total: int = 0
    items: list[RedeemKeyOut] = Field(default_factory=list)


class CreateAgentRedeemKeysBatchRequest(BaseModel):
    count: int
    credit_amount: int


class UpdateAgentRedeemKeyStatusRequest(BaseModel):
    status: str


class UpdateAgentRedeemKeyLockRequest(BaseModel):
    is_locked: bool
