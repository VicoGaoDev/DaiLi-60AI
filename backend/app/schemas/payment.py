from datetime import datetime

from pydantic import BaseModel, Field


class PaymentPlanOut(BaseModel):
    key: str
    title: str
    amount_fen: int
    display_amount: str
    credits: int
    tag: str = ""
    purchasable: bool = True
    disabled_reason: str = ""


class CreatePaymentOrderRequest(BaseModel):
    plan_key: str = Field(min_length=1, max_length=50)


class CreatePaymentOrderResponse(BaseModel):
    order_no: str
    status: str
    amount_fen: int
    credits: int
    subject: str
    pay_url: str
    result_token: str


class PaymentOrderOut(BaseModel):
    order_no: str
    plan_key: str
    subject: str
    amount_fen: int
    credits: int
    status: str
    paid_at: datetime | None = None
    credited_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PaymentPlansResponse(BaseModel):
    items: list[PaymentPlanOut]
