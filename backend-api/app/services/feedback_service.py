from __future__ import annotations

import json

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.models.feedback import Feedback
from app.models.task import Task
from app.models.user import User
from app.services.image_delivery_service import get_optional_cos_config, serialize_asset_urls, serialize_image
from app.services.business_id_service import (
    feedback_external_id,
    get_feedback_by_business_id,
    get_task_by_business_id,
    task_external_id,
    user_external_id,
)
from app.services.task_type_service import get_task_scene_type_map, resolve_task_type_for_task
from app.utils.datetime_utils import now_local

VALID_FEEDBACK_STATUSES = {"pending", "processing", "completed"}


def _feedback_base_query(db: Session):
    return (
        db.query(Feedback)
        .options(
            selectinload(Feedback.user),
            selectinload(Feedback.handler),
            selectinload(Feedback.task).selectinload(Task.user),
            selectinload(Feedback.task).selectinload(Task.images),
        )
    )


def _resolve_task_filter(db: Session, task_id: str | None) -> int | None:
    if not task_id:
        return None
    task = get_task_by_business_id(db, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return task.id


def _validate_feedback_content(content: str) -> str:
    normalized = (content or "").strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="反馈内容不能为空")
    if len(normalized) > 5000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="反馈内容不能超过 5000 个字符")
    return normalized


def _validate_optional_text(value: str | None, field_label: str) -> str:
    normalized = (value or "").strip()
    if len(normalized) > 5000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_label}不能超过 5000 个字符")
    return normalized


def _serialize_task_images(task: Task | None, *, db: Session) -> list[dict]:
    if not task:
        return []
    cos_config = get_optional_cos_config(db)
    return [
        serialize_image(image, cos_config=cos_config)
        for image in sorted(task.images or [], key=lambda candidate: candidate.id, reverse=True)
        if not image.is_deleted
    ]


def _parse_reference_images(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        refs = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(ref).strip() for ref in refs if str(ref or "").strip()] if isinstance(refs, list) else []


def _serialize_task_reference_images(task: Task | None, *, db: Session) -> list[dict[str, str]]:
    if not task:
        return []
    cos_config = get_optional_cos_config(db)
    return [serialize_asset_urls(ref, cos_config=cos_config) for ref in _parse_reference_images(task.reference_images)]


def _serialize_feedback(item: Feedback, *, db: Session, include_task_images: bool = False) -> dict:
    task = item.task
    task_user = task.user if task else None
    handler = item.handler
    scene_type_map = get_task_scene_type_map(db)
    reference_assets = _serialize_task_reference_images(task, db=db) if include_task_images else []
    return {
        "feedback_id": feedback_external_id(item),
        "user_id": user_external_id(item.user),
        "username": item.user.username if item.user else "",
        "task_id": task_external_id(task),
        "status": item.status or "pending",
        "is_read": bool(item.is_read),
        "content": item.content or "",
        "process_note": item.process_note or "",
        "result_note": item.result_note or "",
        "handler_id": user_external_id(handler) if handler else None,
        "handler_name": handler.username if handler else "",
        "handled_at": item.handled_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "task_user_id": user_external_id(task_user),
        "task": {
            "task_id": task_external_id(task),
            "model": task.model if task else "",
            "mode": task.mode if task else "generate",
            "task_type": resolve_task_type_for_task(task, scene_type_map=scene_type_map) if task else "text_generate",
            "source": task.source if task else "web",
            "prompt": task.prompt if task else "",
            "status": task.status if task else "",
            "created_at": task.created_at if task else None,
            "reference_images": [asset["image_url"] for asset in reference_assets],
            "reference_image_thumbs": [asset["thumb_url"] for asset in reference_assets],
            "images": _serialize_task_images(task, db=db) if include_task_images else [],
        },
    }


def create_feedback(db: Session, user: User, task_id: str | None, content: str) -> dict:
    task = None
    if task_id:
        task = get_task_by_business_id(db, task_id)
        if not task or task.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    item = Feedback(
        user_id=user.id,
        task_id=task.id if task else None,
        content=_validate_feedback_content(content),
        status="pending",
    )
    db.add(item)
    db.commit()

    created = _feedback_base_query(db).filter(Feedback.id == item.id).first()
    if not created:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="反馈创建失败")
    return _serialize_feedback(created, db=db, include_task_images=True)


def list_feedbacks(
    db: Session,
    *,
    feedback_id: str | None = None,
    user_id: int | None = None,
    task_id: str | None = None,
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    query = _feedback_base_query(db)
    if feedback_id:
        feedback = get_feedback_by_business_id(db, feedback_id)
        if not feedback:
            return {"total": 0, "items": []}
        query = query.filter(Feedback.id == feedback.id)

    if user_id is not None:
        query = query.filter(Feedback.user_id == user_id)

    resolved_task_id = _resolve_task_filter(db, task_id)
    if resolved_task_id is not None:
        query = query.filter(Feedback.task_id == resolved_task_id)

    if status_filter:
        if status_filter not in VALID_FEEDBACK_STATUSES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的反馈状态")
        query = query.filter(Feedback.status == status_filter)

    total = query.count()
    rows = (
        query.order_by(Feedback.created_at.desc(), Feedback.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"total": total, "items": [_serialize_feedback(item, db=db) for item in rows]}


def count_unresolved_feedbacks(
    db: Session,
    *,
    user_id: int | None = None,
) -> int:
    query = db.query(Feedback).filter(Feedback.status != "completed")
    if user_id is not None:
        query = query.filter(Feedback.user_id == user_id)
    return query.count()


def count_user_unread_feedbacks(db: Session, *, user_id: int) -> int:
    return (
        db.query(Feedback)
        .filter(
            Feedback.user_id == user_id,
            Feedback.is_read.is_(False),
        )
        .count()
    )


def get_feedback_detail(
    db: Session,
    feedback_id: str,
    *,
    user_id: int | None = None,
) -> dict:
    item = get_feedback_by_business_id(db, feedback_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")
    if user_id is not None and item.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")

    detail = _feedback_base_query(db).filter(Feedback.id == item.id).first()
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")
    return _serialize_feedback(detail, db=db, include_task_images=True)


def update_feedback(
    db: Session,
    feedback_id: str,
    *,
    admin: User,
    status_value: str | None = None,
    process_note: str | None = None,
    result_note: str | None = None,
) -> dict:
    item = get_feedback_by_business_id(db, feedback_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")

    if status_value is None and process_note is None and result_note is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有可更新的内容")

    if status_value is not None:
        if status_value not in VALID_FEEDBACK_STATUSES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的反馈状态")
        item.status = status_value
        if status_value == "completed":
            item.handled_at = now_local()
        else:
            item.handled_at = None

    if process_note is not None:
        item.process_note = _validate_optional_text(process_note, "处理进度")

    if result_note is not None:
        item.result_note = _validate_optional_text(result_note, "处理结果")

    item.handled_by = admin.id

    if item.status == "completed" and item.handled_at is None:
        item.handled_at = now_local()

    db.add(item)
    db.commit()

    detail = _feedback_base_query(db).filter(Feedback.id == item.id).first()
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")
    return _serialize_feedback(detail, db=db, include_task_images=True)


def mark_feedback_as_read(
    db: Session,
    feedback_id: str,
    *,
    user_id: int,
) -> dict:
    item = get_feedback_by_business_id(db, feedback_id)
    if not item or item.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")

    item.is_read = True
    db.add(item)
    db.commit()

    detail = _feedback_base_query(db).filter(Feedback.id == item.id).first()
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")
    return _serialize_feedback(detail, db=db, include_task_images=True)


def mark_all_feedbacks_as_read(
    db: Session,
    *,
    user_id: int,
) -> int:
    unread_items = (
        db.query(Feedback)
        .filter(
            Feedback.user_id == user_id,
            Feedback.is_read.is_(False),
        )
        .all()
    )
    if not unread_items:
        return 0

    for item in unread_items:
        item.is_read = True
        db.add(item)

    db.commit()
    return len(unread_items)
