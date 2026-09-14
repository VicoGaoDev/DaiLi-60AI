from datetime import timedelta

from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "banana_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    worker_concurrency=settings.CELERY_WORKER_CONCURRENCY,
    worker_prefetch_multiplier=settings.CELERY_PREFETCH_MULTIPLIER,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    timezone="Asia/Shanghai",
    enable_utc=False,
    beat_schedule={
        "send-daily-wecom-report": {
            "task": "app.workers.reporting.send_daily_wecom_report",
            "schedule": crontab(minute=0, hour=0),
        },
        "cleanup-stale-pending-user-assets": {
            "task": "app.workers.user_assets.cleanup_stale_pending_user_assets",
            "schedule": timedelta(minutes=max(int(settings.USER_ASSET_PENDING_CLEANUP_INTERVAL_MINUTES or 0), 1)),
        }
    },
)

celery_app.autodiscover_tasks(["app.workers"])
