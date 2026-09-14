from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.payment import (
    CreatePaymentOrderRequest,
    CreatePaymentOrderResponse,
    PaymentOrderOut,
    PaymentPlansResponse,
)
from app.services.payment_service import (
    build_auto_submit_form,
    close_expired_unpaid_starter_orders,
    create_payment_order,
    format_payment_order,
    get_payment_order_by_result_token_with_sync,
    get_payment_order_for_user_with_sync,
    list_payment_plans,
    process_alipay_notification,
    record_alipay_return,
)

router = APIRouter(prefix="/api/payment", tags=["支付"])


def sync_expired_unpaid_starter_orders(db: Session, user: User) -> None:
    close_expired_unpaid_starter_orders(
        db,
        user=user,
        timeout_express=settings.ALIPAY_TIMEOUT_EXPRESS,
        alipay_app_id=settings.ALIPAY_APP_ID,
        gateway=settings.ALIPAY_GATEWAY,
        private_key=settings.ALIPAY_PRIVATE_KEY,
        sign_type=settings.ALIPAY_SIGN_TYPE,
        alipay_public_key=settings.ALIPAY_PUBLIC_KEY,
    )


@router.get("/plans", response_model=PaymentPlansResponse)
def get_payment_plans(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sync_expired_unpaid_starter_orders(db, user)
    db.commit()
    return {"items": list_payment_plans(db=db, user=user)}


@router.post("/orders", response_model=CreatePaymentOrderResponse)
def create_order(
    body: CreatePaymentOrderRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sync_expired_unpaid_starter_orders(db, user)
    order = create_payment_order(
        db,
        user=user,
        plan_key=body.plan_key,
        alipay_app_id=settings.ALIPAY_APP_ID,
        notify_url=settings.ALIPAY_NOTIFY_URL,
        return_url=settings.ALIPAY_RETURN_URL,
        gateway=settings.ALIPAY_GATEWAY,
        timeout_express=settings.ALIPAY_TIMEOUT_EXPRESS,
        private_key=settings.ALIPAY_PRIVATE_KEY,
        sign_type=settings.ALIPAY_SIGN_TYPE,
        result_token_secret=settings.SECRET_KEY,
    )
    db.commit()
    return order


@router.get("/orders/{order_no}/result", response_model=PaymentOrderOut)
def get_order_result(
    order_no: str,
    token: str = Query(min_length=1),
    db: Session = Depends(get_db),
):
    order = get_payment_order_by_result_token_with_sync(
        db,
        order_no=order_no,
        result_token=token,
        result_token_secret=settings.SECRET_KEY,
        alipay_app_id=settings.ALIPAY_APP_ID,
        gateway=settings.ALIPAY_GATEWAY,
        private_key=settings.ALIPAY_PRIVATE_KEY,
        sign_type=settings.ALIPAY_SIGN_TYPE,
        alipay_public_key=settings.ALIPAY_PUBLIC_KEY,
    )
    db.commit()
    return format_payment_order(order)


@router.get("/orders/{order_no}", response_model=PaymentOrderOut)
def get_order(
    order_no: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = get_payment_order_for_user_with_sync(
        db,
        order_no=order_no,
        user=user,
        alipay_app_id=settings.ALIPAY_APP_ID,
        gateway=settings.ALIPAY_GATEWAY,
        private_key=settings.ALIPAY_PRIVATE_KEY,
        sign_type=settings.ALIPAY_SIGN_TYPE,
        alipay_public_key=settings.ALIPAY_PUBLIC_KEY,
    )
    db.commit()
    return format_payment_order(order)


@router.get("/return/alipay", response_class=HTMLResponse)
async def alipay_return(request: Request, db: Session = Depends(get_db)):
    order = await record_alipay_return(db, request=request)
    if order:
        db.commit()
        return HTMLResponse(build_auto_submit_form(f"/payment-result?order_no={order.order_no}"))
    return HTMLResponse(build_auto_submit_form("/payment-result"))


@router.post("/webhook/alipay")
async def alipay_webhook(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    payload = {key: str(value) for key, value in form.items()}
    process_alipay_notification(
        db,
        payload=payload,
        alipay_public_key=settings.ALIPAY_PUBLIC_KEY,
        alipay_app_id=settings.ALIPAY_APP_ID,
    )
    db.commit()
    return PlainTextResponse("success")
