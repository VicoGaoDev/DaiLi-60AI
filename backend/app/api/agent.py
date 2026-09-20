from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_agent
from app.database import get_db
from app.models.user import User
from app.schemas.agent import (
    AgentCreditLogListOut,
    AgentOverviewOut,
    AgentRedeemKeyListOut,
    CreateAgentRedeemKeysBatchRequest,
    UpdateAgentRedeemKeyLockRequest,
    UpdateAgentRedeemKeyStatusRequest,
)
from app.schemas.admin import RedeemKeyBatchOut, RedeemKeyOut
from app.services.credit_redeem_service import (
    create_agent_redeem_key_batch,
    delete_agent_redeem_key,
    get_agent_redeem_overview,
    list_agent_credit_logs,
    list_agent_redeem_keys,
    update_agent_redeem_key_lock as update_agent_redeem_key_lock_service,
    update_agent_redeem_key_status as update_agent_redeem_key_status_service,
)

router = APIRouter(prefix="/api/agent", tags=["代理人"])


@router.get("/overview", response_model=AgentOverviewOut)
def agent_overview(
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    return get_agent_redeem_overview(db, agent=agent)


@router.get("/credit-logs", response_model=AgentCreditLogListOut)
def agent_credit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_keyword: Optional[str] = Query(None),
    log_type: Optional[str] = Query(None, alias="type", pattern="^(allocate|agent_pool_deduct)$"),
    redeem_key: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    return list_agent_credit_logs(
        db,
        agent=agent,
        page=page,
        page_size=page_size,
        user_keyword=user_keyword,
        log_type=log_type,
        redeem_key=redeem_key,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/redeem-keys", response_model=AgentRedeemKeyListOut)
def agent_list_redeem_keys(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    batch_no: Optional[str] = Query(None),
    redeem_key: Optional[str] = Query(None),
    credit_amount: Optional[int] = Query(None, ge=1),
    status_filter: Optional[str] = Query(None, alias="status", pattern="^(enabled|disabled)$"),
    is_used: Optional[bool] = Query(None),
    used_by: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    return list_agent_redeem_keys(
        db,
        agent=agent,
        page=page,
        page_size=page_size,
        batch_no=batch_no,
        redeem_key=redeem_key,
        credit_amount=credit_amount,
        status_filter=status_filter,
        is_used=is_used,
        used_by=used_by,
        start_date=start_date,
        end_date=end_date,
    )


@router.post("/redeem-keys/batch", response_model=RedeemKeyBatchOut)
def agent_create_redeem_keys_batch(
    body: CreateAgentRedeemKeysBatchRequest,
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    return create_agent_redeem_key_batch(db, count=body.count, credit_amount=body.credit_amount, agent=agent)


@router.post("/redeem-keys/{key_id}/status", response_model=RedeemKeyOut)
def agent_update_redeem_key_status(
    key_id: int,
    body: UpdateAgentRedeemKeyStatusRequest,
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    return update_agent_redeem_key_status_service(db, agent=agent, key_id=key_id, new_status=body.status)


@router.post("/redeem-keys/{key_id}/lock", response_model=RedeemKeyOut)
def agent_set_redeem_key_lock(
    key_id: int,
    body: UpdateAgentRedeemKeyLockRequest,
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    return update_agent_redeem_key_lock_service(db, agent=agent, key_id=key_id, is_locked=body.is_locked)


@router.delete("/redeem-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def agent_delete_redeem_key(
    key_id: int,
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db),
):
    delete_agent_redeem_key(db, agent=agent, key_id=key_id)
