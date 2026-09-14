import logging

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.video_task import VideoTaskCreate, VideoTaskCreateResponse, VideoTaskOut
from app.services.image_delivery_service import get_optional_cos_config
from app.services.failure_refund_service import get_current_failure_refund_remaining_count
from app.services.video_external_api_config_service import require_video_scene_config
from app.services.video_task_service import (
    create_video_task,
    delete_video_task,
    expire_stale_video_tasks,
    get_video_task_detail,
    get_video_task_details,
    list_recent_video_tasks,
    mark_video_tasks_dispatched,
    mark_video_tasks_enqueue_failed,
    mark_video_tasks_queued,
    serialize_video_task,
)

router = APIRouter(prefix="/api/video-tasks", tags=["视频任务"])
video_task_logger = logging.getLogger("app.video_task")


@router.post("/submit", response_model=VideoTaskCreateResponse)
def submit_video_task(
    body: VideoTaskCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task_model = (body.model or "").strip()
    if not task_model:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="model 不能为空")
    require_video_scene_config(db, task_model)
    from app.workers.video_generation import dispatch_video_generation_task

    task = create_video_task(
        db,
        user_id=user.id,
        model=task_model,
        source=body.source,
        generation_mode=body.generation_mode,
        prompt=body.prompt,
        duration_seconds=body.duration_seconds,
        aspect_ratio=body.aspect_ratio,
        resolution=body.resolution,
        reference_images=body.reference_images,
    )
    try:
        dispatch_mode = dispatch_video_generation_task(task.id)
    except Exception as exc:
        mark_video_tasks_enqueue_failed(db, [task.id], error_message=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="视频任务队列暂不可用，请稍后重试",
        ) from exc
    try:
        mark_video_tasks_dispatched(db, [task.id])
        mark_video_tasks_queued(db, [task.id])
    except Exception:
        video_task_logger.exception(
            "video task bookkeeping update failed after dispatch",
            extra={
                "event": "video_task.dispatch.bookkeeping_failed",
                "user_id": user.business_id,
                "task_id": task.business_id,
            },
        )
    video_task_logger.info(
        "video task dispatched",
        extra={
            "event": "video_task.dispatch.sent",
            "user_id": user.business_id,
            "task_id": task.business_id,
            "dispatch_mode": dispatch_mode,
        },
    )
    return VideoTaskCreateResponse(task_id=task.business_id)


@router.get("/{task_id}", response_model=VideoTaskOut)
def get_video_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    expire_stale_video_tasks(db, user_id=user.id)
    task = get_video_task_detail(db, task_id, user.id)
    failure_refund_remaining_count = (
        get_current_failure_refund_remaining_count(db, user.id)
        if task.status == "failed" and int(task.credit_cost or 0) > 0
        else None
    )
    return serialize_video_task(
        task,
        cos_config=get_optional_cos_config(db),
        failure_refund_remaining_count=failure_refund_remaining_count,
        public_error_message=True,
    )


@router.get("", response_model=list[VideoTaskOut])
def get_video_tasks(
    task_ids: list[str] = Query(default=[]),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    expire_stale_video_tasks(db, user_id=user.id)
    if task_ids:
        tasks = get_video_task_details(db, task_ids, user.id)
    else:
        tasks = list_recent_video_tasks(db, user.id, limit=limit)
    cos_config = get_optional_cos_config(db)
    failure_refund_remaining_count = (
        get_current_failure_refund_remaining_count(db, user.id)
        if any(task.status == "failed" and int(task.credit_cost or 0) > 0 for task in tasks)
        else None
    )
    return [
        serialize_video_task(
            task,
            cos_config=cos_config,
            failure_refund_remaining_count=(
                failure_refund_remaining_count
                if task.status == "failed" and int(task.credit_cost or 0) > 0
                else None
            ),
            public_error_message=True,
        )
        for task in tasks
    ]


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_video_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not delete_video_task(db, user.id, task_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="视频任务不存在")
    return None
