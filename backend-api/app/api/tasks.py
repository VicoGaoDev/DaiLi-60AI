import logging
import re
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.task import TaskCreate, TaskCreateResponse, TaskOut
from app.services.image_delivery_service import (
    get_optional_cos_config,
    sanitize_api_public_message,
    serialize_task,
)
from app.services.business_id_service import task_external_id, user_external_id
from app.services.external_api_config_service import require_scene_config
from app.services.cos_service import build_object_key, load_image_bytes, upload_bytes_to_cos
from app.services.task_service import (
    create_tasks,
    get_task_detail,
    get_task_details,
    mark_tasks_dispatched,
    mark_tasks_enqueue_failed,
    mark_tasks_queued,
)

router = APIRouter(prefix="/api/tasks", tags=["生成任务"])
task_logger = logging.getLogger("app.task")
BASE64_IMAGE_PATTERN = re.compile(
    r"^(?:data:image/(?:png|jpe?g|gif|webp);base64,)?[A-Za-z0-9+/=\s]+$",
    re.I,
)
API_GENERATE_MODELS = frozenset(
    {
        "gptimage25_flare_high",
        "gptimage25_sunburst_high",
        "gptimage2_high",
        "gptimage2_medium",
        "gptimage2_low",
        "banana_pro",
        "banana2",
        "banana",
    }
)
API_EDIT_MODELS = frozenset(
    {
        "gptimage25_flare_high_edit",
        "gptimage25_sunburst_high_edit",
        "gptimage2_high_edit",
        "gptimage2_medium_edit",
        "gptimage2_low_edit",
        "banana_pro_edit",
        "banana2_edit",
        "banana_edit",
    }
)
REFERENCE_IMAGE_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _validate_base64_image(value: str, field_name: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return ""
    if not BASE64_IMAGE_PATTERN.fullmatch(normalized) or len(normalized) <= 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} 必须是图片 base64 或 data URL")
    return normalized


def _normalize_base64_images(values: list[str] | None) -> list[str]:
    normalized_images: list[str] = []
    for index, value in enumerate(values or []):
        normalized = _validate_base64_image(value, f"reference_images[{index}]")
        if normalized:
            normalized_images.append(normalized)
    return normalized_images


def _model_requires_reference_images(model: str) -> bool:
    return "edit" in (model or "").strip().lower()


def _resolve_api_task_model(model: str, reference_images: list[str]) -> str:
    task_model = (model or "").strip()
    if not task_model:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="model 不能为空")
    has_reference_images = bool(reference_images)
    if _model_requires_reference_images(task_model) and not has_reference_images:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="图编辑须传入 reference_images",
        )
    allowed = API_EDIT_MODELS if has_reference_images else API_GENERATE_MODELS
    if task_model not in allowed:
        kind = "图编辑" if has_reference_images else "文生图"
        options = "、".join(sorted(allowed))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{kind} model 无效，可选值：{options}",
        )
    return task_model


def _validate_api_generation_request(body: TaskCreate) -> tuple[list[str], str, str]:
    if (body.mode or "generate").strip().lower() != "generate":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="暂不开放局部重绘 API")
    reference_images = _normalize_base64_images(body.reference_images)
    task_model = _resolve_api_task_model(body.model, reference_images)
    resolved_resolution = "" if task_model == "banana" else body.resolution
    return reference_images, task_model, resolved_resolution


def _build_api_task_create_kwargs(
    body: TaskCreate,
    *,
    task_model: str,
    resolved_resolution: str,
    reference_images: list[str],
) -> dict:
    return {
        "model": task_model,
        "source": "api",
        "mode": body.mode,
        "prompt": body.prompt,
        "num_images": 1,
        "size": body.size,
        "resolution": resolved_resolution,
        "custom_size": body.custom_size,
        "reference_images": reference_images,
        "source_image": "",
        "mask_image": "",
        "board_id": body.board_id,
    }


def _persist_reference_images_for_async(db: Session, reference_images: list[str]) -> list[str]:
    persisted_urls: list[str] = []
    for index, reference_image in enumerate(reference_images, start=1):
        loaded = load_image_bytes(reference_image)
        if not loaded:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"reference_images[{index - 1}] 图片解析失败",
            )
        image_bytes, mime_type = loaded
        normalized_mime_type = (mime_type or "image/png").split(";")[0].strip().lower()
        extension = REFERENCE_IMAGE_EXTENSIONS.get(normalized_mime_type, "png")
        object_key = build_object_key("ref", f"api-reference-{index}.{extension}", normalized_mime_type)
        persisted_urls.append(
            upload_bytes_to_cos(
                db,
                data=image_bytes,
                key=object_key,
                content_type=normalized_mime_type,
            )
        )
    return persisted_urls


@router.post("", response_model=list[TaskOut])
def create(
    body: TaskCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task_logger.info(
        "task create request received",
        extra={
            "event": "task.api.received",
            "user_id": user_external_id(user),
            "mode": body.mode,
            "model": body.model.strip(),
            "task_count": 1,
            "prompt_length": len((body.prompt or "").strip()),
        },
    )
    reference_images, task_model, resolved_resolution = _validate_api_generation_request(body)
    require_scene_config(db, task_model)
    persisted_reference_images = _persist_reference_images_for_async(db, reference_images)
    task_create_kwargs = _build_api_task_create_kwargs(
        body,
        task_model=task_model,
        resolved_resolution=resolved_resolution,
        reference_images=persisted_reference_images,
    )
    tasks = create_tasks(
        db,
        user_id=user.id,
        **task_create_kwargs,
    )

    from app.workers.generation import _process_task

    try:
        for task in tasks:
            _process_task(task.id, use_distributed_lock=False)
    except Exception as exc:
        task_logger.exception(
            "sync task processing failed",
            extra={
                "event": "task.sync.exception",
                "user_id": user_external_id(user),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=sanitize_api_public_message(f"任务同步处理失败：{exc}"),
        ) from exc

    task_logger.info(
        "sync task request completed",
        extra={
            "event": "task.api.sync_completed",
            "user_id": user_external_id(user),
            "task_count": len(tasks),
            "mode": body.mode,
            "model": task_model,
        },
    )
    for task in tasks:
        db.refresh(task)
    cos_config = get_optional_cos_config(db)
    return [serialize_task(task, cos_config=cos_config) for task in tasks]


@router.post("/submit", response_model=TaskCreateResponse)
def submit(
    body: TaskCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task_logger.info(
        "async task submit request received",
        extra={
            "event": "task.api.submit.received",
            "user_id": user_external_id(user),
            "mode": body.mode,
            "model": body.model.strip(),
            "task_count": 1,
            "prompt_length": len((body.prompt or "").strip()),
        },
    )
    reference_images, task_model, resolved_resolution = _validate_api_generation_request(body)
    require_scene_config(db, task_model)
    persisted_reference_images = _persist_reference_images_for_async(db, reference_images)

    try:
        from app.workers.generation import dispatch_generation_task, get_generation_dispatch_mode
        dispatch_mode = get_generation_dispatch_mode()
    except RuntimeError as exc:
        task_logger.error(
            "task dispatch mode unavailable",
            extra={
                "event": "task.dispatch.mode_unavailable",
                "user_id": user_external_id(user),
                "mode": body.mode,
                "model": task_model,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    task_create_kwargs = _build_api_task_create_kwargs(
        body,
        task_model=task_model,
        resolved_resolution=resolved_resolution,
        reference_images=persisted_reference_images,
    )
    tasks = create_tasks(
        db,
        user_id=user.id,
        **task_create_kwargs,
    )

    dispatched_task_ids: list[int] = []
    try:
        for task in tasks:
            actual_dispatch_mode = dispatch_generation_task(task.id)
            dispatched_task_ids.append(task.id)
            task_logger.info(
                "async task dispatched",
                extra={
                    "event": "task.dispatch.sent",
                    "user_id": user_external_id(user),
                    "task_id": task_external_id(task),
                    "dispatch_mode": actual_dispatch_mode,
                    "mode": body.mode,
                    "model": task_model,
                },
            )
        mark_tasks_dispatched(db, dispatched_task_ids)
        if dispatch_mode == "celery":
            mark_tasks_queued(db, dispatched_task_ids)
    except Exception as exc:
        failed_task_ids = [task.id for task in tasks if task.id not in set(dispatched_task_ids)]
        mark_tasks_enqueue_failed(db, failed_task_ids, error_message=str(exc))
        task_logger.exception(
            "async task dispatch failed",
            extra={
                "event": "task.dispatch.exception",
                "user_id": user_external_id(user),
                "task_ids": [task_external_id(task) for task in tasks if task.id in set(failed_task_ids)],
                "dispatch_mode": dispatch_mode,
            },
        )
        if dispatched_task_ids:
            task_ids = [task_external_id(task) for task in tasks]
            return TaskCreateResponse(task_id=task_ids[0] if task_ids else None, task_ids=task_ids)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="任务队列暂不可用，请稍后重试",
        ) from exc

    task_ids = [task_external_id(task) for task in tasks]
    task_logger.info(
        "async task submit request completed",
        extra={
            "event": "task.api.submit.completed",
            "user_id": user_external_id(user),
            "task_ids": task_ids,
            "task_count": len(task_ids),
            "dispatch_mode": dispatch_mode,
            "mode": body.mode,
            "model": task_model,
        },
    )
    return TaskCreateResponse(task_id=task_ids[0] if task_ids else None, task_ids=task_ids)


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = get_task_detail(db, task_id, user.id)
    return serialize_task(task, cos_config=get_optional_cos_config(db))


@router.get("", response_model=list[TaskOut])
def get_tasks(
    task_ids: list[str] = Query(default=[]),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tasks = get_task_details(db, task_ids, user.id)
    cos_config = get_optional_cos_config(db)
    return [serialize_task(task, cos_config=cos_config) for task in tasks]
