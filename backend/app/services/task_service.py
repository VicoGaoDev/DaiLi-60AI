from datetime import timedelta
import logging
import json
import re
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.config import settings
from app.models.task import Task
from app.models.image import Image
from app.models.external_api_config import ExternalApiConfig
from app.models.external_api_scene_binding import ExternalApiSceneBinding
from app.models.user import User
from app.models.credit_log import CreditLog
from app.services.failure_refund_service import (
    DAILY_FAILURE_REFUND_LIMIT,
    IMAGE_TASK_FAILURE_REFUND_DESCRIPTION,
    get_today_failure_refund_count,
)
from app.services.business_id_service import task_external_id, user_external_id
from app.services.board_service import validate_user_board_id
from app.services.distributed_lock_service import RedisLockHandle, acquire_redis_lock, release_redis_lock
from app.services.external_api_config_service import SCENE_INPAINT, SCENE_SMART_CUTOUT, get_scene_credit_cost
from app.services.user_credit_service import apply_user_credit_delta, get_user_credit_account
from app.utils.business_id import normalize_business_id
from app.utils.datetime_utils import now_local

ACTIVE_TASK_STATUSES = ("pending", "queued", "processing")
MAX_TASK_PROMPT_LENGTH = 10000
ENQUEUE_FAILURE_DESCRIPTION = "任务入队失败，返还积分"
TASK_FAILURE_REFUND_DESCRIPTION = "任务失败，返还积分"
TASK_SUBMISSION_LOCK_PREFIX = "banana:tasks:submission:user"
TASK_SUBMISSION_LOCK_TIMEOUT_SECONDS = 30
TASK_SUBMISSION_LOCK_BLOCKING_TIMEOUT_SECONDS = 5
TASK_SUBMISSION_LOCK_SLOTS_PER_USER = max(int(settings.MAX_ACTIVE_TASKS_PER_USER or 0), 1)
PROCESSING_TASK_TIMEOUT_DESCRIPTION = "任务处理超时，已自动关闭"
ASYNC_PROVIDER_TIMEOUT_GRACE_SECONDS = 60
task_logger = logging.getLogger("app.task")


def _is_credit_exempt_user(user: User | None) -> bool:
    return bool(user and user.role == "superadmin")


def is_task_credit_refunded(db: Session, task_id: int) -> bool:
    return (
        db.query(CreditLog.id)
        .filter(
            CreditLog.task_id == task_id,
            CreditLog.type == "allocate",
            CreditLog.description.in_([
                ENQUEUE_FAILURE_DESCRIPTION,
                TASK_FAILURE_REFUND_DESCRIPTION,
            ]),
        )
        .first()
        is not None
    )


def is_task_generation_failure_credit_refunded(db: Session, task_id: int) -> bool:
    return (
        db.query(CreditLog.id)
        .filter(
            CreditLog.task_id == task_id,
            CreditLog.type == "allocate",
            CreditLog.description == TASK_FAILURE_REFUND_DESCRIPTION,
        )
        .first()
        is not None
    )


def refund_task_credit_for_generation_failure_if_needed(
    db: Session,
    task: Task,
) -> bool:
    if task.status != "failed":
        return False
    credit_cost = int(task.credit_cost or 0)
    if credit_cost <= 0:
        return False

    if is_task_credit_refunded(db, task.id):
        return False

    try:
        with db.begin_nested():
            get_user_credit_account(db, task.user_id, for_update=True)
            today_refund_count = get_today_failure_refund_count(db, task.user_id)
            if today_refund_count >= DAILY_FAILURE_REFUND_LIMIT:
                task_logger.info(
                    "task credit refund skipped due to daily failure refund limit",
                    extra={
                        "event": "task.credit.refund_daily_limit_exceeded",
                        "task_id": task_external_id(task),
                        "user_id": user_external_id(task.user) if task.user else str(task.user_id),
                        "credit_cost": credit_cost,
                        "today_refund_count": today_refund_count,
                        "daily_limit": DAILY_FAILURE_REFUND_LIMIT,
                    },
                )
                return False
            apply_user_credit_delta(
                db,
                task.user_id,
                delta=credit_cost,
                restore_used_credit=True,
            )
            db.add(CreditLog(
                user_id=task.user_id,
                amount=credit_cost,
                type="allocate",
                description=IMAGE_TASK_FAILURE_REFUND_DESCRIPTION,
                task_id=task.id,
            ))
            db.flush()
    except Exception:
        task_logger.exception(
            "failed to refund task credit after generation failure",
            extra={
                "event": "task.credit.refund_failed",
                "task_id": task_external_id(task),
                "user_id": user_external_id(task.user) if task.user else str(task.user_id),
                "credit_cost": credit_cost,
            },
        )
        return False
    task_logger.info(
        "task credit refunded after generation failure",
        extra={
            "event": "task.credit.refunded",
            "task_id": task_external_id(task),
            "user_id": user_external_id(task.user) if task.user else str(task.user_id),
            "credit_cost": credit_cost,
            "today_refund_count": today_refund_count + 1,
            "daily_limit": DAILY_FAILURE_REFUND_LIMIT,
        },
    )
    return True


SMART_CUTOUT_PROMPT = "智能抠图"
CUSTOM_SIZE_PATTERN = re.compile(r"^(\d+)[xX](\d+)$")
CUSTOM_SIZE_PIXEL_MULTIPLE = 16
CUSTOM_SIZE_MAX_ASPECT_RATIO = 3
CUSTOM_SIZE_MAX_SIDE = 3840
CUSTOM_SIZE_MIN_PIXELS = 655360


def _validate_custom_size(db: Session, scene_key: str, custom_size: str) -> str:
    normalized = (custom_size or "").strip()
    if not normalized:
        return ""
    binding = (
        db.query(ExternalApiSceneBinding)
        .filter(
            ExternalApiSceneBinding.scene_key == scene_key,
            ExternalApiSceneBinding.is_deleted.is_(False),
        )
        .first()
    )
    if not binding or binding.hide_custom_size:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前模型不支持自定义分辨率")
    match = CUSTOM_SIZE_PATTERN.fullmatch(normalized)
    if not match:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="自定义分辨率格式应为 宽x高")
    width, height = (int(match.group(1)), int(match.group(2)))
    minimum = max(1, int(binding.custom_size_min or 256))
    maximum = max(minimum, int(binding.custom_size_max or 4096))
    step = max(1, int(binding.custom_size_step or 8))
    if not (minimum <= width <= maximum and minimum <= height <= maximum):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"自定义分辨率宽高须在 {minimum}-{maximum} 之间",
        )
    if (width - minimum) % step != 0 or (height - minimum) % step != 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"自定义分辨率宽高须按 {step} 递增",
        )
    if width % 16 != 0 or height % 16 != 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="自定义分辨率宽高须为 16px 的倍数",
        )
    if max(width, height) > CUSTOM_SIZE_MAX_SIDE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"自定义分辨率最大边长不超过 {CUSTOM_SIZE_MAX_SIDE}px",
        )
    short_side = min(width, height)
    long_side = max(width, height)
    if short_side <= 0 or long_side / short_side > CUSTOM_SIZE_MAX_ASPECT_RATIO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"自定义分辨率长短边比例不能超过 {CUSTOM_SIZE_MAX_ASPECT_RATIO}:1",
        )
    if width * height < CUSTOM_SIZE_MIN_PIXELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"自定义分辨率总像素数不得低于 {CUSTOM_SIZE_MIN_PIXELS}px",
        )
    return f"{width}x{height}"


def _validate_task_create_payload(
    mode: str,
    prompt: str,
    num_images: int,
    source_image: str,
    mask_image: str,
    reference_images: list[str] | None = None,
) -> tuple[str, int, str]:
    mode = (mode or "generate").strip().lower()
    if mode not in {"generate", "inpaint", "smart_cutout"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的生成模式")
    normalized_prompt = (prompt or "").strip()
    if mode == "smart_cutout":
        normalized_prompt = normalized_prompt or SMART_CUTOUT_PROMPT
    elif not normalized_prompt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="提示词不能为空")
    if len(normalized_prompt) > MAX_TASK_PROMPT_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"提示词不能超过 {MAX_TASK_PROMPT_LENGTH} 个字符",
        )
    if num_images < 1 or num_images > 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="生成数量须在 1-8 之间")
    if mode == "inpaint":
        if not source_image.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先上传原图")
        if not mask_image.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先涂抹需要重绘的区域")
        num_images = 1
    if mode == "smart_cutout":
        refs = [item.strip() for item in (reference_images or []) if item and str(item).strip()]
        if not refs:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先上传目标图")
        if len(refs) > 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="智能抠图最多支持原图和涂抹蒙版各一张")
        num_images = 1
    return mode, num_images, normalized_prompt


def _task_submission_lock_name(user_id: int, slot_index: int) -> str:
    return f"{TASK_SUBMISSION_LOCK_PREFIX}:{int(user_id)}:{int(slot_index)}"


def _acquire_task_submission_lock(user_id: int) -> RedisLockHandle:
    if settings.allow_sync_generation_fallback:
        # In sync fallback mode, skip Redis probing and rely on in-process controls.
        return RedisLockHandle(status="acquired")

    saw_unavailable = False
    for slot_index in range(TASK_SUBMISSION_LOCK_SLOTS_PER_USER):
        handle = acquire_redis_lock(
            _task_submission_lock_name(user_id, slot_index),
            timeout_seconds=TASK_SUBMISSION_LOCK_TIMEOUT_SECONDS,
            blocking_timeout_seconds=0,
        )
        if handle.status == "acquired":
            return handle
        if handle.status == "unavailable":
            saw_unavailable = True

    if saw_unavailable:
        return RedisLockHandle(status="unavailable")

    return RedisLockHandle(status="contended")


def _get_async_provider_timeout_seconds(db: Session, task: Task) -> int | None:
    provider_task_id = (task.provider_task_id or "").strip()
    if not provider_task_id or not task.provider_api_config_id:
        return None

    config = (
        db.query(ExternalApiConfig)
        .filter(ExternalApiConfig.id == task.provider_api_config_id)
        .first()
    )
    if not config or (config.call_mode or "sync").strip().lower() != "async":
        return None

    return max(int(config.poll_timeout_seconds or 0), 1)


def _is_async_provider_task_still_polling(db: Session, task: Task, *, now_value) -> bool:
    poll_timeout_seconds = _get_async_provider_timeout_seconds(db, task)
    if poll_timeout_seconds is None:
        return False

    started_at = task.provider_started_at or task.updated_at or task.request_started_at or task.enqueued_at or task.created_at
    if started_at is None:
        return False

    allowed_seconds = poll_timeout_seconds + max(int(settings.AI_TIMEOUT or 0), ASYNC_PROVIDER_TIMEOUT_GRACE_SECONDS)
    return started_at > now_value - timedelta(seconds=allowed_seconds)


def _is_sync_request_in_flight(task: Task, *, now_value) -> bool:
    """同步主/备接口调用进行中时，避免按 updated_at 误杀任务。"""
    if task.request_started_at is None or task.request_finished_at is not None:
        return False
    if (task.provider_task_id or "").strip():
        return False
    attempt_started_at = task.updated_at or task.request_started_at
    allowed_seconds = max(int(settings.AI_TIMEOUT or 0), 1) + ASYNC_PROVIDER_TIMEOUT_GRACE_SECONDS
    return attempt_started_at > now_value - timedelta(seconds=allowed_seconds)


def _is_provider_request_still_active(db: Session, task: Task, *, now_value) -> bool:
    return _is_async_provider_task_still_polling(db, task, now_value=now_value) or _is_sync_request_in_flight(
        task,
        now_value=now_value,
    )


def _expire_stale_processing_tasks(
    db: Session,
    *,
    user_id: int | None = None,
    business_ids: list[str] | None = None,
) -> None:
    timeout_seconds = max(int(settings.PROCESSING_TASK_TIMEOUT_SECONDS or 0), 0)
    if timeout_seconds <= 0:
        return

    now_value = now_local()
    cutoff = now_value - timedelta(seconds=timeout_seconds)
    query = db.query(Task).filter(
        Task.status.in_(ACTIVE_TASK_STATUSES),
        Task.is_deleted.is_(False),
        Task.updated_at.is_not(None),
        Task.updated_at <= cutoff,
    )
    if user_id is not None:
        query = query.filter(Task.user_id == user_id)
    if business_ids:
        query = query.filter(Task.business_id.in_(business_ids))

    stale_tasks = [
        task
        for task in query.all()
        if not _is_provider_request_still_active(db, task, now_value=now_value)
    ]
    if not stale_tasks:
        return

    recoverable_tasks = []
    expire_tasks = []
    for task in stale_tasks:
        provider_task_id = (task.provider_task_id or "").strip()
        provider_status = (task.provider_status or "").strip().lower()
        if provider_task_id and provider_status != "timeout" and (task.status or "") == "processing":
            recoverable_tasks.append(task)
        else:
            expire_tasks.append(task)

    if recoverable_tasks:
        for task in recoverable_tasks:
            task.next_poll_at = now_value
        db.commit()
        task_logger.warning(
            "stale async processing tasks marked due for last poll",
            extra={
                "event": "task.processing.rescheduled",
                "task_ids": [task_external_id(task) for task in recoverable_tasks],
                "task_count": len(recoverable_tasks),
            },
        )

    if not expire_tasks:
        return

    for task in expire_tasks:
        has_success_image = False
        for image in task.images:
            if image.status == "success":
                has_success_image = True
                continue
            image.status = "failed"
            image.error_message = PROCESSING_TASK_TIMEOUT_DESCRIPTION
            image.image_url = ""
            image.preview_url = ""
            image.image_format = ""
            image.image_size_bytes = 0

        task.status = "success" if has_success_image and all(image.status == "success" for image in task.images) else "failed"
        task.error_message = "" if task.status == "success" else PROCESSING_TASK_TIMEOUT_DESCRIPTION
        refund_task_credit_for_generation_failure_if_needed(db, task)

    db.commit()
    task_logger.error(
        "stale processing tasks expired",
        extra={
            "event": "task.processing.expired",
            "task_ids": [task_external_id(task) for task in expire_tasks],
            "task_count": len(expire_tasks),
            "timeout_seconds": timeout_seconds,
        },
    )


def create_tasks(
    db: Session,
    user_id: int,
    model: str,
    source: str,
    mode: str,
    prompt: str,
    num_images: int,
    size: str,
    resolution: str = "4K",
    custom_size: str = "",
    reference_images: list[str] | None = None,
    source_image: str = "",
    mask_image: str = "",
    board_id: int | None = None,
    canvas_id: int | None = None,
) -> list[Task]:
    mode, num_images, prompt = _validate_task_create_payload(
        mode=mode,
        prompt=prompt,
        num_images=num_images,
        source_image=source_image,
        mask_image=mask_image,
        reference_images=reference_images,
    )
    submission_lock = _acquire_task_submission_lock(user_id)
    if submission_lock.status == "contended":
        task_logger.warning(
            "task submission rejected by submission lock",
            extra={
                "event": "task.create.lock_contended",
                "user_id": str(user_id),
                "mode": mode,
                "model": model.strip(),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="当前提交任务较多，请稍后重试",
        )
    if submission_lock.status == "unavailable" and not settings.allow_sync_generation_fallback:
        task_logger.error(
            "task submission lock unavailable",
            extra={
                "event": "task.create.lock_unavailable",
                "user_id": str(user_id),
                "mode": mode,
                "model": model.strip(),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="任务提交锁服务不可用，请稍后重试",
        )

    tasks: list[Task] = []
    try:
        user = (
            db.query(User)
            .filter(User.id == user_id)
            .with_for_update()
            .first()
        )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户不存在",
            )
        credit_account = get_user_credit_account(db, user.id, for_update=True)
        current_balance = int(credit_account.remain_credit or 0) if credit_account else 0
        if mode == "inpaint":
            scene_key = SCENE_INPAINT
        elif mode == "smart_cutout":
            scene_key = SCENE_SMART_CUTOUT
        else:
            scene_key = model.strip()
        normalized_custom_size = (
            ""
            if mode == "inpaint"
            else _validate_custom_size(db, scene_key, custom_size)
        )
        billing_resolution = "" if normalized_custom_size else resolution
        if normalized_custom_size:
            size = ""
            resolution = ""
        single_image_tool = mode in {"inpaint", "smart_cutout"}
        task_logger.info(
            "task submission accepted",
            extra={
                "event": "task.create.requested",
                "user_id": user_external_id(user),
                "mode": mode,
                "model": model.strip(),
                "task_count": 1 if single_image_tool else num_images,
                "prompt_length": len((prompt or "").strip()),
            },
        )
        unit_cost = get_scene_credit_cost(db, scene_key, resolution=billing_resolution)
        task_count = 1 if single_image_tool else num_images
        task_count = ensure_task_submission_capacity(db, user_id=user_id, new_task_count=task_count)
        total_cost = task_count * unit_cost
        per_task_credit_cost = 0 if _is_credit_exempt_user(user) else unit_cost
        actual_total_cost = 0 if _is_credit_exempt_user(user) else total_cost
        if actual_total_cost and current_balance < total_cost:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"积分不足，需要 {total_cost} 积分，当前余额 {current_balance}",
            )

        ref_json = json.dumps(reference_images or [])

        if actual_total_cost:
            credit_account.remain_credit = current_balance - total_cost
            credit_account.used_credit = int(credit_account.used_credit or 0) + total_cost
            db.add(credit_account)

        normalized_prompt = prompt.strip()
        normalized_model = model.strip()
        normalized_source = (source or "web").strip().lower() or "web"
        normalized_source_image = source_image.strip()
        normalized_mask_image = mask_image.strip()
        normalized_canvas_id = int(canvas_id) if canvas_id is not None else None
        normalized_board_id = None if normalized_canvas_id is not None else validate_user_board_id(db, user_id, board_id)
        if mode == "inpaint":
            credit_log_description = "局部重绘 1 张图片"
        elif mode == "smart_cutout":
            credit_log_description = "智能抠图 1 张图片"
        else:
            credit_log_description = "生成 1 张图片"
        if normalized_source == "api":
            credit_log_description = f"API {credit_log_description}"

        for _ in range(task_count):
            task = Task(
                user_id=user_id,
                board_id=normalized_board_id,
                canvas_id=normalized_canvas_id,
                model=normalized_model,
                source=normalized_source,
                mode=mode,
                prompt=normalized_prompt,
                num_images=1,
                size=size,
                resolution=resolution,
                custom_size=normalized_custom_size,
                reference_images=ref_json,
                source_image=normalized_source_image,
                mask_image=normalized_mask_image,
                credit_cost=per_task_credit_cost,
                status="pending",
                error_message="",
            )
            db.add(task)
            db.flush()

            image = Image(task_id=task.id, image_url="", status="pending", error_message="")
            db.add(image)

            if per_task_credit_cost:
                db.add(CreditLog(
                    user_id=user_id,
                    amount=-per_task_credit_cost,
                    type="consume",
                    description=credit_log_description,
                    task_id=task.id,
                ))

            tasks.append(task)

        db.commit()
        for task in tasks:
            db.refresh(task)
        task_logger.info(
            "tasks created",
            extra={
                "event": "task.create.persisted",
                "user_id": user_external_id(user),
                "task_ids": [task_external_id(task) for task in tasks],
                "task_count": len(tasks),
                "mode": mode,
                "model": normalized_model,
                "credit_cost": per_task_credit_cost,
                "total_cost": actual_total_cost,
            },
        )
        return tasks
    except Exception:
        task_logger.exception(
            "task creation failed",
            extra={
                "event": "task.create.failed",
                "user_id": user_external_id(user) if "user" in locals() and user else str(user_id),
                "mode": mode,
                "model": model.strip(),
            },
        )
        db.rollback()
        raise
    finally:
        release_redis_lock(submission_lock)


def ensure_task_submission_capacity(db: Session, user_id: int, new_task_count: int) -> int:
    normalized_new_task_count = max(int(new_task_count or 0), 0)
    if normalized_new_task_count <= 0:
        return 0

    _expire_stale_processing_tasks(db, user_id=user_id)

    per_user_limit = max(int(settings.MAX_ACTIVE_TASKS_PER_USER or 0), 0)
    if per_user_limit:
        current_user_active_count = (
            db.query(Task)
            .filter(
                Task.user_id == user_id,
                Task.status.in_(ACTIVE_TASK_STATUSES),
                Task.is_deleted.is_(False),
            )
            .count()
        )
        available_user_slots = per_user_limit - current_user_active_count
        if available_user_slots <= 0:
            task_logger.warning(
                "task submission exceeded per-user limit",
                extra={
                    "event": "task.create.user_limit_exceeded",
                    "user_id": str(user_id),
                    "task_count": normalized_new_task_count,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"当前最多允许同时处理 {per_user_limit} 个任务，"
                    "请等待部分任务完成后再试"
                ),
            )
        normalized_new_task_count = min(normalized_new_task_count, available_user_slots)

    global_limit = max(int(settings.MAX_ACTIVE_TASKS_GLOBAL or 0), 0)
    if global_limit:
        current_global_active_count = (
            db.query(Task)
            .filter(Task.status.in_(ACTIVE_TASK_STATUSES), Task.is_deleted.is_(False))
            .count()
        )
        available_global_slots = global_limit - current_global_active_count
        if available_global_slots <= 0:
            task_logger.warning(
                "task submission exceeded global limit",
                extra={
                    "event": "task.create.global_limit_exceeded",
                    "user_id": str(user_id),
                    "task_count": normalized_new_task_count,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="当前排队任务较多，请稍后再试",
            )
        normalized_new_task_count = min(normalized_new_task_count, available_global_slots)

    return normalized_new_task_count


def mark_tasks_queued(db: Session, task_ids: list[int]) -> None:
    if not task_ids:
        return

    tasks = (
        db.query(Task)
        .filter(Task.id.in_(task_ids), Task.status == "pending")
        .all()
    )
    enqueued_at = now_local()
    for task in tasks:
        task.status = "queued"
        task.error_message = ""
        task.enqueued_at = enqueued_at
    db.commit()
    task_logger.info(
        "tasks marked queued",
        extra={
            "event": "task.dispatch.queued",
            "task_ids": [task_external_id(task) for task in tasks],
            "task_count": len(tasks),
        },
    )


def mark_tasks_dispatched(db: Session, task_ids: list[int]) -> None:
    if not task_ids:
        return

    tasks = db.query(Task).filter(Task.id.in_(task_ids)).all()
    if not tasks:
        return

    enqueued_at = now_local()
    for task in tasks:
        if task.enqueued_at is None:
            task.enqueued_at = enqueued_at
    db.commit()
    task_logger.info(
        "tasks marked dispatched",
        extra={
            "event": "task.dispatch.persisted",
            "task_ids": [task_external_id(task) for task in tasks],
            "task_count": len(tasks),
        },
    )


def mark_tasks_enqueue_failed(
    db: Session,
    task_ids: list[int],
    *,
    error_message: str,
) -> None:
    if not task_ids:
        return

    tasks = (
        db.query(Task)
        .filter(Task.id.in_(task_ids), Task.status == "pending")
        .all()
    )
    if not tasks:
        return

    normalized_error_message = (error_message or "任务入队失败").strip()
    user = tasks[0].user
    refund_total = 0

    for task in tasks:
        task.status = "failed"
        task.error_message = normalized_error_message
        refund_total += int(task.credit_cost or 0)
        for image in task.images:
            image.status = "failed"
            image.error_message = normalized_error_message
            image.image_url = ""
            image.preview_url = ""
            image.image_format = ""
            image.image_size_bytes = 0

        if task.credit_cost:
            db.add(CreditLog(
                user_id=task.user_id,
                amount=int(task.credit_cost or 0),
                type="allocate",
                description=ENQUEUE_FAILURE_DESCRIPTION,
                task_id=task.id,
            ))

    if user and refund_total:
        apply_user_credit_delta(
            db,
            user.id,
            delta=refund_total,
            restore_used_credit=True,
        )

    db.commit()
    task_logger.error(
        "tasks enqueue failed",
        extra={
            "event": "task.dispatch.failed",
            "task_ids": [task_external_id(task) for task in tasks],
            "task_count": len(tasks),
        },
    )


def get_task_detail(db: Session, task_id: str, user_id: int | None = None) -> Task:
    normalized_task_id = normalize_business_id(task_id)
    if normalized_task_id:
        _expire_stale_processing_tasks(db, user_id=user_id, business_ids=[normalized_task_id])
    query = db.query(Task).filter(Task.business_id == normalized_task_id)
    if user_id is not None:
        query = query.filter(Task.user_id == user_id, Task.is_deleted.is_(False))
    task = query.first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return task


def get_task_details(db: Session, task_ids: list[str], user_id: int | None = None) -> list[Task]:
    if not task_ids:
        return []

    normalized_ids = []
    seen_ids: set[str] = set()
    for task_id in task_ids:
        normalized_task_id = normalize_business_id(task_id)
        if not normalized_task_id:
            continue
        if normalized_task_id in seen_ids:
            continue
        seen_ids.add(normalized_task_id)
        normalized_ids.append(normalized_task_id)

    if not normalized_ids:
        return []

    _expire_stale_processing_tasks(db, user_id=user_id, business_ids=normalized_ids)
    try:
        from app.services.chat_generate_service import sync_chat_generate_status_for_tasks
        sync_chat_generate_status_for_tasks(db, normalized_ids)
    except Exception:
        task_logger.exception(
            "failed to sync chat generate status",
            extra={"event": "task.chat_generate.sync_failed", "task_ids": normalized_ids},
        )

    query = db.query(Task).filter(Task.business_id.in_(normalized_ids))
    if user_id is not None:
        query = query.filter(Task.user_id == user_id, Task.is_deleted.is_(False))

    task_map = {task.business_id: task for task in query.all()}
    return [task_map[task_id] for task_id in normalized_ids if task_id in task_map]
