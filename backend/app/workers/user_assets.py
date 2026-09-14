from __future__ import annotations

import logging

from app.config import settings
from app.database import SessionLocal
from app.services.user_asset_service import cleanup_stale_pending_assets
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.user_assets.cleanup_stale_pending_user_assets")
def cleanup_stale_pending_user_assets() -> int:
    db = SessionLocal()
    try:
        cleaned = cleanup_stale_pending_assets(
            db,
            limit=max(int(settings.USER_ASSET_PENDING_CLEANUP_BATCH_SIZE or 0), 1),
        )
        if cleaned:
            logger.info("Cleaned stale pending user assets", extra={"cleaned_count": cleaned})
        return cleaned
    except Exception:
        logger.exception("Failed to cleanup stale pending user assets")
        return 0
    finally:
        db.close()
