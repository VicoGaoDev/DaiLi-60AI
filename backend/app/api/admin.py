from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.deps import require_admin, require_superadmin
from app.models.user import User
from app.schemas.admin import (
    CreateUserRequest, UserOut, UpdateStatusRequest, UpdateRoleRequest,
    UpdateWhitelistRequest, ResetPasswordRequest, StatsOut, AllocateCreditsRequest, ResetCreditsRequest, CreditLogOut,
    CreateRedeemKeysBatchRequest, RedeemKeyBatchOut, RedeemKeyOut, UpdateRedeemKeyStatusRequest, PaymentOrderAdminOut,
    CreateOfflineOrderRequest, OfflineOrderOut,
    AnalyticsSummaryOut, AnalyticsTimeseriesOut, AnalyticsBreakdownOut, AnalyticsRedeemRevenueOut, AnalyticsRevenueTimeseriesOut, ErrorAnalyticsOut, ErrorCategoryTimeseriesOut, ErrorTaskListOut, DailyReportTestOut, DailyReportRangeRequest, ApiAlertTestOut,
    AdminLedgerCreateRequest, AdminLedgerUpdateRequest, AdminLedgerOut,
    AdminUserListOut, AdminUserPromoDashboardOut,
    VideoStatsOut,
)
from app.schemas.canvas import CanvasListResponse
from app.schemas.chat import ChatMessageListOut, ChatSessionAdminListOut, ChatSessionAdminOut
from app.schemas.task import TaskOut
from app.schemas.feedback import (
    FeedbackDetail,
    FeedbackListResponse,
    FeedbackMessageCreateRequest,
    FeedbackMessageListResponse,
    FeedbackMessageOut,
    FeedbackReadCountResponse,
    FeedbackUnresolvedCountResponse,
    FeedbackUpdateRequest,
)
from app.schemas.history import HistoryResponse, UserHistoryCardItem, UserHistoryResponse
from app.schemas.video_task import AdminVideoTaskListOut, VideoTaskOut
from app.services.business_id_service import get_user_by_business_id
from app.services.admin_service import (
    create_user, list_users, list_user_options, get_user_detail, update_user_status, update_user_role,
    update_user_whitelist, reset_user_password, get_stats, allocate_credits, reset_user_credits, get_credit_logs,
    list_payment_orders, create_offline_order, list_offline_orders,
    list_admin_ledgers, get_admin_ledger, create_admin_ledger, update_admin_ledger, refresh_admin_ledger_income,
    get_admin_invite_reward_dashboard,
    get_admin_invite_reward_user_detail,
    get_admin_promo_stats_dashboard,
    get_admin_promo_stats_user_detail,
    get_analytics_summary, get_analytics_timeseries, get_analytics_breakdown, get_analytics_redeem_revenue,
    get_analytics_payment_revenue, get_analytics_offline_order_revenue, get_analytics_revenue_timeseries, get_error_analytics, get_error_category_timeseries, get_error_tasks,
    get_video_stats, get_video_analytics_summary, get_video_analytics_timeseries, get_video_analytics_breakdown,
)
from app.services.credit_redeem_service import create_redeem_key_batch, list_redeem_keys, update_redeem_key_status
from app.services.promo_service import get_user_promo_dashboard_for_admin
from app.services.feedback_service import (
    close_feedback,
    count_admin_unread_feedbacks,
    count_unresolved_feedbacks,
    create_feedback_message,
    get_feedback_detail,
    list_feedback_messages,
    list_feedbacks,
    mark_feedback_as_admin_read,
    update_feedback,
)
from app.services.history_service import get_admin_history_cards, get_admin_history_detail, get_all_history
from app.services.canvas_service import list_all_canvases
from app.services.chat_service import get_admin_session, list_admin_messages, list_admin_sessions
from app.services.image_delivery_service import get_optional_cos_config, serialize_task
from app.services.task_service import get_task_details
from app.services.daily_report_service import DailyReportSendResult, send_previous_day_report, send_range_report
from app.services.api_alert_service import ApiAlertRunResult, execute_api_alerts
from app.services.video_task_service import (
    expire_stale_video_tasks,
    get_video_task_detail,
    list_admin_video_tasks,
    serialize_video_task,
)

router = APIRouter(prefix="/api/admin", tags=["管理员"])


def _resolve_optional_user_id(db: Session, user_id: str | None) -> int | None:
    if not user_id:
        return None
    user = get_user_by_business_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user.id


def _format_daily_report_result(result: DailyReportSendResult) -> dict:
    stats = result.stats
    return {
        "sent": result.sent,
        "report_date": stats.start_at.strftime("%Y-%m-%d"),
        "range_start": stats.start_at,
        "range_end": stats.end_at,
        "revenue_fen": stats.revenue_fen,
        "revenue_yuan": stats.revenue_fen / 100,
        "total_revenue_yuan": stats.total_revenue_yuan,
        "paid_order_count": stats.paid_order_count,
        "offline_order_revenue_fen": stats.offline_order_revenue_fen,
        "offline_order_revenue_yuan": stats.offline_order_revenue_fen / 100,
        "offline_order_count": stats.offline_order_count,
        "redeem_revenue_yuan": stats.redeem_revenue_yuan,
        "redeem_used_count": stats.redeem_used_count,
        "task_total_count": stats.task_total_count,
        "task_success_count": stats.task_success_count,
        "task_failed_count": stats.task_failed_count,
        "credit_consumed": stats.credit_consumed,
    }


@router.post("/users", response_model=UserOut)
def admin_create_user(
    body: CreateUserRequest,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return create_user(db, body.username, body.password, body.role, operator=_user)


@router.get("/users", response_model=AdminUserListOut)
def admin_list_users(
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(30, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    whitelist: Optional[bool] = Query(None),
    sort: str = Query("created_at_desc"),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_users(
        db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        status_filter=status,
        whitelist=whitelist,
        sort=sort,
    )


@router.get("/user-options", response_model=list[UserOut])
def admin_list_user_options(
    keyword: Optional[str] = Query(None),
    limit: int = Query(2000, ge=1, le=5000),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_user_options(db, keyword=keyword, limit=limit)


@router.get("/users/{user_id}", response_model=UserOut)
def admin_get_user_detail(
    user_id: str,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_user_detail(db, user_id)


@router.get("/canvases", response_model=CanvasListResponse)
def admin_list_canvases(
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None),
    user_id: str | None = Query(None),
):
    return list_all_canvases(
        db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        owner_user_id=_resolve_optional_user_id(db, user_id),
    )


@router.get("/chat/sessions", response_model=ChatSessionAdminListOut)
def admin_list_chat_sessions(
    page_size: int = Query(50, ge=1, le=100),
    keyword: str | None = Query(None),
    user_id: str | None = Query(None),
    before_session_id: str | None = Query(None),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_admin_sessions(
        db,
        page_size=page_size,
        keyword=keyword,
        user_id=_resolve_optional_user_id(db, user_id),
        before_session_id=before_session_id,
    )


@router.get("/chat/sessions/{session_id}", response_model=ChatSessionAdminOut)
def admin_get_chat_session(
    session_id: str,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_admin_session(db, session_id)


@router.get("/chat/sessions/{session_id}/messages", response_model=ChatMessageListOut)
def admin_list_chat_messages(
    session_id: str,
    before_id: int | None = Query(None, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_admin_messages(
        db,
        session_id,
        before_id=before_id,
        page_size=page_size,
    )


@router.get("/tasks", response_model=list[TaskOut])
def admin_get_tasks(
    task_ids: list[str] = Query(default=[]),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tasks = [task for task in get_task_details(db, task_ids) if not task.is_deleted]
    cos_config = get_optional_cos_config(db)
    return [serialize_task(task, cos_config=cos_config) for task in tasks]


@router.put("/users/{user_id}/status", response_model=UserOut)
def admin_update_status(
    user_id: str,
    body: UpdateStatusRequest,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return update_user_status(db, user_id, body.status, user)


@router.put("/users/{user_id}/role", response_model=UserOut)
def admin_update_role(
    user_id: str,
    body: UpdateRoleRequest,
    user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return update_user_role(db, user_id, body.role, user)


@router.put("/users/{user_id}/whitelist", response_model=UserOut)
def admin_update_whitelist(
    user_id: str,
    body: UpdateWhitelistRequest,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return update_user_whitelist(db, user_id, body.is_whitelisted)


@router.put("/users/{user_id}/reset-password", response_model=UserOut)
def admin_reset_password(
    user_id: str,
    body: ResetPasswordRequest,
    user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return reset_user_password(db, user_id, body.new_password, user)


@router.post("/users/{user_id}/credits", response_model=UserOut)
def admin_allocate_credits(
    user_id: str,
    body: AllocateCreditsRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return allocate_credits(db, user_id, body.amount, body.description, admin)


@router.post("/users/{user_id}/credits/reset", response_model=UserOut)
def admin_reset_credits(
    user_id: str,
    body: ResetCreditsRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return reset_user_credits(db, user_id, body.description, admin)


@router.get("/users/{user_id}/promo-dashboard", response_model=AdminUserPromoDashboardOut)
def admin_user_promo_dashboard(
    user_id: str,
    month: Optional[str] = Query(None, description="返利统计月份，格式 YYYY-MM"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target_user = get_user_by_business_id(db, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return get_user_promo_dashboard_for_admin(
        db,
        target_user,
        month=month,
        start_date=start_date,
        end_date=end_date,
    )


@router.post("/redeem-keys/batch", response_model=RedeemKeyBatchOut)
def admin_create_redeem_keys_batch(
    body: CreateRedeemKeysBatchRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return create_redeem_key_batch(db, count=body.count, credit_amount=body.credit_amount, admin_user=admin)


@router.get("/redeem-keys", response_model=dict)
def admin_list_redeem_keys(
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
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_redeem_keys(
        db,
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


@router.post("/redeem-keys/{key_id}/status", response_model=RedeemKeyOut)
def admin_update_redeem_key_status(
    key_id: int,
    body: UpdateRedeemKeyStatusRequest,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return update_redeem_key_status(db, key_id=key_id, new_status=body.status)


@router.get("/credit-logs", response_model=dict)
def admin_credit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    direction: Optional[str] = Query(None, pattern="^(increase|decrease)$"),
    mode: Optional[str] = Query(None, pattern="^(text_generate|image_edit|inpaint|smart_cutout|promptReverse|promptOptimize|manual|redeem|purchase)$"),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_credit_logs(db, user_id=_resolve_optional_user_id(db, user_id), page=page, page_size=page_size,
                           start_date=start_date, end_date=end_date, direction=direction, mode=mode)


@router.get("/payment-orders", response_model=dict)
def admin_payment_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status", pattern="^(created|pending_pay|paid|credited|closed|failed)$"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_payment_orders(
        db,
        page=page,
        page_size=page_size,
        user_keyword=user,
        status_filter=status_filter,
        start_date=start_date,
        end_date=end_date,
    )


@router.post("/offline-orders", response_model=OfflineOrderOut)
def admin_create_offline_order(
    body: CreateOfflineOrderRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return create_offline_order(
        db,
        user_id=body.user_id,
        order_type=body.order_type,
        credit_amount=body.credit_amount,
        amount_yuan=body.amount_yuan,
        remark=body.remark,
        admin=admin,
    )


@router.get("/offline-orders", response_model=dict)
def admin_offline_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_offline_orders(
        db,
        page=page,
        page_size=page_size,
        user_keyword=user,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/ledgers", response_model=dict)
def admin_list_ledgers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_admin_ledgers(db, page=page, page_size=page_size)


@router.get("/ledgers/{month}", response_model=AdminLedgerOut)
def admin_get_ledger(
    month: str,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_admin_ledger(db, month=month)


@router.post("/ledgers", response_model=AdminLedgerOut)
def admin_create_ledger(
    body: AdminLedgerCreateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return create_admin_ledger(db, payload=body, operator=admin)


@router.put("/ledgers/{month}", response_model=AdminLedgerOut)
def admin_update_ledger(
    month: str,
    body: AdminLedgerUpdateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return update_admin_ledger(db, month=month, payload=body, operator=admin)


@router.post("/ledgers/{month}/refresh-income", response_model=AdminLedgerOut)
def admin_refresh_ledger_income(
    month: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return refresh_admin_ledger_income(db, month=month, operator=admin)


@router.get("/stats", response_model=StatsOut)
def admin_stats(
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_stats(db)


@router.get("/invite-rewards", response_model=dict)
def admin_invite_rewards(
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_admin_invite_reward_dashboard(db)


@router.get("/invite-rewards/users/{user_id}", response_model=dict)
def admin_invite_reward_user_detail(
    user_id: str,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_admin_invite_reward_user_detail(db, user_id)


@router.get("/promo-stats", response_model=dict)
def admin_promo_stats(
    month: Optional[str] = Query(None, description="返利排行月份，格式 YYYY-MM，默认当前月"),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_admin_promo_stats_dashboard(db, month=month)


@router.get("/promo-stats/users/{user_id}", response_model=dict)
def admin_promo_stats_user_detail(
    user_id: str,
    month: Optional[str] = Query(None, description="返利统计月份，格式 YYYY-MM"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_admin_promo_stats_user_detail(
        db,
        user_id,
        month=month,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/video-stats", response_model=VideoStatsOut)
def admin_video_stats(
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_video_stats(db)


@router.get("/analytics/summary", response_model=AnalyticsSummaryOut)
def admin_analytics_summary(
    granularity: str = Query("day", pattern="^(3hour|day|week|month)$"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    user_id: Optional[str] = Query(None),
    source: Optional[str] = Query(None, pattern="^(web|app|api)$"),
    model: Optional[str] = Query(None),
    mode: Optional[str] = Query(None, pattern="^(text_generate|image_edit|inpaint|smart_cutout|promptReverse|promptOptimize)$"),
    status: Optional[str] = Query(None),
    canvas_task_filter: Optional[str] = Query(None, pattern="^(canvas|non_canvas)$"),
    include_unsafe_tasks: bool = Query(True),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    resolved_user_id = _resolve_optional_user_id(db, user_id)
    return get_analytics_summary(
        db,
        granularity=granularity,
        start_date=start_date,
        end_date=end_date,
        user_id=resolved_user_id,
        source=source,
        model=model,
        mode=mode,
        canvas_task_filter=canvas_task_filter,
        status_filter=status,
        include_unsafe_tasks=include_unsafe_tasks,
    )


@router.get("/analytics/timeseries", response_model=AnalyticsTimeseriesOut)
def admin_analytics_timeseries(
    granularity: str = Query("day", pattern="^(3hour|day|week|month)$"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    user_id: Optional[str] = Query(None),
    source: Optional[str] = Query(None, pattern="^(web|app|api)$"),
    model: Optional[str] = Query(None),
    mode: Optional[str] = Query(None, pattern="^(text_generate|image_edit|inpaint|smart_cutout|promptReverse|promptOptimize)$"),
    status: Optional[str] = Query(None),
    canvas_task_filter: Optional[str] = Query(None, pattern="^(canvas|non_canvas)$"),
    include_unsafe_tasks: bool = Query(True),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    resolved_user_id = _resolve_optional_user_id(db, user_id)
    return get_analytics_timeseries(
        db,
        granularity=granularity,
        start_date=start_date,
        end_date=end_date,
        user_id=resolved_user_id,
        source=source,
        model=model,
        mode=mode,
        canvas_task_filter=canvas_task_filter,
        status_filter=status,
        include_unsafe_tasks=include_unsafe_tasks,
    )


@router.get("/analytics/breakdown", response_model=AnalyticsBreakdownOut)
def admin_analytics_breakdown(
    granularity: str = Query("day", pattern="^(3hour|day|week|month)$"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    user_id: Optional[str] = Query(None),
    source: Optional[str] = Query(None, pattern="^(web|app|api)$"),
    model: Optional[str] = Query(None),
    mode: Optional[str] = Query(None, pattern="^(text_generate|image_edit|inpaint|smart_cutout|promptReverse|promptOptimize)$"),
    status: Optional[str] = Query(None),
    canvas_task_filter: Optional[str] = Query(None, pattern="^(canvas|non_canvas)$"),
    include_unsafe_tasks: bool = Query(True),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    resolved_user_id = _resolve_optional_user_id(db, user_id)
    return get_analytics_breakdown(
        db,
        granularity=granularity,
        start_date=start_date,
        end_date=end_date,
        user_id=resolved_user_id,
        source=source,
        model=model,
        mode=mode,
        canvas_task_filter=canvas_task_filter,
        status_filter=status,
        include_unsafe_tasks=include_unsafe_tasks,
    )


@router.get("/video-analytics/summary", response_model=AnalyticsSummaryOut)
def admin_video_analytics_summary(
    granularity: str = Query("day", pattern="^(3hour|day|week|month)$"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    user_id: Optional[str] = Query(None),
    source: Optional[str] = Query(None, pattern="^(web|app|api)$"),
    model: Optional[str] = Query(None),
    mode: Optional[str] = Query(None, pattern="^(text_to_video|image_to_video|first_last_frame)$"),
    status: Optional[str] = Query(None, pattern="^(pending|queued|processing|success|failed)$"),
    include_unsafe_tasks: bool = Query(True),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    resolved_user_id = _resolve_optional_user_id(db, user_id)
    return get_video_analytics_summary(
        db,
        granularity=granularity,
        start_date=start_date,
        end_date=end_date,
        user_id=resolved_user_id,
        source=source,
        model=model,
        mode=mode,
        status_filter=status,
        include_unsafe_tasks=include_unsafe_tasks,
    )


@router.get("/video-analytics/timeseries", response_model=AnalyticsTimeseriesOut)
def admin_video_analytics_timeseries(
    granularity: str = Query("day", pattern="^(3hour|day|week|month)$"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    user_id: Optional[str] = Query(None),
    source: Optional[str] = Query(None, pattern="^(web|app|api)$"),
    model: Optional[str] = Query(None),
    mode: Optional[str] = Query(None, pattern="^(text_to_video|image_to_video|first_last_frame)$"),
    status: Optional[str] = Query(None, pattern="^(pending|queued|processing|success|failed)$"),
    include_unsafe_tasks: bool = Query(True),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    resolved_user_id = _resolve_optional_user_id(db, user_id)
    return get_video_analytics_timeseries(
        db,
        granularity=granularity,
        start_date=start_date,
        end_date=end_date,
        user_id=resolved_user_id,
        source=source,
        model=model,
        mode=mode,
        status_filter=status,
        include_unsafe_tasks=include_unsafe_tasks,
    )


@router.get("/video-analytics/breakdown", response_model=AnalyticsBreakdownOut)
def admin_video_analytics_breakdown(
    granularity: str = Query("day", pattern="^(3hour|day|week|month)$"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    user_id: Optional[str] = Query(None),
    source: Optional[str] = Query(None, pattern="^(web|app|api)$"),
    model: Optional[str] = Query(None),
    mode: Optional[str] = Query(None, pattern="^(text_to_video|image_to_video|first_last_frame)$"),
    status: Optional[str] = Query(None, pattern="^(pending|queued|processing|success|failed)$"),
    include_unsafe_tasks: bool = Query(True),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    resolved_user_id = _resolve_optional_user_id(db, user_id)
    return get_video_analytics_breakdown(
        db,
        granularity=granularity,
        start_date=start_date,
        end_date=end_date,
        user_id=resolved_user_id,
        source=source,
        model=model,
        mode=mode,
        status_filter=status,
        include_unsafe_tasks=include_unsafe_tasks,
    )


@router.get("/analytics/redeem-revenue", response_model=AnalyticsRedeemRevenueOut)
def admin_analytics_redeem_revenue(
    granularity: str = Query("day", pattern="^(3hour|day|week|month)$"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_analytics_redeem_revenue(
        db,
        granularity=granularity,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/analytics/payment-revenue", response_model=AnalyticsRedeemRevenueOut)
def admin_analytics_payment_revenue(
    granularity: str = Query("day", pattern="^(3hour|day|week|month)$"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_analytics_payment_revenue(
        db,
        granularity=granularity,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/analytics/offline-order-revenue", response_model=AnalyticsRedeemRevenueOut)
def admin_analytics_offline_order_revenue(
    granularity: str = Query("day", pattern="^(3hour|day|week|month)$"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_analytics_offline_order_revenue(
        db,
        granularity=granularity,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/analytics/revenue-timeseries", response_model=AnalyticsRevenueTimeseriesOut)
def admin_analytics_revenue_timeseries(
    granularity: str = Query("day", pattern="^(3hour|day|week|month)$"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_analytics_revenue_timeseries(
        db,
        granularity=granularity,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/analytics/errors", response_model=ErrorAnalyticsOut)
def admin_error_analytics(
    task_kind: str = Query("image", pattern="^(image|video)$"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    source: Optional[str] = Query(None, pattern="^(web|app|api)$"),
    model: Optional[str] = Query(None),
    error_category: Optional[str] = Query(None),
    used_fallback_api: Optional[bool] = Query(None),
    include_unsafe_tasks: bool = Query(True),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_error_analytics(
        db,
        task_kind=task_kind,
        start_date=start_date,
        end_date=end_date,
        source=source,
        model=model,
        error_category=error_category,
        used_fallback_api=used_fallback_api,
        include_unsafe_tasks=include_unsafe_tasks,
    )


@router.get("/analytics/errors/timeseries", response_model=ErrorCategoryTimeseriesOut)
def admin_error_category_timeseries(
    task_kind: str = Query("image", pattern="^(image|video)$"),
    granularity: str = Query("3hour", pattern="^(1hour|3hour|6hour)$"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    source: Optional[str] = Query(None, pattern="^(web|app|api)$"),
    model: Optional[str] = Query(None),
    used_fallback_api: Optional[bool] = Query(None),
    include_unsafe_tasks: bool = Query(True),
    limit: int = Query(6, ge=1, le=12),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_error_category_timeseries(
        db,
        task_kind=task_kind,
        granularity=granularity,
        start_date=start_date,
        end_date=end_date,
        source=source,
        model=model,
        used_fallback_api=used_fallback_api,
        include_unsafe_tasks=include_unsafe_tasks,
        limit=limit,
    )


@router.get("/analytics/errors/tasks", response_model=ErrorTaskListOut)
def admin_error_tasks(
    task_kind: str = Query("image", pattern="^(image|video)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    source: Optional[str] = Query(None, pattern="^(web|app|api)$"),
    model: Optional[str] = Query(None),
    error_category: Optional[str] = Query(None),
    used_fallback_api: Optional[bool] = Query(None),
    include_unsafe_tasks: bool = Query(True),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_error_tasks(
        db,
        task_kind=task_kind,
        page=page,
        page_size=page_size,
        start_date=start_date,
        end_date=end_date,
        source=source,
        model=model,
        error_category=error_category,
        used_fallback_api=used_fallback_api,
        include_unsafe_tasks=include_unsafe_tasks,
    )


@router.get("/history", response_model=HistoryResponse)
def admin_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    source: Optional[str] = Query(None, pattern="^(web|app|api)$"),
    model: Optional[str] = Query(None),
    mode: Optional[str] = Query(None, pattern="^(text_generate|image_edit|inpaint|smart_cutout|promptReverse|promptOptimize)$"),
    canvas_task_filter: Optional[str] = Query(None, pattern="^(canvas|non_canvas)$"),
    include_unsafe_tasks: bool = Query(True),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    resolved_user_id = _resolve_optional_user_id(db, user_id)
    return get_all_history(
        db, page, page_size,
        status=status, user_id=resolved_user_id,
        source=source,
        model=model, mode=mode,
        canvas_task_filter=canvas_task_filter,
        include_unsafe_tasks=include_unsafe_tasks,
        start_date=start_date, end_date=end_date,
    )


@router.get("/history/detail", response_model=UserHistoryCardItem)
def admin_history_detail(
    item_type: str = Query(..., pattern="^(task|prompt_history|prompt_optimize_task)$"),
    task_id: Optional[str] = Query(None),
    history_id: Optional[int] = Query(None),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return get_admin_history_detail(
            db,
            item_type=item_type,
            task_id=task_id,
            history_id=history_id,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的历史记录标识")
    except LookupError:
        raise HTTPException(status_code=404, detail="历史记录不存在")


@router.get("/history/cards", response_model=UserHistoryResponse)
def admin_history_cards(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_prompt_reverse: bool = Query(True),
    mode: Optional[str] = Query(None, pattern="^(text_generate|image_edit|inpaint|smart_cutout|promptReverse|promptOptimize)$"),
    source: Optional[str] = Query(None, pattern="^(web|app|api)$"),
    model: Optional[str] = Query(None),
    prompt: Optional[str] = Query(None),
    status: Optional[str] = Query(None, pattern="^(pending|processing|success|failed)$"),
    user_id: Optional[str] = Query(None),
    used_fallback_api: Optional[bool] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_admin_history_cards(
        db,
        page,
        page_size,
        include_prompt_reverse=include_prompt_reverse,
        user_id=_resolve_optional_user_id(db, user_id),
        mode=mode,
        source=source,
        model=model,
        prompt=prompt,
        status=status,
        used_fallback_api=used_fallback_api,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/video-tasks", response_model=AdminVideoTaskListOut)
def admin_video_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source: Optional[str] = Query(None, pattern="^(web|app|api)$"),
    model: Optional[str] = Query(None),
    mode: Optional[str] = Query(None, pattern="^(text_to_video|image_to_video|first_last_frame)$"),
    prompt: Optional[str] = Query(None),
    status: Optional[str] = Query(None, pattern="^(pending|queued|processing|success|failed)$"),
    user_id: Optional[str] = Query(None),
    used_fallback_api: Optional[bool] = Query(None),
    include_unsafe_tasks: bool = Query(True),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    expire_stale_video_tasks(db)
    return list_admin_video_tasks(
        db,
        page=page,
        page_size=page_size,
        user_id=_resolve_optional_user_id(db, user_id),
        source=source,
        model=model,
        mode=mode,
        prompt=prompt,
        status=status,
        used_fallback_api=used_fallback_api,
        include_unsafe_tasks=include_unsafe_tasks,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/video-tasks/{task_id}", response_model=VideoTaskOut)
def admin_video_task_detail(
    task_id: str,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    expire_stale_video_tasks(db)
    task = get_video_task_detail(db, task_id)
    return serialize_video_task(task)


@router.get("/feedback", response_model=FeedbackListResponse)
def admin_feedback_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    feedback_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    task_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, pattern="^(pending|processing|completed)$"),
    feedback_type: Optional[str] = Query(
        None,
        pattern="^(general|image_task|video_task|canvas|purchase|feature_request|bug_report|optimization)$",
    ),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_feedbacks(
        db,
        feedback_id=feedback_id,
        user_id=_resolve_optional_user_id(db, user_id),
        task_id=task_id,
        status_filter=status,
        feedback_type_filter=feedback_type,
        page=page,
        page_size=page_size,
    )


@router.get("/feedback/unresolved-count", response_model=FeedbackUnresolvedCountResponse)
def admin_feedback_unresolved_count(
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return {"count": count_unresolved_feedbacks(db)}


@router.get("/feedback/unread-count", response_model=FeedbackReadCountResponse)
def admin_feedback_unread_count(
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return {"count": count_admin_unread_feedbacks(db)}


@router.get("/feedback/{feedback_id}", response_model=FeedbackDetail)
def admin_feedback_detail(
    feedback_id: str,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_feedback_detail(db, feedback_id)


@router.get("/feedback/{feedback_id}/messages", response_model=FeedbackMessageListResponse)
def admin_feedback_messages(
    feedback_id: str,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_feedback_messages(db, feedback_id)


@router.post("/feedback/{feedback_id}/messages", response_model=FeedbackMessageOut)
def admin_send_feedback_message(
    feedback_id: str,
    body: FeedbackMessageCreateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return create_feedback_message(
        db,
        feedback_id,
        sender=admin,
        sender_role="admin",
        content=body.content,
        attachments=body.attachments,
    )


@router.patch("/feedback/{feedback_id}/read", response_model=FeedbackReadCountResponse)
def admin_mark_feedback_read(
    feedback_id: str,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return mark_feedback_as_admin_read(db, feedback_id)


@router.post("/feedback/{feedback_id}/close", response_model=FeedbackDetail)
def admin_close_feedback(
    feedback_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return close_feedback(db, feedback_id, admin=admin)


@router.patch("/feedback/{feedback_id}", response_model=FeedbackDetail)
def admin_feedback_update(
    feedback_id: str,
    body: FeedbackUpdateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return update_feedback(
        db,
        feedback_id,
        admin=admin,
        status_value=body.status,
        process_note=body.process_note,
        result_note=body.result_note,
    )


@router.post("/notify/daily-report/test", response_model=DailyReportTestOut)
def admin_test_daily_report_notify(
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return _format_daily_report_result(send_previous_day_report(db))


@router.post("/notify/daily-report/range", response_model=DailyReportTestOut)
def admin_send_daily_report_range(
    body: DailyReportRangeRequest,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    if body.end_date <= body.start_date:
        raise HTTPException(status_code=400, detail="结束日期必须晚于开始日期")
    return _format_daily_report_result(
        send_range_report(db, start_at=body.start_date, end_at=body.end_date)
    )


def _format_api_alert_result(result: ApiAlertRunResult) -> dict:
    stats = result.stats
    decision = result.decision
    return {
        "dry_run": result.dry_run,
        "sent_per_api": result.sent_per_api,
        "sent_overall": result.sent_overall,
        "range_start": result.start_at,
        "range_end": result.end_at,
        "slot_start": result.slot_start,
        "overall": {
            "image_count": stats.overall_image_count,
            "success_count": stats.overall_success_count,
            "success_rate": stats.overall_success_rate,
            "api_count": stats.api_count,
            "would_alert": decision.overall_alert,
        },
        "apis": [
            {
                "api_config_id": api.api_config_id,
                "api_config_name": api.api_config_name,
                "image_count": api.image_count,
                "success_count": api.success_count,
                "success_rate": api.success_rate,
                "avg_duration_seconds": api.avg_duration_seconds,
                "would_alert": api.would_alert,
                "alert_reasons": list(api.alert_reasons),
            }
            for api in decision.annotated_apis
        ],
    }


@router.post("/notify/api-alert/test", response_model=ApiAlertTestOut)
def admin_test_api_alert_notify(
    send: bool = Query(False),
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return _format_api_alert_result(
        execute_api_alerts(db, send=send, claim_slot=False)
    )
