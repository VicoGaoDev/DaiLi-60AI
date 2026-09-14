from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.update_log import UpdateLog
from app.services.business_id_service import get_update_log_by_business_id, update_log_external_id
from app.utils.datetime_utils import now_local

VALID_UPDATE_LOG_TAG_TYPES = {"notice", "feature", "optimization", "bugfix", "other"}
MAX_TITLE_LENGTH = 200
MAX_CONTENT_LENGTH = 10000


def _normalize_title(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="标题不能为空")
    if len(normalized) > MAX_TITLE_LENGTH:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"标题不能超过 {MAX_TITLE_LENGTH} 个字符")
    return normalized


def _normalize_content(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="内容不能为空")
    if len(normalized) > MAX_CONTENT_LENGTH:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"内容不能超过 {MAX_CONTENT_LENGTH} 个字符")
    return normalized


def _normalize_tag_type(value: str | None) -> str:
    normalized = (value or "").strip()
    if normalized not in VALID_UPDATE_LOG_TAG_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="更新日志标签类型不支持")
    return normalized


def _normalize_effective_at(value: datetime | None) -> datetime:
    return value or now_local()


def _serialize_update_log(item: UpdateLog) -> dict:
    return {
        "log_id": update_log_external_id(item),
        "title": item.title or "",
        "content": item.content or "",
        "tag_type": item.tag_type or "other",
        "effective_at": item.effective_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _get_update_log_or_404(db: Session, log_id: str) -> UpdateLog:
    item = get_update_log_by_business_id(db, log_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="更新日志不存在")
    return item


def list_public_update_logs(db: Session, *, page: int = 1, page_size: int = 20) -> dict:
    now = now_local()
    query = db.query(UpdateLog).filter(UpdateLog.effective_at <= now)
    total = query.count()
    rows = (
        query.order_by(UpdateLog.effective_at.desc(), UpdateLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"total": total, "items": [_serialize_update_log(item) for item in rows]}


def get_public_update_log_detail(db: Session, log_id: str) -> dict:
    item = _get_update_log_or_404(db, log_id)
    if item.effective_at > now_local():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="更新日志不存在")
    return _serialize_update_log(item)


def list_admin_update_logs(db: Session, *, page: int = 1, page_size: int = 20) -> dict:
    query = db.query(UpdateLog)
    total = query.count()
    rows = (
        query.order_by(UpdateLog.effective_at.desc(), UpdateLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"total": total, "items": [_serialize_update_log(item) for item in rows]}


def get_admin_update_log_detail(db: Session, log_id: str) -> dict:
    item = _get_update_log_or_404(db, log_id)
    return _serialize_update_log(item)


def create_update_log(
    db: Session,
    *,
    title: str,
    content: str,
    tag_type: str,
    effective_at: datetime | None,
) -> dict:
    item = UpdateLog(
        title=_normalize_title(title),
        content=_normalize_content(content),
        tag_type=_normalize_tag_type(tag_type),
        effective_at=_normalize_effective_at(effective_at),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize_update_log(item)


def update_update_log(
    db: Session,
    *,
    log_id: str,
    title: str,
    content: str,
    tag_type: str,
    effective_at: datetime | None,
) -> dict:
    item = _get_update_log_or_404(db, log_id)
    item.title = _normalize_title(title)
    item.content = _normalize_content(content)
    item.tag_type = _normalize_tag_type(tag_type)
    item.effective_at = effective_at or item.created_at or now_local()
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize_update_log(item)


def delete_update_log(db: Session, *, log_id: str) -> None:
    item = _get_update_log_or_404(db, log_id)
    db.delete(item)
    db.commit()
