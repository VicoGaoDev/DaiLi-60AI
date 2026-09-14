import json
from datetime import datetime
from typing import Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, lazyload, selectinload
from app.models.task import Task
from app.models.image import Image
from app.models.credit_log import CreditLog
from app.models.prompt_history import PromptHistory
from app.models.history_pin import HistoryPin
from app.models.user import User
from app.services.prompt_reverse_service import (
    PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION,
    PROMPT_REVERSE_MODE,
    PROMPT_REVERSE_MODEL,
)
from app.services.task_type_service import (
    TASK_TYPE_IMAGE_EDIT,
    TASK_TYPE_INPAINT,
    TASK_TYPE_PROMPT_REVERSE,
    TASK_TYPE_TEXT_GENERATE,
    get_task_scene_type_map,
    resolve_task_type_for_task,
)
from app.services.image_delivery_service import (
    get_optional_cos_config,
    sanitize_api_public_message,
    serialize_asset_urls,
    serialize_image,
)
from app.services.business_id_service import task_external_id, user_external_id
from app.services.task_service import (
    ENQUEUE_FAILURE_DESCRIPTION,
    TASK_FAILURE_REFUND_DESCRIPTION,
    is_task_generation_failure_credit_refunded,
)
from app.utils.datetime_utils import now_local
from app.utils.business_id import normalize_business_id

TASK_CREDIT_REFUND_DESCRIPTIONS = (
    ENQUEUE_FAILURE_DESCRIPTION,
    TASK_FAILURE_REFUND_DESCRIPTION,
)


def _parse_refs(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        refs = json.loads(raw)
        return refs if isinstance(refs, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _resolve_history_card_status(task_status: str | None, image_status: str | None) -> str:
    if task_status in {"pending", "queued", "processing"}:
        return task_status
    if image_status == "pending" and task_status in {"pending", "queued", "processing", "failed"}:
        return task_status
    return image_status or task_status or "pending"


def _calculate_task_run_time(task: Task | None) -> int | None:
    if not task or not task.request_finished_at:
        return None
    started_at = task.request_started_at or task.created_at
    if not started_at:
        return None
    return max(0, int((task.request_finished_at - started_at).total_seconds()))


def _build_history_pin_key(item_type: str, image_id: int | None = None, history_id: int | None = None) -> str:
    if item_type == "task" and isinstance(image_id, int):
        return f"task:{image_id}"
    if item_type == "prompt_history" and isinstance(history_id, int):
        return f"prompt_history:{history_id}"
    raise ValueError("invalid_history_pin_target")


def _serialize_history_pin(pin: HistoryPin | None) -> tuple[bool, datetime | None]:
    if not pin:
        return False, None
    return True, pin.pinned_at


def _serialize_history_images(
    images: list[Image],
    *,
    cos_config,
    include_deleted: bool = False,
) -> list[dict]:
    result: list[dict] = []
    for img in sorted(images, key=lambda item: item.id, reverse=True):
        if not include_deleted and img.is_deleted:
            continue
        result.append(serialize_image(img, cos_config=cos_config))
    return result


def _get_refunded_task_ids(db: Session, task_ids: list[int]) -> set[int]:
    normalized_ids = [int(task_id) for task_id in task_ids if task_id]
    if not normalized_ids:
        return set()
    return {
        int(task_id)
        for (task_id,) in (
            db.query(CreditLog.task_id)
            .filter(
                CreditLog.task_id.in_(normalized_ids),
                CreditLog.task_id.is_not(None),
                CreditLog.type == "allocate",
                CreditLog.description.in_(TASK_CREDIT_REFUND_DESCRIPTIONS),
            )
            .distinct()
            .all()
        )
        if task_id
    }


def _serialize_task_history_detail(task: Task, *, cos_config, scene_type_map: dict[str, str] | None = None) -> dict:
    primary_image = next(
        (img for img in sorted(task.images, key=lambda item: item.id, reverse=True) if not img.is_deleted),
        None,
    )
    primary_image_payload = serialize_image(primary_image, cos_config=cos_config) if primary_image else {
        "id": None,
        "image_url": "",
        "preview_url": "",
        "thumb_url": "",
        "status": task.status or "pending",
        "image_format": "",
        "image_size_bytes": 0,
    }
    source_asset = serialize_asset_urls(task.source_image or "", cos_config=cos_config)
    mask_asset = serialize_asset_urls(task.mask_image or "", cos_config=cos_config)
    reference_assets = [serialize_asset_urls(ref, cos_config=cos_config) for ref in _parse_refs(task.reference_images)]
    visible_images = _serialize_history_images(task.images, cos_config=cos_config)
    task_credit_cost = int(task.credit_cost or 0)
    credit_refunded = False
    if task.status == "failed" and task_credit_cost > 0:
        db = Session.object_session(task)
        credit_refunded = bool(db and is_task_generation_failure_credit_refunded(db, task.id))
    return {
        "history_id": None,
        "item_type": "task",
        "display_id": task_external_id(task),
        "task_id": task_external_id(task),
        "image_id": primary_image.id if primary_image else None,
            "user_id": user_external_id(task.user),
            "username": task.user.username if task.user else "",
            "avatar_url": task.user.avatar_url or "" if task.user else "",
        "is_pinned": False,
        "pinned_at": None,
        "image_url": primary_image_payload["image_url"],
        "preview_url": primary_image_payload["preview_url"],
        "thumb_url": primary_image_payload["thumb_url"],
        "status": _resolve_history_card_status(task.status, primary_image_payload["status"]),
        "image_format": primary_image_payload["image_format"],
        "image_size_bytes": primary_image_payload["image_size_bytes"],
        "task_is_deleted": bool(task.is_deleted),
        "is_soft_deleted": False,
        "task_type": resolve_task_type_for_task(task, scene_type_map=scene_type_map),
        "model": task.model or "",
        "source": task.source or "web",
        "mode": task.mode or "generate",
        "prompt": task.prompt or "",
        "reference_images": [asset["image_url"] for asset in reference_assets],
        "reference_image_thumbs": [asset["thumb_url"] for asset in reference_assets],
        "source_image": source_asset["image_url"],
        "source_image_thumb": source_asset["thumb_url"],
        "mask_image": mask_asset["image_url"],
        "mask_image_thumb": mask_asset["thumb_url"],
        "num_images": task.num_images or 1,
        "size": task.size or "",
        "resolution": task.resolution or "",
        "custom_size": task.custom_size or "",
        "credit_cost": task_credit_cost,
        "credit_refunded": credit_refunded,
        "created_at": task.created_at,
        "request_started_at": task.request_started_at,
        "request_finished_at": task.request_finished_at,
        "run_time": _calculate_task_run_time(task),
        "error_message": sanitize_api_public_message(task.error_message),
        "images": visible_images,
    }


def _serialize_prompt_history_detail(row: PromptHistory, *, cos_config) -> dict:
    source_asset = serialize_asset_urls(row.source_image or "", cos_config=cos_config)
    db = Session.object_session(row)
    user = db.query(User).filter(User.id == row.user_id).first() if db else None
    return {
        "history_id": row.id,
        "item_type": "prompt_history",
        "display_id": f"PR-{row.id}",
        "task_id": None,
        "image_id": -row.id,
        "user_id": user_external_id(user),
        "username": user.username if user else "",
        "avatar_url": (user.avatar_url or "") if user else "",
        "is_pinned": False,
        "pinned_at": None,
        "image_url": "",
        "preview_url": "",
        "thumb_url": "",
        "status": "success",
        "image_format": "",
        "image_size_bytes": 0,
        "task_is_deleted": False,
        "is_soft_deleted": False,
        "task_type": TASK_TYPE_PROMPT_REVERSE,
        "model": PROMPT_REVERSE_MODEL,
        "source": "web",
        "mode": PROMPT_REVERSE_MODE,
        "prompt": row.prompt or "",
        "reference_images": [],
        "reference_image_thumbs": [],
        "source_image": source_asset["image_url"],
        "source_image_thumb": source_asset["thumb_url"],
        "mask_image": "",
        "mask_image_thumb": "",
        "num_images": 0,
        "size": "-",
        "resolution": "",
        "custom_size": "",
        "credit_cost": 0,
        "created_at": row.created_at,
        "error_message": "",
        "images": [],
    }


def get_user_history(
    db: Session,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    respect_pins: bool = True,
    include_prompt_reverse: bool = True,
    mode: str | None = None,
    source: str | None = None,
    model: str | None = None,
    prompt: str | None = None,
    status: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
):
    cos_config = get_optional_cos_config(db)
    scene_type_map = get_task_scene_type_map(db)
    current_user = db.query(User).filter(User.id == user_id).first()
    history_pins = (
        db.query(HistoryPin)
        .filter(HistoryPin.user_id == user_id)
        .order_by(HistoryPin.pinned_at.desc(), HistoryPin.id.desc())
        .all()
        if respect_pins
        else []
    )
    history_pin_map = {pin.item_key: pin for pin in history_pins}
    image_query = (
        db.query(Image)
        .join(Task, Image.task_id == Task.id)
        .options(selectinload(Image.task).selectinload(Task.images))
        .filter(Task.user_id == user_id)
        .filter(Task.is_deleted.is_(False))
        .filter(Image.is_deleted.is_(False))
    )
    prompt_reverse_query = None
    if include_prompt_reverse:
        prompt_reverse_query = (
            db.query(PromptHistory)
            .filter(
                PromptHistory.user_id == user_id,
                PromptHistory.mode == PROMPT_REVERSE_MODE,
            )
        )
    if mode:
        if mode == TASK_TYPE_PROMPT_REVERSE:
            image_query = image_query.filter(Task.id.is_(None))
        elif mode == TASK_TYPE_INPAINT:
            image_query = image_query.filter(or_(Task.mode == "inpaint", Task.model == "inpaint"))
            prompt_reverse_query = None
        elif mode == TASK_TYPE_TEXT_GENERATE:
            text_generate_models = [key for key, value in scene_type_map.items() if value == "generate"]
            image_query = image_query.filter(Task.mode == "generate")
            image_query = image_query.filter(Task.model.in_(text_generate_models)) if text_generate_models else image_query.filter(Task.id.is_(None))
            prompt_reverse_query = None
        elif mode == TASK_TYPE_IMAGE_EDIT:
            image_edit_models = [key for key, value in scene_type_map.items() if value == "image_edit"]
            image_query = image_query.filter(Task.mode == "generate")
            image_query = image_query.filter(Task.model.in_(image_edit_models)) if image_edit_models else image_query.filter(Task.id.is_(None))
            prompt_reverse_query = None
        else:
            image_query = image_query.filter(Task.mode == mode)
            if mode != PROMPT_REVERSE_MODE:
                prompt_reverse_query = None
    if source:
        image_query = image_query.filter(Task.source == source)
        if source != "web":
            prompt_reverse_query = None
    if model:
        image_query = image_query.filter(Task.model == model)
        if model != PROMPT_REVERSE_MODEL:
            prompt_reverse_query = None
    if prompt:
        keyword = prompt.strip()
        if keyword:
            image_query = image_query.filter(Task.prompt.ilike(f"%{keyword}%"))
            if prompt_reverse_query is not None:
                prompt_reverse_query = prompt_reverse_query.filter(PromptHistory.prompt.ilike(f"%{keyword}%"))
    if status:
        if status == "processing":
            image_query = image_query.filter(Image.status == "pending", Task.status == "processing")
            prompt_reverse_query = None
        elif status == "pending":
            image_query = image_query.filter(Image.status == "pending", Task.status.in_(["pending", "queued"]))
            prompt_reverse_query = None
        elif status == "failed":
            image_query = image_query.filter(or_(Image.status == "failed", and_(Image.status == "pending", Task.status == "failed")))
            prompt_reverse_query = None
        else:
            image_query = image_query.filter(Image.status == status)
    if start_date:
        image_query = image_query.filter(Task.created_at >= start_date)
        if prompt_reverse_query is not None:
            prompt_reverse_query = prompt_reverse_query.filter(PromptHistory.created_at >= start_date)
    if end_date:
        image_query = image_query.filter(Task.created_at <= end_date)
        if prompt_reverse_query is not None:
            prompt_reverse_query = prompt_reverse_query.filter(PromptHistory.created_at <= end_date)
    start_index = (page - 1) * page_size
    fetch_limit = start_index + page_size
    if respect_pins:
        images = image_query.order_by(Task.created_at.desc(), Image.id.desc()).all()
        prompt_reverse_rows = (
            prompt_reverse_query.order_by(PromptHistory.created_at.desc(), PromptHistory.id.desc()).all()
            if prompt_reverse_query is not None
            else []
        )
        total = None
    else:
        fetch_limit += 1
        total = None
        images = (
            image_query
            .order_by(Task.created_at.desc(), Image.id.desc())
            .limit(fetch_limit)
            .all()
        )
        prompt_reverse_rows = (
            prompt_reverse_query
            .order_by(PromptHistory.created_at.desc(), PromptHistory.id.desc())
            .limit(fetch_limit)
            .all()
            if prompt_reverse_query is not None
            else []
        )
    items = []
    for image in images:
        task = image.task
        task_credit_cost = int(task.credit_cost or 0)
        credit_refunded = False
        if task.status == "failed" and task_credit_cost > 0:
            credit_refunded = is_task_generation_failure_credit_refunded(db, task.id)
        image_payload = serialize_image(image, cos_config=cos_config)
        source_asset = serialize_asset_urls(task.source_image or "", cos_config=cos_config)
        mask_asset = serialize_asset_urls(task.mask_image or "", cos_config=cos_config)
        reference_assets = [serialize_asset_urls(ref, cos_config=cos_config) for ref in _parse_refs(task.reference_images)]
        visible_images = _serialize_history_images(task.images, cos_config=cos_config)
        is_pinned, pinned_at = _serialize_history_pin(history_pin_map.get(_build_history_pin_key("task", image_id=image.id)))
        items.append({
            "history_id": None,
            "item_type": "task",
            "display_id": task_external_id(task),
            "task_id": task_external_id(task),
            "image_id": image.id,
            "user_id": user_external_id(current_user),
            "username": current_user.username if current_user else "",
            "avatar_url": (current_user.avatar_url or "") if current_user else "",
            "is_pinned": is_pinned,
            "pinned_at": pinned_at,
            "image_url": image_payload["image_url"],
            "preview_url": image_payload["preview_url"],
            "thumb_url": image_payload["thumb_url"],
            "status": _resolve_history_card_status(task.status, image.status),
            "image_format": image_payload["image_format"],
            "image_size_bytes": image_payload["image_size_bytes"],
            "task_is_deleted": False,
            "is_soft_deleted": False,
            "task_type": resolve_task_type_for_task(task, scene_type_map=scene_type_map),
            "model": task.model or "",
            "source": task.source or "web",
            "mode": task.mode or "generate",
            "prompt": task.prompt or "",
            "reference_images": [asset["image_url"] for asset in reference_assets],
            "reference_image_thumbs": [asset["thumb_url"] for asset in reference_assets],
            "source_image": source_asset["image_url"],
            "source_image_thumb": source_asset["thumb_url"],
            "mask_image": mask_asset["image_url"],
            "mask_image_thumb": mask_asset["thumb_url"],
            "num_images": task.num_images or 1,
            "size": task.size or "",
            "resolution": task.resolution or "",
            "custom_size": task.custom_size or "",
            "credit_cost": task_credit_cost,
            "credit_refunded": credit_refunded,
            "created_at": task.created_at,
            "request_started_at": task.request_started_at,
            "request_finished_at": task.request_finished_at,
            "run_time": _calculate_task_run_time(task),
            "error_message": sanitize_api_public_message(task.error_message),
            "images": visible_images,
        })

    for row in prompt_reverse_rows:
        source_asset = serialize_asset_urls(row.source_image or "", cos_config=cos_config)
        is_pinned, pinned_at = _serialize_history_pin(history_pin_map.get(_build_history_pin_key("prompt_history", history_id=row.id)))
        items.append({
            "history_id": row.id,
            "item_type": "prompt_history",
            "display_id": f"PR-{row.id}",
            "task_id": None,
            "image_id": -row.id,
            "user_id": user_external_id(current_user),
            "username": current_user.username if current_user else "",
            "avatar_url": (current_user.avatar_url or "") if current_user else "",
            "is_pinned": is_pinned,
            "pinned_at": pinned_at,
            "image_url": "",
            "preview_url": "",
            "thumb_url": "",
            "status": "success",
            "image_format": "",
            "image_size_bytes": 0,
            "task_is_deleted": False,
            "is_soft_deleted": False,
            "task_type": TASK_TYPE_PROMPT_REVERSE,
            "model": PROMPT_REVERSE_MODEL,
            "source": "web",
            "mode": PROMPT_REVERSE_MODE,
            "prompt": row.prompt or "",
            "reference_images": [],
            "reference_image_thumbs": [],
            "source_image": source_asset["image_url"],
            "source_image_thumb": source_asset["thumb_url"],
            "mask_image": "",
            "mask_image_thumb": "",
            "num_images": 0,
            "size": "-",
            "resolution": "",
            "custom_size": "",
            "credit_cost": 0,
            "created_at": row.created_at,
            "error_message": "",
            "images": [],
        })

    if respect_pins:
        items.sort(
            key=lambda item: (
                1 if item.get("is_pinned") else 0,
                item.get("pinned_at") or datetime.min,
                item.get("created_at") or datetime.min,
            ),
            reverse=True,
        )
        total = len(items)
    else:
        items.sort(key=lambda item: item.get("created_at") or datetime.min, reverse=True)
    if total is None:
        page_items = items[start_index:start_index + page_size]
        has_more = len(items) > start_index + page_size
        total = start_index + len(page_items) + (1 if has_more else 0)
        return {"total": total, "items": page_items}
    return {"total": total, "items": items[start_index:start_index + page_size]}


def delete_user_history_task(db: Session, user_id: int, task_id: str):
    normalized_task_id = normalize_business_id(task_id)
    task = (
        db.query(Task)
        .filter(
            Task.business_id == normalized_task_id,
            Task.user_id == user_id,
            Task.is_deleted.is_(False),
        )
        .first()
    )
    if not task:
        return False

    task.is_deleted = True
    db.commit()
    return True


def toggle_history_pin(
    db: Session,
    user_id: int,
    *,
    item_type: str,
    image_id: int | None = None,
    history_id: int | None = None,
):
    item_key = _build_history_pin_key(item_type, image_id=image_id, history_id=history_id)

    if item_type == "task":
        if not isinstance(image_id, int):
            raise ValueError("invalid_history_pin_target")
        image_exists = (
            db.query(Image.id)
            .join(Task, Image.task_id == Task.id)
            .filter(
                Image.id == image_id,
                Image.is_deleted.is_(False),
                Task.user_id == user_id,
                Task.is_deleted.is_(False),
            )
            .first()
        )
        if not image_exists:
            raise LookupError("history_item_not_found")
    elif item_type == "prompt_history":
        if not isinstance(history_id, int):
            raise ValueError("invalid_history_pin_target")
        prompt_history_exists = (
            db.query(PromptHistory.id)
            .filter(
                PromptHistory.id == history_id,
                PromptHistory.user_id == user_id,
                PromptHistory.mode == PROMPT_REVERSE_MODE,
            )
            .first()
        )
        if not prompt_history_exists:
            raise LookupError("history_item_not_found")
    else:
        raise ValueError("invalid_history_pin_target")

    pin = (
        db.query(HistoryPin)
        .filter(HistoryPin.user_id == user_id, HistoryPin.item_key == item_key)
        .first()
    )
    if pin:
        db.delete(pin)
        db.commit()
        return {"is_pinned": False, "pinned_at": None}

    pin = HistoryPin(
        user_id=user_id,
        item_type=item_type,
        item_key=item_key,
        image_id=image_id if item_type == "task" else None,
        history_id=history_id if item_type == "prompt_history" else None,
        pinned_at=now_local(),
    )
    db.add(pin)
    db.commit()
    db.refresh(pin)
    return {"is_pinned": True, "pinned_at": pin.pinned_at}


def get_all_history(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    user_id: Optional[int] = None,
    source: Optional[str] = None,
    model: Optional[str] = None,
    mode: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
):
    cos_config = get_optional_cos_config(db)
    scene_type_map = get_task_scene_type_map(db)
    task_query = (
        db.query(Task)
        .join(User, User.id == Task.user_id)
        .filter(User.role != "superadmin", User.is_whitelisted.is_(False))
    )
    reverse_query = (
        db.query(CreditLog)
        .join(User, User.id == CreditLog.user_id)
        .filter(
            CreditLog.type == "consume",
            CreditLog.description == PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION,
            User.role != "superadmin",
            User.is_whitelisted.is_(False),
        )
    )

    if status:
        task_query = task_query.filter(Task.status == status)
        if status != "success":
            reverse_query = reverse_query.filter(CreditLog.id.is_(None))
    if user_id:
        task_query = task_query.filter(Task.user_id == user_id)
        reverse_query = reverse_query.filter(CreditLog.user_id == user_id)
    if source:
        task_query = task_query.filter(Task.source == source)
        if source != "web":
            reverse_query = reverse_query.filter(CreditLog.id.is_(None))
    if model:
        task_query = task_query.filter(Task.model == model)
        if model != PROMPT_REVERSE_MODEL:
            reverse_query = reverse_query.filter(CreditLog.id.is_(None))
    if mode:
        if mode == TASK_TYPE_PROMPT_REVERSE:
            task_query = task_query.filter(Task.id.is_(None))
        elif mode == TASK_TYPE_INPAINT:
            task_query = task_query.filter(or_(Task.mode == "inpaint", Task.model == "inpaint"))
            reverse_query = reverse_query.filter(CreditLog.id.is_(None))
        elif mode == TASK_TYPE_TEXT_GENERATE:
            text_generate_models = [key for key, value in scene_type_map.items() if value == "generate"]
            task_query = task_query.filter(Task.mode == "generate")
            task_query = task_query.filter(Task.model.in_(text_generate_models)) if text_generate_models else task_query.filter(Task.id.is_(None))
            reverse_query = reverse_query.filter(CreditLog.id.is_(None))
        elif mode == TASK_TYPE_IMAGE_EDIT:
            image_edit_models = [key for key, value in scene_type_map.items() if value == "image_edit"]
            task_query = task_query.filter(Task.mode == "generate")
            task_query = task_query.filter(Task.model.in_(image_edit_models)) if image_edit_models else task_query.filter(Task.id.is_(None))
            reverse_query = reverse_query.filter(CreditLog.id.is_(None))
        else:
            task_query = task_query.filter(Task.mode == mode)
            if mode != PROMPT_REVERSE_MODE:
                reverse_query = reverse_query.filter(CreditLog.id.is_(None))
    if start_date:
        task_query = task_query.filter(Task.created_at >= start_date)
        reverse_query = reverse_query.filter(CreditLog.created_at >= start_date)
    if end_date:
        task_query = task_query.filter(Task.created_at <= end_date)
        reverse_query = reverse_query.filter(CreditLog.created_at <= end_date)

    tasks = task_query.order_by(Task.created_at.desc()).all()
    reverse_logs = reverse_query.order_by(CreditLog.created_at.desc()).all()
    refunded_task_ids = _get_refunded_task_ids(db, [task.id for task in tasks])
    total = len(tasks) + len(reverse_logs)
    total_credit_cost = (
        sum(0 if task.id in refunded_task_ids else int(task.credit_cost or 0) for task in tasks)
        + sum(max(0, int(-(log.amount or 0))) for log in reverse_logs)
    )

    user_cache: dict[int, dict[str, str]] = {}
    items = []
    for task in tasks:
        if task.user_id not in user_cache:
            u = db.query(User).filter(User.id == task.user_id).first()
            user_cache[task.user_id] = {
                "user_id": user_external_id(u),
                "username": u.username if u else "未知",
                "avatar_url": (u.avatar_url or "") if u else "",
            }

        soft_deleted_count = sum(1 for img in task.images if img.is_deleted)

        items.append({
            "item_type": "task",
            "task_id": task_external_id(task),
            "history_id": None,
            "display_id": task_external_id(task),
            "user_id": user_cache[task.user_id]["user_id"],
            "username": user_cache[task.user_id]["username"],
            "avatar_url": user_cache[task.user_id]["avatar_url"],
            "task_type": resolve_task_type_for_task(task, scene_type_map=scene_type_map),
            "model": task.model or "",
            "source": task.source or "web",
            "mode": task.mode or "generate",
            "prompt": task.prompt or "",
            "reference_images": _parse_refs(task.reference_images),
            "num_images": task.num_images or 1,
            "size": task.size or "",
            "resolution": task.resolution or "",
            "custom_size": task.custom_size or "",
            "credit_cost": 0 if task.id in refunded_task_ids else int(task.credit_cost or 0),
            "status": task.status,
            "error_message": sanitize_api_public_message(task.error_message),
            "task_is_deleted": bool(task.is_deleted),
            "is_soft_deleted": soft_deleted_count > 0,
            "soft_deleted_count": soft_deleted_count,
            "created_at": task.created_at,
            "images": _serialize_history_images(
                task.images,
                cos_config=cos_config,
                include_deleted=True,
            ),
        })

    for log in reverse_logs:
        if log.user_id not in user_cache:
            u = db.query(User).filter(User.id == log.user_id).first()
            user_cache[log.user_id] = {
                "user_id": user_external_id(u),
                "username": u.username if u else "未知",
                "avatar_url": (u.avatar_url or "") if u else "",
            }

        items.append({
            "item_type": "prompt_history",
            "task_id": None,
            "history_id": log.id,
            "display_id": f"PR-{log.id}",
            "user_id": user_cache[log.user_id]["user_id"],
            "username": user_cache[log.user_id]["username"],
            "avatar_url": user_cache[log.user_id]["avatar_url"],
            "task_type": TASK_TYPE_PROMPT_REVERSE,
            "model": PROMPT_REVERSE_MODEL,
            "source": "web",
            "mode": PROMPT_REVERSE_MODE,
            "prompt": "",
            "reference_images": [],
            "num_images": 0,
            "size": "-",
            "resolution": "",
            "custom_size": "",
            "credit_cost": max(0, int(-(log.amount or 0))),
            "status": "success",
            "error_message": "",
            "task_is_deleted": False,
            "is_soft_deleted": False,
            "soft_deleted_count": 0,
            "created_at": log.created_at,
            "images": [],
        })

    items.sort(key=lambda item: item["created_at"] or datetime.min, reverse=True)
    start_index = (page - 1) * page_size
    paged_items = items[start_index:start_index + page_size]

    return {"total": total, "total_credit_cost": total_credit_cost, "items": paged_items}


def get_admin_history_cards(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    *,
    include_prompt_reverse: bool = True,
    include_restricted_users: bool = False,
    include_deleted_tasks: bool = True,
    user_id: int | None = None,
    mode: str | None = None,
    source: str | None = None,
    model: str | None = None,
    prompt: str | None = None,
    status: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
):
    cos_config = get_optional_cos_config(db)
    scene_type_map = get_task_scene_type_map(db)
    running_statuses = ["pending", "queued", "processing"]
    image_query = (
        db.query(Image)
        .join(Task, Image.task_id == Task.id)
        .join(User, User.id == Task.user_id)
        .options(selectinload(Image.task).options(
            selectinload(Task.images),
            selectinload(Task.user),
            lazyload(Task.api_attempts),
        ))
        .filter(Task.is_deleted.is_(False))
        .filter(Image.is_deleted.is_(False))
    )
    running_task_query = (
        db.query(Task)
        .join(User, User.id == Task.user_id)
        .options(selectinload(Task.images), selectinload(Task.user), lazyload(Task.api_attempts))
        .filter(Task.status.in_(running_statuses))
    )
    task_without_image_query = (
        db.query(Task)
        .join(User, User.id == Task.user_id)
        .options(selectinload(Task.images), selectinload(Task.user), lazyload(Task.api_attempts))
        .filter(~Task.status.in_(running_statuses))
        .filter(~Task.images.any(Image.is_deleted.is_(False)))
    )
    if not include_restricted_users:
        image_query = image_query.filter(User.role != "superadmin", User.is_whitelisted.is_(False))
        running_task_query = running_task_query.filter(User.role != "superadmin", User.is_whitelisted.is_(False))
        task_without_image_query = task_without_image_query.filter(User.role != "superadmin", User.is_whitelisted.is_(False))
    if not include_deleted_tasks:
        image_query = image_query.filter(Task.is_deleted.is_(False))
        running_task_query = running_task_query.filter(Task.is_deleted.is_(False))
        task_without_image_query = task_without_image_query.filter(Task.is_deleted.is_(False))
    prompt_reverse_query = None
    if include_prompt_reverse:
        prompt_reverse_query = (
            db.query(PromptHistory)
            .join(User, User.id == PromptHistory.user_id)
            .filter(
                PromptHistory.mode == PROMPT_REVERSE_MODE,
            )
        )
        if not include_restricted_users:
            prompt_reverse_query = prompt_reverse_query.filter(User.role != "superadmin", User.is_whitelisted.is_(False))

    if user_id is not None:
        image_query = image_query.filter(Task.user_id == user_id)
        running_task_query = running_task_query.filter(Task.user_id == user_id)
        task_without_image_query = task_without_image_query.filter(Task.user_id == user_id)
        if prompt_reverse_query is not None:
            prompt_reverse_query = prompt_reverse_query.filter(PromptHistory.user_id == user_id)
    if mode:
        if mode == TASK_TYPE_PROMPT_REVERSE:
            image_query = image_query.filter(Task.id.is_(None))
            running_task_query = running_task_query.filter(Task.id.is_(None))
            task_without_image_query = task_without_image_query.filter(Task.id.is_(None))
        elif mode == TASK_TYPE_INPAINT:
            image_query = image_query.filter(or_(Task.mode == "inpaint", Task.model == "inpaint"))
            running_task_query = running_task_query.filter(or_(Task.mode == "inpaint", Task.model == "inpaint"))
            task_without_image_query = task_without_image_query.filter(or_(Task.mode == "inpaint", Task.model == "inpaint"))
            prompt_reverse_query = None
        elif mode == TASK_TYPE_TEXT_GENERATE:
            text_generate_models = [key for key, value in scene_type_map.items() if value == "generate"]
            image_query = image_query.filter(Task.mode == "generate")
            image_query = image_query.filter(Task.model.in_(text_generate_models)) if text_generate_models else image_query.filter(Task.id.is_(None))
            running_task_query = running_task_query.filter(Task.mode == "generate")
            running_task_query = running_task_query.filter(Task.model.in_(text_generate_models)) if text_generate_models else running_task_query.filter(Task.id.is_(None))
            task_without_image_query = task_without_image_query.filter(Task.mode == "generate")
            task_without_image_query = task_without_image_query.filter(Task.model.in_(text_generate_models)) if text_generate_models else task_without_image_query.filter(Task.id.is_(None))
            prompt_reverse_query = None
        elif mode == TASK_TYPE_IMAGE_EDIT:
            image_edit_models = [key for key, value in scene_type_map.items() if value == "image_edit"]
            image_query = image_query.filter(Task.mode == "generate")
            image_query = image_query.filter(Task.model.in_(image_edit_models)) if image_edit_models else image_query.filter(Task.id.is_(None))
            running_task_query = running_task_query.filter(Task.mode == "generate")
            running_task_query = running_task_query.filter(Task.model.in_(image_edit_models)) if image_edit_models else running_task_query.filter(Task.id.is_(None))
            task_without_image_query = task_without_image_query.filter(Task.mode == "generate")
            task_without_image_query = task_without_image_query.filter(Task.model.in_(image_edit_models)) if image_edit_models else task_without_image_query.filter(Task.id.is_(None))
            prompt_reverse_query = None
        else:
            image_query = image_query.filter(Task.mode == mode)
            running_task_query = running_task_query.filter(Task.mode == mode)
            task_without_image_query = task_without_image_query.filter(Task.mode == mode)
            if mode != PROMPT_REVERSE_MODE:
                prompt_reverse_query = None
    if source:
        image_query = image_query.filter(Task.source == source)
        running_task_query = running_task_query.filter(Task.source == source)
        task_without_image_query = task_without_image_query.filter(Task.source == source)
        if source != "web":
            prompt_reverse_query = None
    if model:
        image_query = image_query.filter(Task.model == model)
        running_task_query = running_task_query.filter(Task.model == model)
        task_without_image_query = task_without_image_query.filter(Task.model == model)
        if model != PROMPT_REVERSE_MODEL:
            prompt_reverse_query = None
    if prompt:
        keyword = prompt.strip()
        if keyword:
            image_query = image_query.filter(Task.prompt.ilike(f"%{keyword}%"))
            running_task_query = running_task_query.filter(Task.prompt.ilike(f"%{keyword}%"))
            task_without_image_query = task_without_image_query.filter(Task.prompt.ilike(f"%{keyword}%"))
            if prompt_reverse_query is not None:
                prompt_reverse_query = prompt_reverse_query.filter(PromptHistory.prompt.ilike(f"%{keyword}%"))
    if status:
        if status == "processing":
            image_query = image_query.filter(Task.id.is_(None))
            running_task_query = running_task_query.filter(Task.status == "processing")
            task_without_image_query = task_without_image_query.filter(Task.status == "processing")
            prompt_reverse_query = None
        elif status == "pending":
            image_query = image_query.filter(Task.id.is_(None))
            running_task_query = running_task_query.filter(Task.status.in_(["pending", "queued"]))
            task_without_image_query = task_without_image_query.filter(Task.status.in_(["pending", "queued"]))
            prompt_reverse_query = None
        elif status == "failed":
            image_query = image_query.filter(or_(Image.status == "failed", and_(Image.status == "pending", Task.status == "failed")))
            running_task_query = running_task_query.filter(Task.id.is_(None))
            task_without_image_query = task_without_image_query.filter(Task.status == "failed")
            prompt_reverse_query = None
        else:
            image_query = image_query.filter(Image.status == status)
            running_task_query = running_task_query.filter(Task.id.is_(None))
            task_without_image_query = task_without_image_query.filter(Task.status == status)
    else:
        image_query = image_query.filter(~Task.status.in_(running_statuses))
    if start_date:
        image_query = image_query.filter(Task.created_at >= start_date)
        running_task_query = running_task_query.filter(Task.created_at >= start_date)
        task_without_image_query = task_without_image_query.filter(Task.created_at >= start_date)
        if prompt_reverse_query is not None:
            prompt_reverse_query = prompt_reverse_query.filter(PromptHistory.created_at >= start_date)
    if end_date:
        image_query = image_query.filter(Task.created_at <= end_date)
        running_task_query = running_task_query.filter(Task.created_at <= end_date)
        task_without_image_query = task_without_image_query.filter(Task.created_at <= end_date)
        if prompt_reverse_query is not None:
            prompt_reverse_query = prompt_reverse_query.filter(PromptHistory.created_at <= end_date)

    start_index = (page - 1) * page_size
    fetch_limit = start_index + page_size + 1
    images = (
        image_query
        .order_by(Task.created_at.desc(), Image.id.desc())
        .limit(fetch_limit)
        .all()
    )
    running_tasks = (
        running_task_query
        .order_by(Task.created_at.desc(), Task.id.desc())
        .limit(fetch_limit)
        .all()
    )
    tasks_without_images = (
        task_without_image_query
        .order_by(Task.created_at.desc(), Task.id.desc())
        .limit(fetch_limit)
        .all()
    )
    prompt_reverse_rows = (
        prompt_reverse_query
        .order_by(PromptHistory.created_at.desc(), PromptHistory.id.desc())
        .limit(fetch_limit)
        .all()
        if prompt_reverse_query is not None
        else []
    )

    user_ids = (
        {image.task.user_id for image in images if image.task}
        | {task.user_id for task in running_tasks}
        | {task.user_id for task in tasks_without_images}
        | {row.user_id for row in prompt_reverse_rows}
    )
    user_cache = {
        user.id: user
        for user in db.query(User).filter(User.id.in_(user_ids)).all()
    } if user_ids else {}
    items = []
    for image in images:
        task = image.task
        task_user = user_cache.get(task.user_id) if task else None
        task_credit_cost = int(task.credit_cost or 0) if task else 0
        credit_refunded = False
        if task and task.status == "failed" and task_credit_cost > 0:
            credit_refunded = is_task_generation_failure_credit_refunded(db, task.id)
        image_payload = serialize_image(image, cos_config=cos_config)
        source_asset = serialize_asset_urls(task.source_image or "", cos_config=cos_config)
        mask_asset = serialize_asset_urls(task.mask_image or "", cos_config=cos_config)
        reference_assets = [serialize_asset_urls(ref, cos_config=cos_config) for ref in _parse_refs(task.reference_images)]
        visible_images = _serialize_history_images(task.images, cos_config=cos_config)
        items.append({
            "history_id": None,
            "item_type": "task",
            "display_id": task_external_id(task),
            "task_id": task_external_id(task),
            "image_id": image.id,
            "user_id": user_external_id(task_user),
            "username": task_user.username if task_user else "",
            "avatar_url": (task_user.avatar_url or "") if task_user else "",
            "is_pinned": False,
            "pinned_at": None,
            "image_url": image_payload["image_url"],
            "preview_url": image_payload["preview_url"],
            "thumb_url": image_payload["thumb_url"],
            "status": _resolve_history_card_status(task.status, image.status),
            "image_format": image_payload["image_format"],
            "image_size_bytes": image_payload["image_size_bytes"],
            "task_is_deleted": False,
            "is_soft_deleted": False,
            "task_type": resolve_task_type_for_task(task, scene_type_map=scene_type_map),
            "model": task.model or "",
            "source": task.source or "web",
            "mode": task.mode or "generate",
            "prompt": task.prompt or "",
            "reference_images": [asset["image_url"] for asset in reference_assets],
            "reference_image_thumbs": [asset["thumb_url"] for asset in reference_assets],
            "source_image": source_asset["image_url"],
            "source_image_thumb": source_asset["thumb_url"],
            "mask_image": mask_asset["image_url"],
            "mask_image_thumb": mask_asset["thumb_url"],
            "num_images": task.num_images or 1,
            "size": task.size or "",
            "resolution": task.resolution or "",
            "custom_size": task.custom_size or "",
            "credit_cost": task_credit_cost,
            "credit_refunded": credit_refunded,
            "created_at": task.created_at,
            "error_message": sanitize_api_public_message(task.error_message),
            "images": visible_images,
        })

    for task in running_tasks:
        task_user = user_cache.get(task.user_id)
        source_asset = serialize_asset_urls(task.source_image or "", cos_config=cos_config)
        mask_asset = serialize_asset_urls(task.mask_image or "", cos_config=cos_config)
        reference_assets = [serialize_asset_urls(ref, cos_config=cos_config) for ref in _parse_refs(task.reference_images)]
        visible_images = _serialize_history_images(task.images, cos_config=cos_config)
        primary_image = next((image for image in visible_images if not image.get("is_deleted")), None)
        items.append({
            "history_id": None,
            "item_type": "task",
            "display_id": task_external_id(task),
            "task_id": task_external_id(task),
            "image_id": primary_image["id"] if primary_image else None,
            "user_id": user_external_id(task_user),
            "username": task_user.username if task_user else "",
            "avatar_url": (task_user.avatar_url or "") if task_user else "",
            "is_pinned": False,
            "pinned_at": None,
            "image_url": primary_image["image_url"] if primary_image else "",
            "preview_url": primary_image["preview_url"] if primary_image else "",
            "thumb_url": primary_image["thumb_url"] if primary_image else "",
            "status": task.status or "pending",
            "image_format": primary_image["image_format"] if primary_image else "",
            "image_size_bytes": primary_image["image_size_bytes"] if primary_image else 0,
            "task_is_deleted": False,
            "is_soft_deleted": False,
            "task_type": resolve_task_type_for_task(task, scene_type_map=scene_type_map),
            "model": task.model or "",
            "source": task.source or "web",
            "mode": task.mode or "generate",
            "prompt": task.prompt or "",
            "reference_images": [asset["image_url"] for asset in reference_assets],
            "reference_image_thumbs": [asset["thumb_url"] for asset in reference_assets],
            "source_image": source_asset["image_url"],
            "source_image_thumb": source_asset["thumb_url"],
            "mask_image": mask_asset["image_url"],
            "mask_image_thumb": mask_asset["thumb_url"],
            "num_images": task.num_images or 1,
            "size": task.size or "",
            "resolution": task.resolution or "",
            "custom_size": task.custom_size or "",
            "credit_cost": int(task.credit_cost or 0),
            "credit_refunded": False,
            "created_at": task.created_at,
            "request_started_at": task.request_started_at,
            "request_finished_at": task.request_finished_at,
            "run_time": _calculate_task_run_time(task),
            "error_message": sanitize_api_public_message(task.error_message),
            "images": visible_images,
        })

    for task in tasks_without_images:
        task_user = user_cache.get(task.user_id)
        task_credit_cost = int(task.credit_cost or 0)
        credit_refunded = False
        if task.status == "failed" and task_credit_cost > 0:
            credit_refunded = is_task_generation_failure_credit_refunded(db, task.id)
        source_asset = serialize_asset_urls(task.source_image or "", cos_config=cos_config)
        mask_asset = serialize_asset_urls(task.mask_image or "", cos_config=cos_config)
        reference_assets = [serialize_asset_urls(ref, cos_config=cos_config) for ref in _parse_refs(task.reference_images)]
        items.append({
            "history_id": None,
            "item_type": "task",
            "display_id": task_external_id(task),
            "task_id": task_external_id(task),
            "image_id": None,
            "user_id": user_external_id(task_user),
            "username": task_user.username if task_user else "",
            "avatar_url": (task_user.avatar_url or "") if task_user else "",
            "is_pinned": False,
            "pinned_at": None,
            "image_url": "",
            "preview_url": "",
            "thumb_url": "",
            "status": task.status or "pending",
            "image_format": "",
            "image_size_bytes": 0,
            "task_is_deleted": False,
            "is_soft_deleted": False,
            "task_type": resolve_task_type_for_task(task, scene_type_map=scene_type_map),
            "model": task.model or "",
            "source": task.source or "web",
            "mode": task.mode or "generate",
            "prompt": task.prompt or "",
            "reference_images": [asset["image_url"] for asset in reference_assets],
            "reference_image_thumbs": [asset["thumb_url"] for asset in reference_assets],
            "source_image": source_asset["image_url"],
            "source_image_thumb": source_asset["thumb_url"],
            "mask_image": mask_asset["image_url"],
            "mask_image_thumb": mask_asset["thumb_url"],
            "num_images": task.num_images or 1,
            "size": task.size or "",
            "resolution": task.resolution or "",
            "custom_size": task.custom_size or "",
            "credit_cost": task_credit_cost,
            "credit_refunded": credit_refunded,
            "created_at": task.created_at,
            "request_started_at": task.request_started_at,
            "request_finished_at": task.request_finished_at,
            "run_time": _calculate_task_run_time(task),
            "error_message": sanitize_api_public_message(task.error_message),
            "images": [],
        })

    for row in prompt_reverse_rows:
        row_user = user_cache.get(row.user_id)
        source_asset = serialize_asset_urls(row.source_image or "", cos_config=cos_config)
        items.append({
            "history_id": row.id,
            "item_type": "prompt_history",
            "display_id": f"PR-{row.id}",
            "task_id": None,
            "image_id": -row.id,
            "user_id": user_external_id(row_user),
            "username": row_user.username if row_user else "",
            "avatar_url": (row_user.avatar_url or "") if row_user else "",
            "is_pinned": False,
            "pinned_at": None,
            "image_url": "",
            "preview_url": "",
            "thumb_url": "",
            "status": "success",
            "image_format": "",
            "image_size_bytes": 0,
            "task_is_deleted": False,
            "is_soft_deleted": False,
            "task_type": TASK_TYPE_PROMPT_REVERSE,
            "model": PROMPT_REVERSE_MODEL,
            "source": "web",
            "mode": PROMPT_REVERSE_MODE,
            "prompt": row.prompt or "",
            "reference_images": [],
            "reference_image_thumbs": [],
            "source_image": source_asset["image_url"],
            "source_image_thumb": source_asset["thumb_url"],
            "mask_image": "",
            "mask_image_thumb": "",
            "num_images": 0,
            "size": "-",
            "resolution": "",
            "custom_size": "",
            "credit_cost": 0,
            "created_at": row.created_at,
            "error_message": "",
            "images": [],
        })

    items.sort(key=lambda item: item.get("created_at") or datetime.min, reverse=True)
    page_items = items[start_index:start_index + page_size]
    has_more = len(items) > start_index + page_size
    total = start_index + len(page_items) + (1 if has_more else 0)
    return {"total": total, "items": page_items}


def get_admin_history_detail(
    db: Session,
    *,
    item_type: str,
    task_id: str | None = None,
    history_id: int | None = None,
):
    cos_config = get_optional_cos_config(db)
    scene_type_map = get_task_scene_type_map(db)
    if item_type == "task":
        normalized_task_id = normalize_business_id(task_id)
        if not normalized_task_id:
            raise ValueError("invalid_task_id")
        # 按精确 task_id 查询时不排除白名单/超管用户，便于反馈等场景回看关联任务。
        task = (
            db.query(Task)
            .options(selectinload(Task.images), selectinload(Task.user))
            .filter(Task.business_id == normalized_task_id)
            .first()
        )
        if not task:
            raise LookupError("task_not_found")
        return _serialize_task_history_detail(task, cos_config=cos_config, scene_type_map=scene_type_map)

    if item_type == "prompt_history":
        if not isinstance(history_id, int):
            raise ValueError("invalid_history_id")
        row = (
            db.query(PromptHistory)
            .filter(
                PromptHistory.id == history_id,
                PromptHistory.mode == PROMPT_REVERSE_MODE,
            )
            .first()
        )
        if not row:
            raise LookupError("prompt_history_not_found")
        return _serialize_prompt_history_detail(row, cos_config=cos_config)

    raise ValueError("invalid_item_type")
