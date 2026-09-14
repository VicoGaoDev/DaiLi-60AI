from __future__ import annotations

import logging

from app.services.daily_report_scheduler import run_daily_report_once
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.reporting.send_daily_wecom_report")
def send_daily_wecom_report() -> bool:
    try:
        return run_daily_report_once()
    except Exception:
        logger.exception("Failed to send daily WeCom report")
        return False
