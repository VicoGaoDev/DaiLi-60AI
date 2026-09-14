from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.api_alert_run import ApiAlertRun
from app.models.image import Image
from app.models.task import Task
from app.models.task_api_attempt import TaskApiAttempt
from app.services.content_safety_service import build_exclude_content_safety_failed_task_clause
from app.services.wecom_notify_service import send_wecom_alert_markdown
from app.utils.datetime_utils import now_local

ALERT_TYPE_PER_API = "per_api"
ALERT_TYPE_OVERALL = "overall"
RUN_STATUS_SKIPPED = "skipped"
RUN_STATUS_SENDING = "sending"
RUN_STATUS_SENT = "sent"
RUN_STATUS_FAILED = "failed"
MAX_MARKDOWN_APIS = 20
SEND_RETRY_TIMES = 2


@dataclass(frozen=True)
class ApiAlertApiStat:
    api_config_id: int | None
    api_config_name: str
    image_count: int
    success_count: int
    avg_duration_seconds: float | None
    alert_reasons: tuple[str, ...] = ()

    @property
    def success_rate(self) -> float:
        if self.image_count <= 0:
            return 0.0
        return (self.success_count / self.image_count) * 100

    @property
    def would_alert(self) -> bool:
        return bool(self.alert_reasons)


@dataclass(frozen=True)
class ApiAlertStats:
    start_at: datetime
    end_at: datetime
    apis: list[ApiAlertApiStat]
    overall_image_count: int
    overall_success_count: int
    api_count: int

    @property
    def overall_success_rate(self) -> float:
        if self.overall_image_count <= 0:
            return 0.0
        return (self.overall_success_count / self.overall_image_count) * 100


@dataclass(frozen=True)
class ApiAlertDecision:
    per_api_alerts: list[ApiAlertApiStat]
    overall_alert: bool
    annotated_apis: list[ApiAlertApiStat]


@dataclass(frozen=True)
class ApiAlertRunResult:
    dry_run: bool
    start_at: datetime
    end_at: datetime
    slot_start: datetime
    stats: ApiAlertStats
    decision: ApiAlertDecision
    sent_per_api: bool = False
    sent_overall: bool = False
    claimed_per_api: str | None = None
    claimed_overall: str | None = None


@dataclass
class _ApiAlertStatAccumulator:
    api_config_id: int | None
    api_config_name: str
    image_count: int = 0
    success_count: int = 0
    duration_seconds_sum: float = 0.0
    duration_count: int = 0

    def add(
        self,
        *,
        api_config_name: str,
        image_count: int,
        success_count: int,
        duration_seconds_sum: float | None,
        duration_count: int,
    ) -> None:
        normalized_name = (api_config_name or "").strip()
        if normalized_name:
            self.api_config_name = normalized_name
        self.image_count += image_count
        self.success_count += success_count
        if duration_seconds_sum is not None:
            self.duration_seconds_sum += duration_seconds_sum
        self.duration_count += duration_count

    def to_api_stat(self) -> ApiAlertApiStat:
        avg_duration = (
            self.duration_seconds_sum / self.duration_count
            if self.duration_count > 0
            else None
        )
        return ApiAlertApiStat(
            api_config_id=self.api_config_id,
            api_config_name=self.api_config_name or f"接口#{self.api_config_id}",
            image_count=self.image_count,
            success_count=self.success_count,
            avg_duration_seconds=avg_duration,
        )


def align_slot_start(moment: datetime, interval_minutes: int) -> datetime:
    interval = max(int(interval_minutes or 0), 1)
    origin = datetime(1970, 1, 1)
    elapsed_minutes = int((moment - origin).total_seconds() // 60)
    return origin + timedelta(minutes=(elapsed_minutes // interval) * interval)


def next_slot_start(moment: datetime, interval_minutes: int) -> datetime:
    interval = max(int(interval_minutes or 0), 1)
    return align_slot_start(moment, interval) + timedelta(minutes=interval)


def seconds_until_next_slot(moment: datetime, interval_minutes: int) -> float:
    wait_seconds = (next_slot_start(moment, interval_minutes) - moment).total_seconds()
    return max(wait_seconds, 0.1)


def get_alert_window(
    reference_time: datetime | None = None,
    *,
    window_minutes: int | None = None,
) -> tuple[datetime, datetime]:
    end_at = reference_time or now_local()
    window = max(int(window_minutes if window_minutes is not None else settings.API_ALERT_WINDOW_MINUTES or 0), 1)
    return end_at - timedelta(minutes=window), end_at


def _exclude_example_template_seed_task_clause():
    return or_(Task.is_example_template_seed.is_(False), Task.is_example_template_seed.is_(None))


def _sync_task_clause():
    return or_(Task.provider_task_id.is_(None), Task.provider_task_id == "")


def _async_task_clause():
    return Task.provider_task_id.is_not(None), Task.provider_task_id != ""


def _image_duration_seconds_expr():
    return func.unix_timestamp(Image.request_finished_at) - func.unix_timestamp(
        Image.request_started_at
    )


def collect_api_alert_stats(
    db: Session,
    *,
    start_at: datetime,
    end_at: datetime,
) -> ApiAlertStats:
    window_images = (
        db.query(Image.id.label("image_id"))
        .join(Task, Task.id == Image.task_id)
        .filter(
            Image.request_finished_at.is_not(None),
            Image.request_finished_at >= start_at,
            Image.request_finished_at < end_at,
            Image.status.in_(("success", "failed")),
            build_exclude_content_safety_failed_task_clause(Image.status, Image.error_message),
            _exclude_example_template_seed_task_clause(),
        )
        .subquery()
    )
    duration_seconds = _image_duration_seconds_expr()
    sync_grouped = (
        db.query(
            TaskApiAttempt.api_config_id.label("api_config_id"),
            func.max(TaskApiAttempt.api_config_name).label("api_config_name"),
            func.count(TaskApiAttempt.id).label("image_count"),
            func.coalesce(func.sum(case((TaskApiAttempt.status == "success", 1), else_=0)), 0).label("success_count"),
            func.sum(TaskApiAttempt.duration_ms / 1000.0).label("duration_seconds_sum"),
            func.count(TaskApiAttempt.duration_ms).label("duration_count"),
        )
        .select_from(TaskApiAttempt)
        .join(window_images, window_images.c.image_id == TaskApiAttempt.image_id)
        .join(Image, Image.id == TaskApiAttempt.image_id)
        .join(Task, Task.id == Image.task_id)
        .filter(
            TaskApiAttempt.api_config_id.is_not(None),
            TaskApiAttempt.status.in_(("success", "failed")),
            build_exclude_content_safety_failed_task_clause(
                TaskApiAttempt.status,
                TaskApiAttempt.error_message,
            ),
            _sync_task_clause(),
            _exclude_example_template_seed_task_clause(),
        )
        .group_by(TaskApiAttempt.api_config_id)
        .all()
    )

    async_latest_attempt = (
        db.query(
            TaskApiAttempt.image_id.label("image_id"),
            func.max(TaskApiAttempt.id).label("attempt_id"),
        )
        .join(window_images, window_images.c.image_id == TaskApiAttempt.image_id)
        .join(Image, Image.id == TaskApiAttempt.image_id)
        .join(Task, Task.id == Image.task_id)
        .filter(*_async_task_clause())
        .group_by(TaskApiAttempt.image_id)
        .subquery()
    )
    async_grouped = (
        db.query(
            TaskApiAttempt.api_config_id.label("api_config_id"),
            func.max(TaskApiAttempt.api_config_name).label("api_config_name"),
            func.count(Image.id).label("image_count"),
            func.coalesce(func.sum(case((Image.status == "success", 1), else_=0)), 0).label("success_count"),
            func.sum(duration_seconds).label("duration_seconds_sum"),
            func.count(duration_seconds).label("duration_count"),
        )
        .select_from(Image)
        .join(Task, Task.id == Image.task_id)
        .join(async_latest_attempt, async_latest_attempt.c.image_id == Image.id)
        .join(TaskApiAttempt, TaskApiAttempt.id == async_latest_attempt.c.attempt_id)
        .filter(
            Image.request_finished_at.is_not(None),
            Image.request_finished_at >= start_at,
            Image.request_finished_at < end_at,
            Image.status.in_(("success", "failed")),
            TaskApiAttempt.api_config_id.is_not(None),
            _exclude_example_template_seed_task_clause(),
        )
        .group_by(TaskApiAttempt.api_config_id)
        .all()
    )

    accumulators: dict[int, _ApiAlertStatAccumulator] = {}
    for row in [*sync_grouped, *async_grouped]:
        if row.api_config_id is None and not (row.api_config_name or "").strip():
            continue
        api_config_id = int(row.api_config_id) if row.api_config_id is not None else None
        if api_config_id is None:
            continue
        accumulator = accumulators.setdefault(
            api_config_id,
            _ApiAlertStatAccumulator(
                api_config_id=api_config_id,
                api_config_name=(row.api_config_name or "").strip() or f"接口#{api_config_id}",
            ),
        )
        accumulator.add(
            api_config_name=row.api_config_name or "",
            image_count=int(row.image_count or 0),
            success_count=int(row.success_count or 0),
            duration_seconds_sum=(
                None
                if row.duration_seconds_sum is None
                else float(row.duration_seconds_sum)
            ),
            duration_count=int(row.duration_count or 0),
        )

    apis = [
        accumulator.to_api_stat()
        for accumulator in accumulators.values()
    ]
    apis.sort(key=lambda item: (item.success_rate, -(item.avg_duration_seconds or 0), item.api_config_name))

    overall_image_count = sum(api.image_count for api in apis)
    overall_success_count = sum(api.success_count for api in apis)

    return ApiAlertStats(
        start_at=start_at,
        end_at=end_at,
        apis=apis,
        overall_image_count=int(overall_image_count or 0),
        overall_success_count=int(overall_success_count or 0),
        api_count=len(apis),
    )


def evaluate_api_alerts(
    stats: ApiAlertStats,
    *,
    min_call_count: int | None = None,
    overall_min_call_count: int | None = None,
    success_rate_threshold: float | None = None,
    avg_duration_seconds: float | None = None,
) -> ApiAlertDecision:
    min_count = max(int(min_call_count if min_call_count is not None else settings.API_ALERT_MIN_CALL_COUNT or 0), 1)
    overall_min = max(
        int(
            overall_min_call_count
            if overall_min_call_count is not None
            else settings.API_ALERT_OVERALL_MIN_CALL_COUNT or 0
        ),
        1,
    )
    rate_threshold = float(
        success_rate_threshold
        if success_rate_threshold is not None
        else settings.API_ALERT_SUCCESS_RATE_THRESHOLD
    )
    duration_threshold = float(
        avg_duration_seconds
        if avg_duration_seconds is not None
        else settings.API_ALERT_AVG_DURATION_SECONDS
    )

    annotated: list[ApiAlertApiStat] = []
    per_api_alerts: list[ApiAlertApiStat] = []
    for api in stats.apis:
        reasons: list[str] = []
        if api.image_count >= min_count:
            if api.success_rate < rate_threshold:
                reasons.append("success_rate")
            if api.avg_duration_seconds is not None and api.avg_duration_seconds > duration_threshold:
                reasons.append("duration")
        annotated_api = ApiAlertApiStat(
            api_config_id=api.api_config_id,
            api_config_name=api.api_config_name,
            image_count=api.image_count,
            success_count=api.success_count,
            avg_duration_seconds=api.avg_duration_seconds,
            alert_reasons=tuple(reasons),
        )
        annotated.append(annotated_api)
        if reasons:
            per_api_alerts.append(annotated_api)

    overall_alert = stats.overall_image_count >= overall_min and stats.overall_success_rate < rate_threshold
    return ApiAlertDecision(
        per_api_alerts=per_api_alerts,
        overall_alert=overall_alert,
        annotated_apis=annotated,
    )


def _format_range(start_at: datetime, end_at: datetime) -> str:
    return f"{start_at.strftime('%Y-%m-%d %H:%M')} ~ {end_at.strftime('%Y-%m-%d %H:%M')}"


def _format_api_line(api: ApiAlertApiStat) -> str:
    duration = "—" if api.avg_duration_seconds is None else f"{api.avg_duration_seconds:.1f}s"
    success_text = f"成功率 {api.success_rate:.1f}% ({api.success_count}/{api.image_count})"
    duration_text = f"平均耗时 {duration}"
    if "success_rate" in api.alert_reasons:
        success_text = f'<font color="warning">{success_text}</font>'
    if "duration" in api.alert_reasons:
        duration_text = f'<font color="warning">{duration_text}</font>'
    return f"> 🔴 **{api.api_config_name}**\n> {success_text}　｜　{duration_text}"


def build_per_api_markdown(stats: ApiAlertStats, alerts: list[ApiAlertApiStat]) -> str:
    lines = [
        "## 🚨 接口质量告警",
        '> 状态: <font color="warning">**接口指标异常**</font>',
        f"> 统计区间: {_format_range(stats.start_at, stats.end_at)}",
        f"> 告警规则: 成功率 < {settings.API_ALERT_SUCCESS_RATE_THRESHOLD:g}% 或 平均耗时 > {settings.API_ALERT_AVG_DURATION_SECONDS:g}s",
        "",
    ]
    for api in alerts[:MAX_MARKDOWN_APIS]:
        lines.append(_format_api_line(api))
    omitted = len(alerts) - MAX_MARKDOWN_APIS
    if omitted > 0:
        lines.append(f"> 另有 {omitted} 个接口也触发阈值，已省略")
    return "\n".join(lines)


def build_overall_markdown(stats: ApiAlertStats) -> str:
    return (
        "## 🚨 全量接口成功率告警\n"
        '> 状态: <font color="warning">**整体成功率异常**</font>\n'
        f"> 统计区间: {_format_range(stats.start_at, stats.end_at)}\n"
        f"> 告警规则: 全部接口合计成功率 < {settings.API_ALERT_SUCCESS_RATE_THRESHOLD:g}%\n"
        "\n"
        f"> 合计成功率: <font color=\"warning\">**{stats.overall_success_rate:.1f}%**</font> "
        f"({stats.overall_success_count}/{stats.overall_image_count})\n"
        f"> 涉及接口数: **{stats.api_count}**"
    )


def _send_with_retry(content: str) -> bool:
    for attempt in range(SEND_RETRY_TIMES):
        if send_wecom_alert_markdown(content):
            return True
        if attempt + 1 < SEND_RETRY_TIMES:
            time.sleep(1)
    return False


def _get_run(db: Session, slot_start: datetime, alert_type: str) -> ApiAlertRun | None:
    return (
        db.query(ApiAlertRun)
        .filter(ApiAlertRun.slot_start == slot_start, ApiAlertRun.alert_type == alert_type)
        .first()
    )


def _save_run(db: Session, slot_start: datetime, alert_type: str, status: str) -> None:
    row = _get_run(db, slot_start, alert_type)
    if row is None:
        db.add(ApiAlertRun(slot_start=slot_start, alert_type=alert_type, status=status))
    else:
        row.status = status
    db.commit()


def _claim_run(db: Session, slot_start: datetime, alert_type: str) -> bool:
    row = _get_run(db, slot_start, alert_type)
    if row is not None:
        if row.status in {RUN_STATUS_SENDING, RUN_STATUS_SENT, RUN_STATUS_SKIPPED}:
            return False
        row.status = RUN_STATUS_SENDING
    else:
        db.add(ApiAlertRun(slot_start=slot_start, alert_type=alert_type, status=RUN_STATUS_SENDING))
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def preview_api_alerts(
    db: Session,
    *,
    reference_time: datetime | None = None,
) -> ApiAlertRunResult:
    return execute_api_alerts(db, reference_time=reference_time, send=False, claim_slot=False)


def execute_api_alerts(
    db: Session,
    *,
    reference_time: datetime | None = None,
    send: bool = False,
    claim_slot: bool = False,
) -> ApiAlertRunResult:
    moment = reference_time or now_local()
    start_at, end_at = get_alert_window(moment)
    slot_start = align_slot_start(moment, settings.API_ALERT_INTERVAL_MINUTES)
    stats = collect_api_alert_stats(db, start_at=start_at, end_at=end_at)
    decision = evaluate_api_alerts(stats)

    sent_per_api = False
    sent_overall = False
    claimed_per_api = None
    claimed_overall = None

    if decision.per_api_alerts:
        can_send_per_api = not claim_slot or _claim_run(db, slot_start, ALERT_TYPE_PER_API)
        if send and can_send_per_api:
            sent_per_api = _send_with_retry(build_per_api_markdown(stats, decision.per_api_alerts))
            if claim_slot:
                claimed_per_api = RUN_STATUS_SENT if sent_per_api else RUN_STATUS_FAILED
                _save_run(db, slot_start, ALERT_TYPE_PER_API, claimed_per_api)
        elif claim_slot:
            existing = _get_run(db, slot_start, ALERT_TYPE_PER_API)
            claimed_per_api = existing.status if existing else None
    elif claim_slot and _claim_run(db, slot_start, ALERT_TYPE_PER_API):
        claimed_per_api = RUN_STATUS_SKIPPED
        _save_run(db, slot_start, ALERT_TYPE_PER_API, claimed_per_api)

    if decision.overall_alert:
        can_send_overall = not claim_slot or _claim_run(db, slot_start, ALERT_TYPE_OVERALL)
        if send and can_send_overall:
            sent_overall = _send_with_retry(build_overall_markdown(stats))
            if claim_slot:
                claimed_overall = RUN_STATUS_SENT if sent_overall else RUN_STATUS_FAILED
                _save_run(db, slot_start, ALERT_TYPE_OVERALL, claimed_overall)
        elif claim_slot:
            existing = _get_run(db, slot_start, ALERT_TYPE_OVERALL)
            claimed_overall = existing.status if existing else None
    elif claim_slot and _claim_run(db, slot_start, ALERT_TYPE_OVERALL):
        claimed_overall = RUN_STATUS_SKIPPED
        _save_run(db, slot_start, ALERT_TYPE_OVERALL, claimed_overall)

    return ApiAlertRunResult(
        dry_run=not send,
        start_at=start_at,
        end_at=end_at,
        slot_start=slot_start,
        stats=stats,
        decision=decision,
        sent_per_api=sent_per_api,
        sent_overall=sent_overall,
        claimed_per_api=claimed_per_api,
        claimed_overall=claimed_overall,
    )
