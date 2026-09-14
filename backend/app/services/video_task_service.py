from __future__ import annotations

import json
import logging
import re
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models.credit_log import CreditLog
from app.models.user import User
from app.models.video_result import VideoResult
from app.models.video_task import VideoTask
from app.services.business_id_service import user_external_id
from app.services.content_safety_service import build_exclude_content_safety_failed_task_clause
from app.services.failure_refund_service import (
    DAILY_FAILURE_REFUND_LIMIT,
    get_today_failure_refund_count,
)
from app.services.image_delivery_service import get_optional_cos_config, normalize_external_image_url, resolve_user_avatar_url
from app.services.user_credit_service import apply_user_credit_delta, get_user_credit_account
from app.services.video_external_api_config_service import (
    VIDEO_SCENE_AVAILABILITY_FIRST_LAST,
    VIDEO_SCENE_AVAILABILITY_IMAGE,
    VIDEO_SCENE_AVAILABILITY_TEXT,
    get_video_scene_credit_cost,
    get_video_scene_max_reference_images,
    is_video_scene_available_for_task_mode,
    normalize_video_generation_mode,
)
from app.utils.business_id import normalize_business_id
from app.utils.datetime_utils import now_local


ACTIVE_VIDEO_TASK_STATUSES = ("pending", "queued", "processing")
VIDEO_TASK_PROMPT_MAX_LENGTH = 5000
VIDEO_TASK_MAX_REFERENCE_IMAGES = 6
VIDEO_TASK_ENQUEUE_REFUND_PREFIX = "AI视频任务入队失败返还"
VIDEO_TASK_FAILURE_REFUND_PREFIX = "AI视频任务失败返还"
VIDEO_TASK_CONSUME_PREFIX = "AI视频生成"
VIDEO_TASK_SAFETY_ERROR_MESSAGE = "生成的视频存在安全风险（色情、暴力、版权、政治敏感等），请尝试修改提示词或参考图，或换个模型尝试（不同模型审查尺度不同）！"
VIDEO_TASK_INVALID_ASPECT_RATIO_MESSAGE = "当前宽高比不受支持，请更换其他宽高比后重试"
VIDEO_TASK_FAILURE_MESSAGE = "生成视频失败，请反馈给我们处理"
VIDEO_TASK_SAFETY_ERROR_PATTERN = re.compile(
    r"unsafe|image_unsafe|content blocked|appear to be unsafe|safety|nsfw|敏感|违规|审核拒绝|内容安全",
    re.IGNORECASE,
)
VIDEO_TASK_INVALID_ASPECT_RATIO_PATTERN = re.compile(
    r"n?put\.aspect_ratio is invalid|aspect_ratio is invalid",
    re.IGNORECASE,
)
video_task_logger = logging.getLogger("app.video_task")


def _is_credit_exempt_user(user: User | None) -> bool:
    return bool(user and user.role == "superadmin")


def _refund_description(prefix: str, task: VideoTask) -> str:
    return f"{prefix} {task.business_id}"


def _parse_reference_images(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [normalize_external_image_url(item) for item in parsed if normalize_external_image_url(item)]


def is_video_task_credit_refunded(db: Session, task: VideoTask) -> bool:
    return (
        db.query(CreditLog.id)
        .filter(
            CreditLog.user_id == task.user_id,
            CreditLog.type == "allocate",
            CreditLog.description.in_([
                _refund_description(VIDEO_TASK_ENQUEUE_REFUND_PREFIX, task),
                _refund_description(VIDEO_TASK_FAILURE_REFUND_PREFIX, task),
            ]),
        )
        .first()
        is not None
    )


def format_video_task_public_error_message(error_message: str | None) -> str:
    detail = (error_message or "").strip()
    if not detail:
        return ""
    if VIDEO_TASK_SAFETY_ERROR_PATTERN.search(detail):
        return VIDEO_TASK_SAFETY_ERROR_MESSAGE
    if VIDEO_TASK_INVALID_ASPECT_RATIO_PATTERN.search(detail):
        return VIDEO_TASK_INVALID_ASPECT_RATIO_MESSAGE
    return VIDEO_TASK_FAILURE_MESSAGE


def serialize_video_task(
    task: VideoTask,
    *,
    credit_refunded: bool | None = None,
    failure_refund_remaining_count: int | None = None,
    cos_config=None,
    public_error_message: bool = False,
) -> dict:
    db = Session.object_session(task)
    reference_images = _parse_reference_images(task.reference_images)
    generation_mode = normalize_video_generation_mode(
        getattr(task, "generation_mode", ""),
        has_reference_images=bool(reference_images),
    )
    resolved_credit_refunded = bool(credit_refunded)
    if credit_refunded is None and db is not None and task.status == "failed":
        resolved_credit_refunded = is_video_task_credit_refunded(db, task)
    resolved_task_error_message = (
        format_video_task_public_error_message(task.error_message)
        if public_error_message
        else (task.error_message or "")
    )
    return {
        "id": task.business_id,
        "model": task.model or "",
        "source": task.source or "web",
        "generation_mode": generation_mode,
        "prompt": task.prompt or "",
        "duration_seconds": int(task.duration_seconds or 0),
        "aspect_ratio": task.aspect_ratio or "",
        "resolution": task.resolution or "",
        "reference_images": reference_images,
        "credit_cost": int(task.credit_cost or 0),
        "credit_refunded": resolved_credit_refunded,
        "failure_refund_remaining_count": failure_refund_remaining_count,
        "used_fallback_api": bool(task.used_fallback_api),
        "task_is_deleted": bool(task.is_deleted),
        "status": task.status or "pending",
        "error_message": resolved_task_error_message,
        "created_at": task.created_at,
        "enqueued_at": task.enqueued_at,
        "request_started_at": task.request_started_at,
        "request_finished_at": task.request_finished_at,
        "videos": [
            {
                "id": result.id,
                "video_url": normalize_external_image_url(result.video_url, cos_config=cos_config),
                "cover_url": normalize_external_image_url(result.cover_url, cos_config=cos_config),
                "video_format": result.video_format or "",
                "video_size_bytes": int(result.video_size_bytes or 0),
                "duration_seconds": result.duration_seconds,
                "status": result.status or "pending",
                "error_message": (
                    format_video_task_public_error_message(result.error_message)
                    if public_error_message
                    else (result.error_message or "")
                ),
            }
            for result in task.results
        ],
        "api_attempts": [
            {
                "id": attempt.id,
                "api_config_id": attempt.api_config_id,
                "api_config_name": attempt.api_config_name or "",
                "attempt_index": int(attempt.attempt_index or 1),
                "is_fallback": bool(attempt.is_fallback),
                "status": attempt.status or "failed",
                "http_status": attempt.http_status,
                "error_message": attempt.error_message or "",
                "duration_ms": attempt.duration_ms,
                "created_at": attempt.created_at,
            }
            for attempt in sorted(task.api_attempts, key=lambda item: (item.attempt_index or 0, item.id or 0))
        ],
    }


def refund_video_task_credit_for_failure_if_needed(db: Session, task: VideoTask) -> bool:
    if task.status != "failed":
        return False
    credit_cost = int(task.credit_cost or 0)
    if credit_cost <= 0:
        return False
    if is_video_task_credit_refunded(db, task):
        return False
    try:
        with db.begin_nested():
            get_user_credit_account(db, task.user_id, for_update=True)
            today_refund_count = get_today_failure_refund_count(db, task.user_id)
            if today_refund_count >= DAILY_FAILURE_REFUND_LIMIT:
                video_task_logger.info(
                    "video task credit refund skipped due to daily failure refund limit",
                    extra={
                        "event": "video_task.credit.refund_daily_limit_exceeded",
                        "task_id": task.business_id,
                        "user_id": user_external_id(task.user) if task.user else str(task.user_id),
                        "credit_cost": credit_cost,
                        "today_refund_count": today_refund_count,
                        "daily_limit": DAILY_FAILURE_REFUND_LIMIT,
                    },
                )
                return False
            apply_user_credit_delta(db, task.user_id, delta=credit_cost, restore_used_credit=True)
            db.add(
                CreditLog(
                    user_id=task.user_id,
                    amount=credit_cost,
                    type="allocate",
                    description=_refund_description(VIDEO_TASK_FAILURE_REFUND_PREFIX, task),
                    task_id=None,
                )
            )
            db.flush()
    except Exception:
        video_task_logger.exception(
            "failed to refund video task credit after generation failure",
            extra={
                "event": "video_task.credit.refund_failed",
                "task_id": task.business_id,
                "user_id": user_external_id(task.user) if task.user else str(task.user_id),
                "credit_cost": credit_cost,
            },
        )
        return False
    video_task_logger.info(
        "video task credit refunded after generation failure",
        extra={
            "event": "video_task.credit.refunded",
            "task_id": task.business_id,
            "user_id": user_external_id(task.user) if task.user else str(task.user_id),
            "credit_cost": credit_cost,
            "today_refund_count": today_refund_count + 1,
            "daily_limit": DAILY_FAILURE_REFUND_LIMIT,
        },
    )
    return True


def _validate_video_task_create_payload(
    generation_mode: str,
    prompt: str,
    duration_seconds: int,
    aspect_ratio: str,
    resolution: str,
    reference_images: list[str] | None = None,
    *,
    max_reference_images: int = VIDEO_TASK_MAX_REFERENCE_IMAGES,
) -> tuple[str, str, int, str, str, list[str]]:
    normalized_generation_mode = normalize_video_generation_mode(generation_mode, has_reference_images=bool(reference_images))
    normalized_prompt = (prompt or "").strip()
    if not normalized_prompt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="提示词不能为空")
    if len(normalized_prompt) > VIDEO_TASK_PROMPT_MAX_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"提示词不能超过 {VIDEO_TASK_PROMPT_MAX_LENGTH} 个字符",
        )
    normalized_duration = int(duration_seconds or 0)
    if normalized_duration <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="视频秒数必须大于 0")
    normalized_aspect_ratio = (aspect_ratio or "").strip()
    normalized_resolution = (resolution or "").strip()
    normalized_reference_images: list[str] = []
    for item in reference_images or []:
        normalized_url = normalize_external_image_url(item)
        if normalized_url and normalized_url not in normalized_reference_images:
            normalized_reference_images.append(normalized_url)
    if normalized_generation_mode == VIDEO_SCENE_AVAILABILITY_TEXT:
        if normalized_reference_images:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文生视频不支持上传参考图")
    elif normalized_generation_mode == VIDEO_SCENE_AVAILABILITY_FIRST_LAST:
        if len(normalized_reference_images) != 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="首尾帧视频必须上传首帧和尾帧两张图片")
    else:
        allowed_reference_images = max(0, min(int(max_reference_images or 0), VIDEO_TASK_MAX_REFERENCE_IMAGES))
        if allowed_reference_images <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前场景不支持上传参考图")
        if not normalized_reference_images:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="图生视频必须上传参考图")
        if len(normalized_reference_images) > allowed_reference_images:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"参考图最多支持 {allowed_reference_images} 张",
            )
    return (
        normalized_generation_mode,
        normalized_prompt,
        normalized_duration,
        normalized_aspect_ratio,
        normalized_resolution,
        normalized_reference_images,
    )


def _validate_video_scene_mode_access(db: Session, scene_key: str, *, generation_mode: str) -> None:
    from app.models.video_external_api_scene_binding import VideoExternalApiSceneBinding

    binding = (
        db.query(VideoExternalApiSceneBinding.availability_mode, VideoExternalApiSceneBinding.availability_modes_json)
        .filter(
            VideoExternalApiSceneBinding.scene_key == (scene_key or "").strip().lower(),
            VideoExternalApiSceneBinding.is_deleted.is_(False),
        )
        .first()
    )
    if not binding:
        return
    availability_mode = binding[0] if isinstance(binding, tuple) else binding.availability_mode
    availability_modes_json = binding[1] if isinstance(binding, tuple) else binding.availability_modes_json
    if is_video_scene_available_for_task_mode(
        availability_mode,
        generation_mode=generation_mode,
        availability_modes_json=availability_modes_json,
    ):
        return
    mode_label = {
        VIDEO_SCENE_AVAILABILITY_TEXT: "文生视频",
        VIDEO_SCENE_AVAILABILITY_IMAGE: "图生视频",
        VIDEO_SCENE_AVAILABILITY_FIRST_LAST: "首尾帧",
    }.get(generation_mode, "当前模式")
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"当前视频场景不支持{mode_label}")


def _ensure_video_task_submission_capacity(db: Session, user_id: int) -> None:
    per_user_limit = max(int(settings.MAX_ACTIVE_TASKS_PER_USER or 0), 0)
    if per_user_limit:
        current_user_active_count = (
            db.query(VideoTask)
            .filter(
                VideoTask.user_id == user_id,
                VideoTask.status.in_(ACTIVE_VIDEO_TASK_STATUSES),
                VideoTask.is_deleted.is_(False),
            )
            .count()
        )
        if current_user_active_count >= per_user_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"当前最多允许同时处理 {per_user_limit} 个视频任务，请稍后再试",
            )

    global_limit = max(int(settings.MAX_ACTIVE_TASKS_GLOBAL or 0), 0)
    if global_limit:
        current_global_active_count = (
            db.query(VideoTask)
            .filter(
                VideoTask.status.in_(ACTIVE_VIDEO_TASK_STATUSES),
                VideoTask.is_deleted.is_(False),
            )
            .count()
        )
        if current_global_active_count >= global_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="当前视频任务较多，请稍后重试",
            )


def create_video_task(
    db: Session,
    *,
    user_id: int,
    model: str,
    source: str,
    generation_mode: str,
    prompt: str,
    duration_seconds: int,
    aspect_ratio: str,
    resolution: str,
    reference_images: list[str] | None = None,
) -> VideoTask:
    normalized_model = (model or "").strip()
    if not normalized_model:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择视频模型")
    max_reference_images = get_video_scene_max_reference_images(db, normalized_model)
    normalized_generation_mode, normalized_prompt, normalized_duration, normalized_aspect_ratio, normalized_resolution, normalized_reference_images = _validate_video_task_create_payload(
        generation_mode,
        prompt,
        duration_seconds,
        aspect_ratio,
        resolution,
        reference_images,
        max_reference_images=max_reference_images,
    )
    _validate_video_scene_mode_access(
        db,
        normalized_model,
        generation_mode=normalized_generation_mode,
    )
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户不存在")

    _ensure_video_task_submission_capacity(db, user_id)
    credit_account = get_user_credit_account(db, user.id, for_update=True)
    current_balance = int(credit_account.remain_credit or 0) if credit_account else 0
    unit_cost = get_video_scene_credit_cost(
        db,
        normalized_model,
        resolution=normalized_resolution,
        duration_seconds=normalized_duration,
    )
    actual_cost = 0 if _is_credit_exempt_user(user) else unit_cost
    if actual_cost > 0 and current_balance < actual_cost:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"积分不足，需要 {actual_cost} 积分，当前余额 {current_balance}",
        )
    if actual_cost > 0:
        credit_account.remain_credit = current_balance - actual_cost
        credit_account.used_credit = int(credit_account.used_credit or 0) + actual_cost
        db.add(credit_account)

    task = VideoTask(
        user_id=user_id,
        model=normalized_model,
        source=(source or "web").strip().lower() or "web",
        generation_mode=normalized_generation_mode,
        prompt=normalized_prompt,
        duration_seconds=normalized_duration,
        aspect_ratio=normalized_aspect_ratio,
        resolution=normalized_resolution,
        reference_images=json.dumps(normalized_reference_images, ensure_ascii=False),
        credit_cost=actual_cost,
        status="pending",
        error_message="",
    )
    db.add(task)
    db.flush()

    db.add(
        VideoResult(
            task_id=task.id,
            video_url="",
            cover_url="",
            video_format="",
            video_size_bytes=0,
            duration_seconds=normalized_duration,
            status="pending",
            error_message="",
        )
    )
    if actual_cost > 0:
        db.add(
            CreditLog(
                user_id=user_id,
                amount=-actual_cost,
                type="consume",
                description=f"{VIDEO_TASK_CONSUME_PREFIX} {normalized_duration} 秒视频 {task.business_id}",
                task_id=None,
            )
        )
    db.commit()
    db.refresh(task)
    return task


def mark_video_tasks_dispatched(db: Session, task_ids: list[int]) -> None:
    if not task_ids:
        return
    tasks = db.query(VideoTask).filter(VideoTask.id.in_(task_ids)).all()
    if not tasks:
        return
    enqueued_at = now_local()
    for task in tasks:
        if task.enqueued_at is None:
            task.enqueued_at = enqueued_at
    db.commit()


def mark_video_tasks_queued(db: Session, task_ids: list[int]) -> None:
    if not task_ids:
        return
    tasks = (
        db.query(VideoTask)
        .filter(VideoTask.id.in_(task_ids), VideoTask.status == "pending")
        .all()
    )
    if not tasks:
        return
    enqueued_at = now_local()
    for task in tasks:
        task.status = "queued"
        task.enqueued_at = enqueued_at
        task.error_message = ""
    db.commit()


def mark_video_tasks_enqueue_failed(db: Session, task_ids: list[int], *, error_message: str) -> None:
    if not task_ids:
        return
    tasks = (
        db.query(VideoTask)
        .filter(VideoTask.id.in_(task_ids), VideoTask.status == "pending")
        .all()
    )
    if not tasks:
        return
    normalized_error_message = (error_message or "视频任务入队失败").strip()
    refund_total = 0
    for task in tasks:
        task.status = "failed"
        task.error_message = normalized_error_message
        refund_total += int(task.credit_cost or 0)
        for result in task.results:
            result.status = "failed"
            result.error_message = normalized_error_message
            result.video_url = ""
            result.cover_url = ""
            result.video_format = ""
            result.video_size_bytes = 0
        if task.credit_cost:
            db.add(
                CreditLog(
                    user_id=task.user_id,
                    amount=int(task.credit_cost or 0),
                    type="allocate",
                    description=_refund_description(VIDEO_TASK_ENQUEUE_REFUND_PREFIX, task),
                    task_id=None,
                )
            )
    if refund_total > 0:
        apply_user_credit_delta(db, tasks[0].user_id, delta=refund_total, restore_used_credit=True)
    db.commit()


def get_video_task_detail(db: Session, task_id: str, user_id: int | None = None) -> VideoTask:
    normalized_task_id = normalize_business_id(task_id)
    query = db.query(VideoTask).filter(VideoTask.business_id == normalized_task_id)
    if user_id is not None:
        query = query.filter(VideoTask.user_id == user_id, VideoTask.is_deleted.is_(False))
    task = query.first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="视频任务不存在")
    return task


def get_video_task_details(db: Session, task_ids: list[str], user_id: int | None = None) -> list[VideoTask]:
    normalized_ids: list[str] = []
    seen_ids: set[str] = set()
    for task_id in task_ids:
        normalized_task_id = normalize_business_id(task_id)
        if not normalized_task_id or normalized_task_id in seen_ids:
            continue
        seen_ids.add(normalized_task_id)
        normalized_ids.append(normalized_task_id)
    if not normalized_ids:
        return []

    query = db.query(VideoTask).filter(VideoTask.business_id.in_(normalized_ids))
    if user_id is not None:
        query = query.filter(VideoTask.user_id == user_id, VideoTask.is_deleted.is_(False))
    task_map = {task.business_id: task for task in query.all()}
    return [task_map[task_id] for task_id in normalized_ids if task_id in task_map]


def list_recent_video_tasks(db: Session, user_id: int, *, limit: int = 20) -> list[VideoTask]:
    normalized_limit = max(min(int(limit or 20), 100), 1)
    return (
        db.query(VideoTask)
        .filter(VideoTask.user_id == user_id, VideoTask.is_deleted.is_(False))
        .order_by(VideoTask.created_at.desc(), VideoTask.id.desc())
        .limit(normalized_limit)
        .all()
    )


def list_admin_video_tasks(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    user_id: int | None = None,
    source: str | None = None,
    model: str | None = None,
    mode: str | None = None,
    prompt: str | None = None,
    status: str | None = None,
    used_fallback_api: bool | None = None,
    start_date=None,
    end_date=None,
    include_unsafe_tasks: bool = True,
) -> dict:
    normalized_page = max(int(page or 1), 1)
    normalized_page_size = max(min(int(page_size or 20), 100), 1)
    query = (
        db.query(VideoTask)
        .options(selectinload(VideoTask.user))
        .join(User, User.id == VideoTask.user_id)
        .filter(User.role == "user", User.is_whitelisted.is_(False))
    )
    if user_id is not None:
        query = query.filter(VideoTask.user_id == user_id)
    if source:
        query = query.filter(VideoTask.source == source)
    if model:
        query = query.filter(VideoTask.model == model)
    if not include_unsafe_tasks:
        query = query.filter(build_exclude_content_safety_failed_task_clause(VideoTask.status, VideoTask.error_message))
    if mode == VIDEO_SCENE_AVAILABILITY_TEXT:
        query = query.filter(
            (VideoTask.generation_mode == VIDEO_SCENE_AVAILABILITY_TEXT)
            | (
                ((VideoTask.generation_mode == "") | (VideoTask.generation_mode.is_(None)))
                & ((VideoTask.reference_images == "") | (VideoTask.reference_images == "[]"))
            )
        )
    elif mode == VIDEO_SCENE_AVAILABILITY_IMAGE:
        query = query.filter(
            (VideoTask.generation_mode == VIDEO_SCENE_AVAILABILITY_IMAGE)
            | (
                ((VideoTask.generation_mode == "") | (VideoTask.generation_mode.is_(None)))
                & VideoTask.reference_images.is_not(None)
                & VideoTask.reference_images.notin_(["", "[]"])
            )
        )
    elif mode == VIDEO_SCENE_AVAILABILITY_FIRST_LAST:
        query = query.filter(VideoTask.generation_mode == VIDEO_SCENE_AVAILABILITY_FIRST_LAST)
    if prompt:
        query = query.filter(VideoTask.prompt.ilike(f"%{prompt.strip()}%"))
    if status:
        query = query.filter(VideoTask.status == status)
    if used_fallback_api is not None:
        query = query.filter(VideoTask.used_fallback_api.is_(used_fallback_api))
    if start_date is not None:
        query = query.filter(VideoTask.created_at >= start_date)
    if end_date is not None:
        query = query.filter(VideoTask.created_at <= end_date)

    total = query.count()
    tasks = (
        query
        .order_by(VideoTask.created_at.desc(), VideoTask.id.desc())
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
        .all()
    )
    cos_config = get_optional_cos_config(db)
    return {
        "total": total,
        "items": [
            {
                **serialize_video_task(task),
                "user_id": task.user.business_id if task.user else "",
                "username": task.user.username if task.user else "",
                "avatar_url": resolve_user_avatar_url(task.user, cos_config=cos_config),
            }
            for task in tasks
        ],
    }


def delete_video_task(db: Session, user_id: int, task_id: str) -> bool:
    normalized_task_id = normalize_business_id(task_id)
    task = (
        db.query(VideoTask)
        .filter(
            VideoTask.business_id == normalized_task_id,
            VideoTask.user_id == user_id,
            VideoTask.is_deleted.is_(False),
        )
        .first()
    )
    if not task:
        return False

    task.is_deleted = True
    db.commit()
    return True


def expire_stale_video_tasks(db: Session, *, user_id: int | None = None) -> None:
    timeout_seconds = max(int(settings.PROCESSING_TASK_TIMEOUT_SECONDS or 0), 0)
    if timeout_seconds <= 0:
        return
    deadline = now_local() - timedelta(seconds=timeout_seconds)
    query = db.query(VideoTask).filter(
        VideoTask.status.in_(ACTIVE_VIDEO_TASK_STATUSES),
        VideoTask.updated_at.is_not(None),
        VideoTask.updated_at < deadline,
    )
    if user_id is not None:
        query = query.filter(VideoTask.user_id == user_id)
    tasks = query.all()
    if not tasks:
        return

    for task in tasks:
        task.status = "failed"
        task.error_message = "视频任务处理超时，已自动关闭"
        task.request_finished_at = now_local()
        for result in task.results:
            if result.status == "pending":
                result.status = "failed"
                result.error_message = task.error_message
        refund_video_task_credit_for_failure_if_needed(db, task)
    db.commit()
