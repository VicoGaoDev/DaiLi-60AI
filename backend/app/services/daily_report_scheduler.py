from __future__ import annotations

import logging
import threading
from datetime import date, datetime, time, timedelta

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, engine
from app.models.daily_report_run import DailyReportRun
from app.services.daily_report_service import send_previous_day_report
from app.services.wecom_notify_service import is_wecom_notify_enabled
from app.utils.datetime_utils import now_local

logger = logging.getLogger(__name__)

RUN_STATUS_SENDING = "sending"
RUN_STATUS_SENT = "sent"
RUN_STATUS_FAILED = "failed"
MAX_SEND_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 300
SENDING_STALE_MINUTES = 30

_stop_event = threading.Event()
_thread: threading.Thread | None = None
_thread_lock = threading.Lock()


def next_midnight(moment: datetime) -> datetime:
    return datetime.combine(moment.date() + timedelta(days=1), time.min)


def seconds_until_next_midnight(moment: datetime) -> float:
    return max((next_midnight(moment) - moment).total_seconds(), 0.1)


def start_daily_report_scheduler() -> None:
    if not is_wecom_notify_enabled():
        logger.info("Daily WeCom report scheduler disabled")
        return
    if not _is_schema_ready():
        logger.error(
            "Daily report scheduler disabled: run 2026-09-01-002__add-daily-report-run.sql first"
        )
        return

    global _thread
    with _thread_lock:
        if _thread is not None and _thread.is_alive():
            return
        _stop_event.clear()
        _thread = threading.Thread(target=_loop, name="daily-report-scheduler", daemon=True)
        _thread.start()
        logger.info("Daily WeCom report scheduler started")


def stop_daily_report_scheduler(timeout_seconds: float | None = None) -> None:
    _stop_event.set()
    thread = _thread
    if thread is not None and thread.is_alive():
        timeout = timeout_seconds
        if timeout is None:
            timeout = max(int(settings.WECOM_NOTIFY_TIMEOUT_SECONDS or 0), 1) + 5
        thread.join(timeout=timeout)
        if thread.is_alive():
            logger.error("Daily report scheduler did not stop within %.1f seconds", timeout)


def _is_schema_ready() -> bool:
    try:
        inspector = inspect(engine)
        if "daily_report_runs" not in inspector.get_table_names():
            return False
        columns = {column["name"] for column in inspector.get_columns("daily_report_runs")}
        if not {"id", "report_date", "status", "created_at", "updated_at"}.issubset(columns):
            return False
        unique_column_sets = {
            tuple(constraint.get("column_names") or [])
            for constraint in inspector.get_unique_constraints("daily_report_runs")
        }
        unique_column_sets.update(
            tuple(index.get("column_names") or [])
            for index in inspector.get_indexes("daily_report_runs")
            if index.get("unique")
        )
        return ("report_date",) in unique_column_sets
    except Exception:
        logger.exception("Failed to validate daily report database schema")
        return False


def _loop() -> None:
    while not _stop_event.is_set():
        if _stop_event.wait(seconds_until_next_midnight(now_local())):
            break
        for attempt in range(MAX_SEND_ATTEMPTS):
            try:
                if run_daily_report_once():
                    break
            except Exception:
                logger.exception("Daily WeCom report tick failed")
            if attempt + 1 < MAX_SEND_ATTEMPTS and _stop_event.wait(RETRY_DELAY_SECONDS):
                return


def _claim_report(
    db: Session,
    report_date: date,
    *,
    current_time: datetime | None = None,
) -> bool:
    row = (
        db.query(DailyReportRun)
        .filter(DailyReportRun.report_date == report_date)
        .first()
    )
    if row is not None:
        if row.status == RUN_STATUS_SENT:
            return False
        if row.status == RUN_STATUS_SENDING:
            now_value = current_time or now_local()
            stale_before = now_value - timedelta(minutes=SENDING_STALE_MINUTES)
            if row.updated_at is None or row.updated_at > stale_before:
                return False
        row.status = RUN_STATUS_SENDING
    else:
        db.add(DailyReportRun(report_date=report_date, status=RUN_STATUS_SENDING))
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def _finish_report(db: Session, report_date: date, status: str) -> None:
    row = (
        db.query(DailyReportRun)
        .filter(DailyReportRun.report_date == report_date)
        .first()
    )
    if row is None:
        db.add(DailyReportRun(report_date=report_date, status=status))
    else:
        row.status = status
    db.commit()


def run_daily_report_once(reference_time: datetime | None = None) -> bool:
    if not is_wecom_notify_enabled():
        logger.info("Skip daily report because WeCom notify is disabled")
        return False
    if not _is_schema_ready():
        logger.error("Skip daily report because daily_report_runs schema is missing")
        return False

    moment = reference_time or now_local()
    report_date = moment.date() - timedelta(days=1)
    lock_name = f"daily_wecom_report:{report_date.isoformat()}"
    with engine.connect() as conn:
        acquired = conn.execute(text("SELECT GET_LOCK(:n, 0)"), {"n": lock_name}).scalar()
        if acquired != 1:
            logger.info("Skip daily report; another worker holds the date lock")
            return False
        try:
            db = SessionLocal()
            try:
                if not _claim_report(db, report_date, current_time=moment):
                    logger.info("Skip daily report; report date already claimed: %s", report_date)
                    return False
                try:
                    result = send_previous_day_report(db, reference_time=moment)
                except Exception:
                    _finish_report(db, report_date, RUN_STATUS_FAILED)
                    raise
                status = RUN_STATUS_SENT if result.sent else RUN_STATUS_FAILED
                _finish_report(db, report_date, status)
                return result.sent
            finally:
                db.close()
        finally:
            try:
                conn.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": lock_name})
            except Exception:
                logger.exception("Failed to release daily report date lock")
