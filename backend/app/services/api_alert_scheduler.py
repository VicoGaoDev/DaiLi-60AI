from __future__ import annotations

import logging
import threading

from sqlalchemy import inspect, text

from app.config import settings
from app.database import SessionLocal, engine
from app.services.api_alert_service import (
    align_slot_start,
    execute_api_alerts,
    seconds_until_next_slot,
)
from app.services.wecom_notify_service import is_wecom_alert_enabled
from app.utils.datetime_utils import now_local

logger = logging.getLogger(__name__)

_stop_event = threading.Event()
_thread: threading.Thread | None = None
_thread_lock = threading.Lock()


def start_api_alert_scheduler() -> None:
    if not is_wecom_alert_enabled():
        logger.info("API alert scheduler disabled")
        return
    if not _is_schema_ready():
        logger.error(
            "API alert scheduler disabled: run 2026-09-01-001__add-api-alert-support.sql first"
        )
        return

    global _thread
    with _thread_lock:
        if _thread is not None and _thread.is_alive():
            return
        _stop_event.clear()
        _thread = threading.Thread(target=_loop, name="api-alert-scheduler", daemon=True)
        _thread.start()
        logger.info("API alert scheduler started")


def stop_api_alert_scheduler(timeout_seconds: float | None = None) -> None:
    _stop_event.set()
    thread = _thread
    if thread is not None and thread.is_alive():
        timeout = timeout_seconds
        if timeout is None:
            timeout = max(int(settings.WECOM_NOTIFY_TIMEOUT_SECONDS or 0), 1) * 2 + 5
        thread.join(timeout=timeout)
        if thread.is_alive():
            logger.error("API alert scheduler did not stop within %.1f seconds", timeout)


def _is_schema_ready() -> bool:
    try:
        inspector = inspect(engine)
        if "api_alert_runs" not in inspector.get_table_names() or "images" not in inspector.get_table_names():
            return False
        run_columns = {column["name"] for column in inspector.get_columns("api_alert_runs")}
        if not {"id", "slot_start", "alert_type", "status", "created_at", "updated_at"}.issubset(run_columns):
            return False
        unique_column_sets = {
            tuple(constraint.get("column_names") or [])
            for constraint in inspector.get_unique_constraints("api_alert_runs")
        }
        unique_column_sets.update(
            tuple(index.get("column_names") or [])
            for index in inspector.get_indexes("api_alert_runs")
            if index.get("unique")
        )
        if ("slot_start", "alert_type") not in unique_column_sets:
            return False
        image_columns = {column["name"] for column in inspector.get_columns("images")}
        if not {"request_started_at", "request_finished_at"}.issubset(image_columns):
            return False
        image_indexes = {index["name"] for index in inspector.get_indexes("images")}
        return "idx_images_request_finished_at" in image_indexes
    except Exception:
        logger.exception("Failed to validate API alert database schema")
        return False


def _loop() -> None:
    interval_minutes = max(int(settings.API_ALERT_INTERVAL_MINUTES or 0), 1)
    while not _stop_event.is_set():
        wait_seconds = seconds_until_next_slot(now_local(), interval_minutes)
        if _stop_event.wait(wait_seconds):
            break
        try:
            run_scheduled_api_alerts()
        except Exception:
            logger.exception("API alert tick failed")


def run_scheduled_api_alerts() -> None:
    if not is_wecom_alert_enabled():
        logger.info("Skip API alert tick because alert webhook is disabled")
        return

    moment = now_local()
    slot_start = align_slot_start(moment, settings.API_ALERT_INTERVAL_MINUTES)
    lock_name = f"api_performance_alert:{slot_start.strftime('%Y%m%d%H%M')}"
    with engine.connect() as conn:
        acquired = conn.execute(text("SELECT GET_LOCK(:n, 0)"), {"n": lock_name}).scalar()
        if acquired != 1:
            logger.info("Skip API alert tick; another worker holds the slot lock")
            return
        try:
            db = SessionLocal()
            try:
                result = execute_api_alerts(db, reference_time=moment, send=True, claim_slot=True)
                logger.info(
                    "API alert tick finished: per_api=%s overall=%s sent_per_api=%s sent_overall=%s",
                    bool(result.decision.per_api_alerts),
                    result.decision.overall_alert,
                    result.sent_per_api,
                    result.sent_overall,
                )
            finally:
                db.close()
        finally:
            try:
                conn.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": lock_name})
            except Exception:
                logger.exception("Failed to release API alert slot lock")
