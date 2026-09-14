from __future__ import annotations

import json

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.models.feedback import Feedback, FeedbackMessage
from app.models.task import Task
from app.models.user import User
from app.services.image_delivery_service import get_optional_cos_config, serialize_asset_urls, serialize_image
from app.services.business_id_service import (
    feedback_external_id,
    feedback_message_external_id,
    get_feedback_by_business_id,
    get_task_by_business_id,
    task_external_id,
    user_external_id,
)
from app.services.task_service import is_task_generation_failure_credit_refunded
from app.services.task_type_service import get_task_scene_type_map, resolve_task_type_for_task
from app.services.user_credit_service import get_user_credit_account
from app.services.wecom_notify_service import format_wecom_user_label, send_wecom_markdown
from app.utils.datetime_utils import now_local

VALID_FEEDBACK_STATUSES = {"pending", "processing", "completed"}
VALID_FEEDBACK_TYPES = {
    "general",
    "image_task",
    "video_task",
    "canvas",
    "purchase",
    "feature_request",
    "bug_report",
    "optimization",
}
SUGGESTION_FEEDBACK_TYPES = {"feature_request", "bug_report", "optimization"}


def _feedback_base_query(db: Session, *, include_task: bool = False):
    query = db.query(Feedback).options(
        selectinload(Feedback.user),
        selectinload(Feedback.handler),
    )
    if include_task:
        query = query.options(
            selectinload(Feedback.task).selectinload(Task.user),
            selectinload(Feedback.task).selectinload(Task.images),
        )
    return query


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


def _validate_feedback_type(feedback_type: str | None) -> str:
    normalized = (feedback_type or "").strip() or "general"
    if normalized not in VALID_FEEDBACK_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的反馈类型")
    return normalized


def _coerce_feedback_type(feedback_type: str | None) -> str:
    normalized = (feedback_type or "").strip() or "general"
    return normalized if normalized in VALID_FEEDBACK_TYPES else "general"


def _parse_feedback_attachments(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        values = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(values, list):
        return []
    attachments: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized:
            attachments.append(normalized)
    return attachments


def _validate_feedback_attachments(attachments: list[str] | None) -> list[str]:
    normalized_items: list[str] = []
    for raw in attachments or []:
        normalized = str(raw or "").strip()
        if not normalized:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="反馈附件地址不能为空")
        normalized_items.append(normalized)
    if len(normalized_items) > 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="反馈图片最多上传 5 张")
    return normalized_items


def _feedback_type_label(feedback_type: str) -> str:
    return {
        "general": "通用反馈",
        "image_task": "图片任务反馈",
        "video_task": "视频任务反馈",
        "canvas": "Canvas反馈",
        "purchase": "购买积分反馈",
        "feature_request": "功能建议",
        "bug_report": "问题反馈",
        "optimization": "优化建议",
    }.get(feedback_type, feedback_type or "通用反馈")


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


def _build_empty_feedback_task() -> dict:
    return {
        "task_id": "",
        "model": "",
        "mode": "generate",
        "task_type": "text_generate",
        "source": "web",
        "prompt": "",
        "status": "",
        "error_message": "",
        "credit_refunded": False,
        "created_at": None,
        "reference_images": [],
        "reference_image_thumbs": [],
        "images": [],
    }


def _load_task_business_id_map(db: Session, task_ids: list[int]) -> dict[int, str]:
    normalized_ids = sorted({int(task_id) for task_id in task_ids if task_id})
    if not normalized_ids:
        return {}
    rows = db.query(Task.id, Task.business_id).filter(Task.id.in_(normalized_ids)).all()
    return {int(task_id): str(business_id or "") for task_id, business_id in rows}


def _serialize_feedback(
    item: Feedback,
    *,
    db: Session,
    include_task: bool = False,
    include_task_images: bool = False,
    task_business_id_map: dict[int, str] | None = None,
) -> dict:
    task = item.task if include_task else None
    task_user = task.user if task else None
    handler = item.handler
    scene_type_map = get_task_scene_type_map(db)
    reference_assets = _serialize_task_reference_images(task, db=db) if include_task_images else []
    task_credit_cost = int(task.credit_cost or 0) if task else 0
    task_credit_refunded = False
    if task and task.status == "failed" and task_credit_cost > 0:
        task_credit_refunded = bool(is_task_generation_failure_credit_refunded(db, task.id))
    feedback_type = _coerce_feedback_type(item.feedback_type)
    task_external = ""
    if task:
        task_external = task_external_id(task)
    elif item.task_id and task_business_id_map:
        task_external = task_business_id_map.get(int(item.task_id), "")
    return {
        "feedback_id": feedback_external_id(item),
        "user_id": user_external_id(item.user),
        "username": item.user.username if item.user else "",
        "task_id": task_external,
        "feedback_type": feedback_type,
        "attachments": _parse_feedback_attachments(item.attachments_json),
        "status": item.status or "pending",
        "is_read": bool(item.is_read),
        "content": item.content or "",
        "process_note": item.process_note or "",
        "result_note": item.result_note or "",
        "handler_id": user_external_id(handler) if handler else None,
        "handler_name": handler.username if handler else "",
        "handled_at": item.handled_at,
        "last_message_at": item.last_message_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "task_user_id": user_external_id(task_user),
        "task": (
            {
                "task_id": task_external_id(task),
                "model": task.model if task else "",
                "mode": task.mode if task else "generate",
                "task_type": resolve_task_type_for_task(task, scene_type_map=scene_type_map) if task else "text_generate",
                "source": task.source if task else "web",
                "prompt": task.prompt if task else "",
                "status": task.status if task else "",
                "error_message": task.error_message if task else "",
                "credit_refunded": task_credit_refunded,
                "created_at": task.created_at if task else None,
                "reference_images": [asset["image_url"] for asset in reference_assets],
                "reference_image_thumbs": [asset["thumb_url"] for asset in reference_assets],
                "images": _serialize_task_images(task, db=db) if include_task_images else [],
            }
            if task
            else {**_build_empty_feedback_task(), "task_id": task_external}
        ),
    }



def _validate_feedback_message_payload(content: str | None, attachments: list[str] | None) -> tuple[str, list[str]]:
    normalized_content = (content or "").strip()
    if len(normalized_content) > 1500:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="回复内容不能超过 1500 个字符")
    normalized_attachments = _validate_feedback_attachments(attachments)
    if len(normalized_attachments) > 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="每条回复最多上传 1 张图片")
    if not normalized_content and not normalized_attachments:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="回复内容或图片不能为空")
    return normalized_content, normalized_attachments


def _serialize_feedback_message(message: FeedbackMessage) -> dict:
    sender = message.sender
    return {
        "message_id": feedback_message_external_id(message),
        "feedback_id": feedback_external_id(message.feedback),
        "sender_role": message.sender_role or "user",
        "sender_id": user_external_id(sender) if sender else None,
        "sender_name": sender.username if sender else ("系统" if message.sender_role == "system" else ""),
        "content": message.content or "",
        "attachments": _parse_feedback_attachments(message.attachments_json),
        "created_at": message.created_at,
    }


def _send_feedback_message_notification(db: Session, item: Feedback, message: FeedbackMessage, *, user: User) -> None:
    if message.sender_role != "user":
        return
    content = (message.content or "").strip()
    content_preview = content if len(content) <= 200 else content[:200] + "..."
    attachment_count = len(_parse_feedback_attachments(message.attachments_json))
    user_label = format_wecom_user_label(user)
    send_wecom_markdown(
        "## 用户追加反馈消息\n"
        f"> 反馈单号: `{feedback_external_id(item)}`\n"
        f"> 用户: **{user_label}**\n"
        f"> 发送时间: {now_local().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"> 图片数量: **{attachment_count}**\n"
        f"> 消息内容: {content_preview or '已上传图片'}"
    )

def _send_feedback_created_notification(db: Session, item: Feedback, *, user: User) -> None:
    content = (item.content or "").strip()
    content_preview = content if len(content) <= 200 else content[:200] + "..."
    feedback_type = _coerce_feedback_type(item.feedback_type)
    attachment_count = len(_parse_feedback_attachments(item.attachments_json))
    user_label = format_wecom_user_label(user)
    credit_account = get_user_credit_account(db, user.id, create_if_missing=False)
    remain_credit = int(credit_account.remain_credit or 0) if credit_account else 0
    used_credit = int(credit_account.used_credit or 0) if credit_account else 0
    send_wecom_markdown(
        "## 💬 用户提交新反馈\n"
        f"> 🧾 反馈单号: `{feedback_external_id(item)}`\n"
        f"> 🏷️ 类型: **{_feedback_type_label(feedback_type)}**\n"
        f"> 👤 用户: **{user_label}**\n"
        f"> ⚡ 已使用积分: **{used_credit}**\n"
        f"> ⚡ 剩余积分: **{remain_credit}**\n"
        f"> ⏰ 提交时间: {now_local().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"> 🖼️ 附件数量: **{attachment_count}**\n"
        f"> 📝 反馈内容: {content_preview}"
    )


def create_feedback(
    db: Session,
    user: User,
    task_id: str | None,
    content: str,
    feedback_type: str | None = None,
    attachments: list[str] | None = None,
) -> dict:
    task = None
    if task_id:
        task = get_task_by_business_id(db, task_id)
        if not task or task.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    normalized_feedback_type = _validate_feedback_type(feedback_type)
    normalized_attachments = _validate_feedback_attachments(attachments)
    normalized_content = _validate_feedback_content(content)
    now = now_local()
    item = Feedback(
        user_id=user.id,
        task_id=task.id if task else None,
        content=normalized_content,
        feedback_type=normalized_feedback_type,
        attachments_json=json.dumps(normalized_attachments, ensure_ascii=False),
        status="pending",
        last_message_at=now,
        user_last_read_at=now,
    )
    db.add(item)
    db.flush()
    db.add(FeedbackMessage(
        feedback_id=item.id,
        sender_role="user",
        sender_id=user.id,
        content=normalized_content,
        attachments_json=json.dumps(normalized_attachments, ensure_ascii=False),
        created_at=now,
    ))
    db.commit()
    db.refresh(item)
    _send_feedback_created_notification(db, item, user=user)

    created = _feedback_base_query(db, include_task=True).filter(Feedback.id == item.id).first()
    if not created:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="反馈创建失败")
    return _serialize_feedback(created, db=db, include_task=True, include_task_images=True)


def list_feedbacks(
    db: Session,
    *,
    feedback_id: str | None = None,
    user_id: int | None = None,
    task_id: str | None = None,
    status_filter: str | None = None,
    feedback_type_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    query = _feedback_base_query(db, include_task=False)
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

    if feedback_type_filter:
        normalized_feedback_type = _validate_feedback_type(feedback_type_filter)
        query = query.filter(Feedback.feedback_type == normalized_feedback_type)

    total = query.count()
    rows = (
        query.order_by(Feedback.last_message_at.desc(), Feedback.created_at.desc(), Feedback.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    task_business_id_map = _load_task_business_id_map(db, [int(item.task_id) for item in rows if item.task_id])
    return {
        "total": total,
        "items": [
            _serialize_feedback(item, db=db, task_business_id_map=task_business_id_map)
            for item in rows
        ],
    }


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
        db.query(Feedback.id)
        .join(FeedbackMessage, FeedbackMessage.feedback_id == Feedback.id)
        .filter(
            Feedback.user_id == user_id,
            FeedbackMessage.sender_role.in_(["admin", "system"]),
            (Feedback.user_last_read_at.is_(None)) | (FeedbackMessage.created_at > Feedback.user_last_read_at),
        )
        .distinct()
        .count()
    )


def count_admin_unread_feedbacks(db: Session) -> int:
    return (
        db.query(Feedback.id)
        .join(FeedbackMessage, FeedbackMessage.feedback_id == Feedback.id)
        .filter(
            FeedbackMessage.sender_role == "user",
            (Feedback.admin_last_read_at.is_(None)) | (FeedbackMessage.created_at > Feedback.admin_last_read_at),
        )
        .distinct()
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

    detail = _feedback_base_query(db, include_task=True).filter(Feedback.id == item.id).first()
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")
    return _serialize_feedback(detail, db=db, include_task=True, include_task_images=True)


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

    detail = _feedback_base_query(db, include_task=True).filter(Feedback.id == item.id).first()
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")
    return _serialize_feedback(detail, db=db, include_task=True, include_task_images=True)



def list_feedback_messages(
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

    messages = (
        db.query(FeedbackMessage)
        .options(selectinload(FeedbackMessage.feedback), selectinload(FeedbackMessage.sender))
        .filter(FeedbackMessage.feedback_id == item.id)
        .order_by(FeedbackMessage.created_at.asc(), FeedbackMessage.id.asc())
        .all()
    )
    return {"items": [_serialize_feedback_message(message) for message in messages]}


def create_feedback_message(
    db: Session,
    feedback_id: str,
    *,
    sender: User,
    sender_role: str,
    content: str | None = None,
    attachments: list[str] | None = None,
    user_id: int | None = None,
) -> dict:
    item = get_feedback_by_business_id(db, feedback_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")
    if user_id is not None and item.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")
    if item.status == "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="反馈已关闭，不能继续回复")
    if sender_role not in {"user", "admin"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的发送方")

    normalized_content, normalized_attachments = _validate_feedback_message_payload(content, attachments)
    now = now_local()
    message = FeedbackMessage(
        feedback_id=item.id,
        sender_role=sender_role,
        sender_id=sender.id,
        content=normalized_content,
        attachments_json=json.dumps(normalized_attachments, ensure_ascii=False),
        created_at=now,
    )
    db.add(message)
    item.last_message_at = now
    if sender_role == "user":
        item.user_last_read_at = now
        _send_feedback_message_notification(db, item, message, user=sender)
    else:
        item.handled_by = sender.id
        item.is_read = False
        if item.status == "pending":
            item.status = "processing"
    db.add(item)
    db.commit()

    created = (
        db.query(FeedbackMessage)
        .options(selectinload(FeedbackMessage.feedback), selectinload(FeedbackMessage.sender))
        .filter(FeedbackMessage.id == message.id)
        .first()
    )
    if not created:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="回复发送失败")
    return _serialize_feedback_message(created)


def mark_feedback_as_admin_read(db: Session, feedback_id: str) -> dict:
    item = get_feedback_by_business_id(db, feedback_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")
    item.admin_last_read_at = now_local()
    db.add(item)
    db.commit()
    return {"count": count_admin_unread_feedbacks(db)}


def close_feedback(db: Session, feedback_id: str, *, admin: User) -> dict:
    item = get_feedback_by_business_id(db, feedback_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")
    item.status = "completed"
    item.handled_by = admin.id
    item.handled_at = now_local()
    db.add(item)
    db.commit()

    detail = _feedback_base_query(db, include_task=True).filter(Feedback.id == item.id).first()
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")
    return _serialize_feedback(detail, db=db, include_task=True, include_task_images=True)


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
    item.user_last_read_at = now_local()
    db.add(item)
    db.commit()

    detail = _feedback_base_query(db, include_task=True).filter(Feedback.id == item.id).first()
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")
    return _serialize_feedback(detail, db=db, include_task=True, include_task_images=True)


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

    now = now_local()
    for item in unread_items:
        item.is_read = True
        item.user_last_read_at = now
        db.add(item)

    db.commit()
    return len(unread_items)
