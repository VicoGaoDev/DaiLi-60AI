from celery import Celery
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
)

celery_app.autodiscover_tasks(["app.workers"])
