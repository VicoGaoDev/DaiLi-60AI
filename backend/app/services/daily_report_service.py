from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.models.credit_redeem_key import CreditRedeemKey
from app.models.credit_log import CreditLog
from app.models.offline_order import OfflineOrder
from app.models.payment_order import PaymentOrder
from app.models.task import Task
from app.services.payment_service import parse_alipay_payment_time
from app.services.admin_service import REDEEM_UNIT_PRICES
from app.utils.datetime_utils import now_local, to_local_naive
from app.services.wecom_notify_service import is_wecom_notify_enabled, send_wecom_markdown

PAYMENT_SUCCESS_STATUSES = ("paid", "credited")


def _exclude_example_template_seed_task_clause():
    return or_(Task.is_example_template_seed.is_(False), Task.is_example_template_seed.is_(None))


@dataclass(frozen=True)
class DailyReportStats:
    start_at: datetime
    end_at: datetime
    revenue_fen: int
    paid_order_count: int
    offline_order_revenue_fen: int
    offline_order_count: int
    redeem_revenue_yuan: float
    redeem_used_count: int
    task_total_count: int
    task_success_count: int
    task_failed_count: int
    credit_consumed: int

    @property
    def total_revenue_yuan(self) -> float:
        return round(
            (self.revenue_fen + self.offline_order_revenue_fen) / 100
            + self.redeem_revenue_yuan,
            2,
        )


@dataclass(frozen=True)
class DailyReportSendResult:
    sent: bool
    stats: DailyReportStats


def get_previous_day_window(reference_time: datetime | None = None) -> tuple[datetime, datetime]:
    current = to_local_naive(reference_time) if reference_time is not None else now_local()
    today_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    start_at = today_start - timedelta(days=1)
    return start_at, today_start


def collect_online_payment_stats(
    db: Session,
    *,
    start_at: datetime,
    end_at: datetime,
) -> tuple[int, int]:
    rows = (
        db.query(
            PaymentOrder.amount_fen,
            PaymentOrder.paid_at,
            PaymentOrder.credited_at,
            PaymentOrder.notify_payload,
        )
        .filter(
            PaymentOrder.status.in_(PAYMENT_SUCCESS_STATUSES),
        )
        .all()
    )
    revenue_fen = 0
    paid_order_count = 0
    for row in rows:
        payment_time = None
        try:
            payload = json.loads(row.notify_payload or "{}")
            if isinstance(payload, dict):
                payment_time = parse_alipay_payment_time(payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            payment_time = None
        effective_paid_at = payment_time or row.paid_at or row.credited_at
        if effective_paid_at is None or not (start_at <= effective_paid_at < end_at):
            continue
        revenue_fen += int(row.amount_fen or 0)
        paid_order_count += 1
    return revenue_fen, paid_order_count


def collect_daily_report_stats(
    db: Session,
    *,
    start_at: datetime,
    end_at: datetime,
) -> DailyReportStats:
    revenue_fen, paid_order_count = collect_online_payment_stats(
        db,
        start_at=start_at,
        end_at=end_at,
    )

    offline_order_revenue_fen, offline_order_count = (
        db.query(
            func.coalesce(
                func.sum(
                    case(
                        (OfflineOrder.order_type == "refund", -OfflineOrder.amount_fen),
                        else_=OfflineOrder.amount_fen,
                    )
                ),
                0,
            ),
            func.count(OfflineOrder.id),
        )
        .filter(
            OfflineOrder.created_at >= start_at,
            OfflineOrder.created_at < end_at,
        )
        .one()
    )

    redeem_rows = (
        db.query(
            CreditRedeemKey.credit_amount,
            func.count(CreditRedeemKey.id).label("used_count"),
        )
        .filter(
            CreditRedeemKey.used_at.is_not(None),
            CreditRedeemKey.used_at >= start_at,
            CreditRedeemKey.used_at < end_at,
        )
        .group_by(CreditRedeemKey.credit_amount)
        .all()
    )
    redeem_revenue_yuan = 0.0
    redeem_used_count = 0
    for row in redeem_rows:
        credit_amount = int(row.credit_amount or 0)
        used_count = int(row.used_count or 0)
        redeem_used_count += used_count
        redeem_revenue_yuan += used_count * float(REDEEM_UNIT_PRICES.get(credit_amount, 0.0))

    task_total_count, task_success_count, task_failed_count = (
        db.query(
            func.count(Task.id),
            func.sum(case((Task.status == "success", 1), else_=0)),
            func.sum(case((Task.status == "failed", 1), else_=0)),
        )
        .filter(
            Task.created_at >= start_at,
            Task.created_at < end_at,
            Task.is_deleted.is_(False),
            _exclude_example_template_seed_task_clause(),
        )
        .one()
    )

    credit_consumed = (
        db.query(func.coalesce(func.sum(-CreditLog.amount), 0))
        .filter(
            CreditLog.type == "consume",
            CreditLog.created_at >= start_at,
            CreditLog.created_at < end_at,
        )
        .scalar()
    )

    return DailyReportStats(
        start_at=start_at,
        end_at=end_at,
        revenue_fen=int(revenue_fen or 0),
        paid_order_count=int(paid_order_count or 0),
        offline_order_revenue_fen=int(offline_order_revenue_fen or 0),
        offline_order_count=int(offline_order_count or 0),
        redeem_revenue_yuan=round(redeem_revenue_yuan, 2),
        redeem_used_count=redeem_used_count,
        task_total_count=int(task_total_count or 0),
        task_success_count=int(task_success_count or 0),
        task_failed_count=int(task_failed_count or 0),
        credit_consumed=int(credit_consumed or 0),
    )


def build_daily_report_markdown(stats: DailyReportStats) -> str:
    revenue_yuan = f"{stats.revenue_fen / 100:.2f}"
    offline_order_revenue_yuan = f"{stats.offline_order_revenue_fen / 100:.2f}"
    report_start_date = stats.start_at.strftime("%Y-%m-%d")
    report_end_date = (stats.end_at - timedelta(seconds=1)).strftime("%Y-%m-%d")
    report_period = report_start_date if report_start_date == report_end_date else f"{report_start_date} ~ {report_end_date}"
    return (
        f"## 📊 周期经营数据报告\n"
        f"> 📅 周期: **{report_period}**\n"
        f"> 🕒 统计区间: {stats.start_at.strftime('%Y-%m-%d %H:%M')} ~ {stats.end_at.strftime('%Y-%m-%d %H:%M')}\n"
        f"> 💰 总营业额: <font color=\"warning\">¥{stats.total_revenue_yuan:.2f}</font>\n"
        f"> 💵 在线支付营业额: <font color=\"warning\">¥{revenue_yuan}</font>\n"
        f"> ✅ 支付成功订单数: **{stats.paid_order_count}**\n"
        f"> 🧾 线下订单营业额: <font color=\"warning\">¥{offline_order_revenue_yuan}</font>\n"
        f"> 📝 线下订单录入数: **{stats.offline_order_count}**\n"
        f"> 🎟️ 兑换码营业额: <font color=\"warning\">¥{stats.redeem_revenue_yuan:.2f}</font>\n"
        f"> 🔑 兑换码使用次数: **{stats.redeem_used_count}**\n"
        f"> 🖼️ 任务总数: **{stats.task_total_count}**\n"
        f"> 🟢 成功任务数: **{stats.task_success_count}**\n"
        f"> 🔴 失败任务数: **{stats.task_failed_count}**\n"
        f"> ⚡ 积分消耗: **{stats.credit_consumed}**"
    )


def send_previous_day_report(
    db: Session,
    *,
    reference_time: datetime | None = None,
) -> DailyReportSendResult:
    start_at, end_at = get_previous_day_window(reference_time)
    return send_range_report(db, start_at=start_at, end_at=end_at)


def send_range_report(
    db: Session,
    *,
    start_at: datetime,
    end_at: datetime,
) -> DailyReportSendResult:
    normalized_start = to_local_naive(start_at)
    normalized_end = to_local_naive(end_at)
    stats = collect_daily_report_stats(db, start_at=normalized_start, end_at=normalized_end)
    sent = False
    if is_wecom_notify_enabled():
        sent = send_wecom_markdown(build_daily_report_markdown(stats))
    return DailyReportSendResult(sent=sent, stats=stats)
