import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.task import TaskCreate, TaskCreateResponse, TaskOut
from app.services.image_delivery_service import get_optional_cos_config, serialize_task
from app.services.business_id_service import task_external_id, user_external_id
from app.services.external_api_config_service import (
    get_default_generation_model_key,
    require_scene_config,
    SCENE_INPAINT,
    SCENE_SMART_CUTOUT,
)
from app.services.task_service import (
    create_tasks,
    get_task_detail,
    get_task_details,
    mark_tasks_dispatched,
    mark_tasks_enqueue_failed,
    mark_tasks_queued,
)
from app.services.failure_refund_service import get_current_failure_refund_remaining_count

router = APIRouter(prefix="/api/tasks", tags=["生成任务"])
task_logger = logging.getLogger("app.task")


@router.post("", response_model=TaskCreateResponse)
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
            "task_count": body.num_images,
            "prompt_length": len((body.prompt or "").strip()),
        },
    )
    if body.mode == "inpaint":
        require_scene_config(db, SCENE_INPAINT)
        task_model = SCENE_INPAINT
        resolved_resolution = body.resolution
    elif body.mode == "smart_cutout":
        require_scene_config(db, SCENE_SMART_CUTOUT)
        task_model = SCENE_SMART_CUTOUT
        resolved_resolution = body.resolution
    else:
        task_model = body.model.strip() or get_default_generation_model_key(db)
        require_scene_config(db, task_model)
        resolved_resolution = "" if task_model == "banana" else body.resolution

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

    tasks = create_tasks(
        db,
        user_id=user.id,
        model=task_model,
        source=body.source,
        mode=body.mode,
        prompt=body.prompt,
        num_images=body.num_images,
        size=body.size,
        resolution=resolved_resolution,
        custom_size=body.custom_size,
        reference_images=body.reference_images,
        source_image=body.source_image,
        mask_image=body.mask_image,
        board_id=body.board_id,
    )

    dispatched_task_ids: list[int] = []
    try:
        for task in tasks:
            actual_dispatch_mode = dispatch_generation_task(task.id)
            dispatched_task_ids.append(task.id)
            task_logger.info(
                "task dispatched",
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
            "task dispatch failed",
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
        "task create request completed",
        extra={
            "event": "task.api.completed",
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
    failure_refund_remaining_count = (
        get_current_failure_refund_remaining_count(db, user.id)
        if task.status == "failed" and int(task.credit_cost or 0) > 0
        else None
    )
    return serialize_task(
        task,
        cos_config=get_optional_cos_config(db),
        failure_refund_remaining_count=failure_refund_remaining_count,
    )


@router.get("", response_model=list[TaskOut])
def get_tasks(
    task_ids: list[str] = Query(default=[]),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tasks = get_task_details(db, task_ids, user.id)
    cos_config = get_optional_cos_config(db)
    failure_refund_remaining_count = (
        get_current_failure_refund_remaining_count(db, user.id)
        if any(task.status == "failed" and int(task.credit_cost or 0) > 0 for task in tasks)
        else None
    )
    return [
        serialize_task(
            task,
            cos_config=cos_config,
            failure_refund_remaining_count=(
                failure_refund_remaining_count
                if task.status == "failed" and int(task.credit_cost or 0) > 0
                else None
            ),
        )
        for task in tasks
    ]
