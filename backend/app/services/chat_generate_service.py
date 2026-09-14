from __future__ import annotations

import json
import logging
import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.external_api_scene_binding import ExternalApiSceneBinding
from app.models.user import User
from app.schemas.chat import (
    MAX_CHAT_IMAGES,
    ChatGenerateActionRequest,
    ChatGenerateOut,
    ChatMessageOut,
)
from app.services.business_id_service import task_external_id, user_external_id
from app.services.external_api_config_service import (
    SCENE_TYPE_GENERATE,
    SCENE_TYPE_IMAGE_EDIT,
    get_default_generation_model_key,
    require_scene_config,
)
from app.services.task_service import (
    create_tasks,
    mark_tasks_dispatched,
    mark_tasks_enqueue_failed,
    mark_tasks_queued,
)


logger = logging.getLogger(__name__)
task_logger = logging.getLogger("app.task")

GENERATE_IMAGE_SYSTEM_HINT = """当你已经准备好可直接用于生图的提示词，且用户明确要求生成、出图、改图或图编辑时，先用一两句话确认将使用的提示词，然后在回复末尾必须单独输出：

```generate-image
{"prompt":"最终完整提示词","num_images":1,"mode":"generate"}
```

mode 只能是 generate 或 image_edit：
- 从零描述画面、明确文生图、不要参考上一张：mode=generate
- 本条消息附了图，或要把上一张结果/参考图里的内容改掉、替换、图编辑：mode=image_edit
用户说「生成」「出图」「图编辑生成」时都要输出该代码块，不要只写 ```prompt。不要在用户只是讨论、修改提示词、还没要求出图时输出。prompt 必须是最终可生图的完整提示词。"""

GENERATE_FENCE_RE = re.compile(
    r"```(?:generate-image|generate_image)\s*\n([\s\S]*?)```",
    re.IGNORECASE,
)
INCOMPLETE_FENCE_RE = re.compile(
    r"```(?:generate-image|generate_image)\s*\n[\s\S]*$",
    re.IGNORECASE,
)
PROMPT_FENCE_RE = re.compile(
    r"```(?:prompt|提示词)\s*\n([\s\S]*?)```",
    re.IGNORECASE,
)
GENERATE_REQUEST_RE = re.compile(
    r"(生成图片|生成一?张图|出图|生图|开始生成|直接生成|帮我生成|画一?张|做一?张图|图编辑生成|改图生成)",
    re.IGNORECASE,
)
PROMPT_ONLY_REQUEST_RE = re.compile(
    r"((提示词|prompt).{0,12}(优化|修改|改写|润色|扩写|调整|生成)|"
    r"(优化|修改|改写|润色|扩写|调整|生成).{0,12}(提示词|prompt))",
    re.IGNORECASE,
)


def _safe_num_images(value: object) -> int:
    try:
        return max(1, min(8, int(value or 1)))
    except (TypeError, ValueError):
        return 1


def _wants_generation_now(text: str) -> bool:
    source = text or ""
    if PROMPT_ONLY_REQUEST_RE.search(source) and not re.search(
        r"(生成图片|生成一?张图|出图|生图|开始生成|直接生成|图编辑生成|改图生成)",
        source,
        re.IGNORECASE,
    ):
        return False
    return bool(GENERATE_REQUEST_RE.search(source) or _looks_like_image_edit(source))


def parse_generate_extra(raw: str | None) -> ChatGenerateOut | None:
    if not (raw or "").strip():
        return None
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    status_value = str(payload.get("status") or "").strip()
    if not status_value:
        return None
    refs = payload.get("reference_images") or []
    task_ids = payload.get("task_ids") or []
    return ChatGenerateOut(
        status=status_value,
        prompt=str(payload.get("prompt") or "").strip(),
        num_images=_safe_num_images(payload.get("num_images")),
        reference_images=[str(url).strip() for url in refs if str(url).strip()],
        mode_hint=str(payload.get("mode_hint") or "generate").strip() or "generate",
        model=str(payload.get("model") or "").strip(),
        size=str(payload.get("size") or "").strip(),
        resolution=str(payload.get("resolution") or "").strip(),
        custom_size=str(payload.get("custom_size") or "").strip(),
        task_ids=[str(item).strip() for item in task_ids if str(item).strip()],
        error_message=str(payload.get("error_message") or "").strip(),
    )


def dump_generate_extra(payload: ChatGenerateOut) -> str:
    return json.dumps(payload.model_dump(), ensure_ascii=False)


ACTIVE_TASK_STATUSES = ("pending", "queued", "processing")


def sync_chat_generate_status_for_tasks(db: Session, task_ids: list[str]) -> None:
    from app.services.business_id_service import get_task_by_business_id
    from app.utils.business_id import normalize_business_id

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in task_ids:
        task_id = normalize_business_id(raw)
        if not task_id or task_id in seen:
            continue
        seen.add(task_id)
        normalized.append(task_id)
    if not normalized:
        return

    messages = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.extra_json.is_not(None),
            or_(*[ChatMessage.extra_json.contains(task_id) for task_id in normalized]),
        )
        .all()
    )
    changed = False
    for message in messages:
        extra = parse_generate_extra(getattr(message, "extra_json", None))
        if not extra or extra.status != "running" or not extra.task_ids:
            continue
        tasks = [get_task_by_business_id(db, task_id) for task_id in extra.task_ids]
        loaded = [task for task in tasks if task is not None]
        if not loaded:
            continue
        if any((task.status or "") in ACTIVE_TASK_STATUSES for task in loaded):
            continue
        failed = [task for task in loaded if (task.status or "") == "failed"]
        if any((task.status or "") == "success" for task in loaded):
            extra.status = "success"
            extra.error_message = ""
        else:
            extra.status = "failed"
            extra.error_message = next(
                (
                    (task.error_message or task.provider_error_message or "").strip()
                    for task in failed
                    if (task.error_message or task.provider_error_message or "").strip()
                ),
                extra.error_message or "生图失败",
            )
        message.extra_json = dump_generate_extra(extra)
        db.add(message)
        changed = True
    if changed:
        db.commit()


def reconcile_running_chat_generates(db: Session, messages: list[ChatMessage]) -> None:
    task_ids: list[str] = []
    for message in messages:
        extra = parse_generate_extra(getattr(message, "extra_json", None))
        if extra and extra.status == "running" and extra.task_ids:
            task_ids.extend(extra.task_ids)
    if not task_ids:
        return
    from app.services.task_service import _expire_stale_processing_tasks
    from app.utils.business_id import normalize_business_id

    normalized = [normalize_business_id(task_id) for task_id in task_ids]
    normalized = [task_id for task_id in normalized if task_id]
    if normalized:
        _expire_stale_processing_tasks(db, business_ids=normalized)
    sync_chat_generate_status_for_tasks(db, task_ids)


def strip_generate_image_fence(text: str) -> str:
    cleaned = GENERATE_FENCE_RE.sub("", text or "")
    cleaned = INCOMPLETE_FENCE_RE.sub("", cleaned)
    return cleaned.strip()


def extract_generate_image_payload(text: str) -> tuple[str, dict[str, Any] | None]:
    source = text or ""
    match = GENERATE_FENCE_RE.search(source)
    if not match:
        return source.strip(), None
    raw = (match.group(1) or "").strip()
    payload: dict[str, Any] | None = None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            payload = parsed
        elif isinstance(parsed, str) and parsed.strip():
            payload = {"prompt": parsed.strip()}
    except Exception:
        if raw:
            payload = {"prompt": raw}
    prompt = str((payload or {}).get("prompt") or "").strip()
    if not prompt:
        return strip_generate_image_fence(source), None
    try:
        num_images = max(1, min(8, int((payload or {}).get("num_images") or 1)))
    except (TypeError, ValueError):
        num_images = 1
    mode = str((payload or {}).get("mode") or "").strip().lower()
    if mode not in {"generate", "image_edit"}:
        mode = ""
    cleaned = strip_generate_image_fence(source)
    return cleaned, {"prompt": prompt, "num_images": num_images, "mode": mode}


def _fallback_prompt_payload(reply_text: str, user_text: str) -> dict[str, Any] | None:
    if not _wants_generation_now(user_text):
        return None
    match = PROMPT_FENCE_RE.search(reply_text or "")
    prompt = (match.group(1) if match else "").strip()
    if not prompt:
        return None
    return {
        "prompt": prompt,
        "num_images": 1,
        "mode": "image_edit" if _looks_like_image_edit(user_text) else "",
    }


IMAGE_EDIT_HINT_RE = re.compile(
    r"(图编辑|按图|参考图|改成|换成|替换|改一下|修一下|变成|基于这|把这张|把图|图片里|图中的|上一张)",
    re.IGNORECASE,
)
TEXT_GENERATE_HINT_RE = re.compile(
    r"(文生图|不要参考|不要用图|不要上一张|重新文生)",
    re.IGNORECASE,
)


def _looks_like_image_edit(text: str) -> bool:
    return bool(IMAGE_EDIT_HINT_RE.search(text or ""))


def _looks_like_text_generate(text: str) -> bool:
    return bool(TEXT_GENERATE_HINT_RE.search(text or ""))


def _task_result_image_urls(db: Session, task_ids: list[str]) -> list[str]:
    from app.models.image import Image
    from app.services.business_id_service import get_task_by_business_id

    urls: list[str] = []
    seen: set[str] = set()
    for task_id in task_ids:
        task = get_task_by_business_id(db, task_id)
        if not task:
            continue
        rows = (
            db.query(Image)
            .filter(
                Image.task_id == task.id,
                Image.status == "success",
                Image.is_deleted.is_(False),
            )
            .order_by(Image.id.asc())
            .all()
        )
        for item in rows:
            url = (item.image_url or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            urls.append(url)
            if len(urls) >= MAX_CHAT_IMAGES:
                return urls
    return urls


def _latest_context_image_urls(
    db: Session,
    session_pk: int,
    *,
    before_message_id: int | None,
) -> list[str]:
    from app.services.chat_service import _parse_message_image_urls

    query = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session_pk,
            ChatMessage.role.in_(["user", "assistant"]),
            ChatMessage.status == "success",
        )
        .order_by(ChatMessage.id.desc())
    )
    if before_message_id:
        query = query.filter(ChatMessage.id < before_message_id)
    for item in query.limit(30).all():
        if item.role == "user":
            urls = _parse_message_image_urls(getattr(item, "images_json", None))
            if urls:
                return urls[:MAX_CHAT_IMAGES]
        extra = parse_generate_extra(getattr(item, "extra_json", None))
        if extra and extra.task_ids:
            urls = _task_result_image_urls(db, extra.task_ids)
            if urls:
                return urls[:MAX_CHAT_IMAGES]
    return []


def _resolve_generate_mode_and_refs(
    *,
    current_refs: list[str],
    context_refs: list[str],
    requested_mode: str,
    user_text: str,
) -> tuple[str, list[str]]:
    edit_intent = requested_mode == "image_edit" or _looks_like_image_edit(user_text)
    if requested_mode == "generate" or _looks_like_text_generate(user_text):
        return "generate", []
    if current_refs:
        return "image_edit", current_refs[:MAX_CHAT_IMAGES]
    if edit_intent and context_refs:
        return "image_edit", context_refs[:MAX_CHAT_IMAGES]
    return "generate", []


def apply_generate_proposal(
    db: Session,
    *,
    session: ChatSession,
    assistant_message: ChatMessage,
    user_message: ChatMessage | None,
    reply_text: str,
) -> str:
    from app.services.chat_service import _message_image_urls

    cleaned, payload = extract_generate_image_payload(reply_text)
    user_text = (user_message.content if user_message else "") or ""
    if not payload:
        payload = _fallback_prompt_payload(reply_text, user_text)
    if not payload:
        return cleaned
    current_refs = _message_image_urls(user_message) if user_message else []
    context_refs = _latest_context_image_urls(
        db,
        int(session.id),
        before_message_id=int(assistant_message.id) if assistant_message.id else None,
    )
    mode_hint, refs = _resolve_generate_mode_and_refs(
        current_refs=current_refs,
        context_refs=context_refs,
        requested_mode=str(payload.get("mode") or "").strip(),
        user_text=(user_message.content if user_message else "") or "",
    )
    extra = ChatGenerateOut(
        status="pending_confirm",
        prompt=payload["prompt"],
        num_images=int(payload.get("num_images") or 1),
        reference_images=refs[:MAX_CHAT_IMAGES],
        mode_hint=mode_hint,
    )
    assistant_message.extra_json = dump_generate_extra(extra)
    return cleaned or "已准备好生图提示词，请确认后开始生成。"


def _enabled_scene(db: Session, scene_key: str) -> ExternalApiSceneBinding:
    binding = (
        db.query(ExternalApiSceneBinding)
        .filter(
            ExternalApiSceneBinding.scene_key == scene_key,
            ExternalApiSceneBinding.is_deleted.is_(False),
        )
        .first()
    )
    if not binding:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的生图模型")
    if binding.status != "enabled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该生图模型已停用")
    return binding


def _default_image_edit_model_key(db: Session) -> str:
    binding = (
        db.query(ExternalApiSceneBinding)
        .filter(
            ExternalApiSceneBinding.is_deleted.is_(False),
            ExternalApiSceneBinding.scene_type == SCENE_TYPE_IMAGE_EDIT,
            ExternalApiSceneBinding.status == "enabled",
        )
        .order_by(ExternalApiSceneBinding.sort_order.asc(), ExternalApiSceneBinding.id.asc())
        .first()
    )
    if not binding:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未配置可用的图编辑模型")
    return str(binding.scene_key)


def _dispatch_created_tasks(db: Session, user: User, tasks: list, *, mode: str, model: str) -> None:
    try:
        from app.workers.generation import dispatch_generation_task, get_generation_dispatch_mode
        dispatch_mode = get_generation_dispatch_mode()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

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
                    "mode": mode,
                    "model": model,
                    "source": "chat",
                },
            )
        mark_tasks_dispatched(db, dispatched_task_ids)
        if dispatch_mode == "celery":
            mark_tasks_queued(db, dispatched_task_ids)
    except Exception as exc:
        failed_task_ids = [task.id for task in tasks if task.id not in set(dispatched_task_ids)]
        mark_tasks_enqueue_failed(db, failed_task_ids, error_message=str(exc))
        if dispatched_task_ids:
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="任务队列暂不可用，请稍后重试",
        ) from exc


def _chat_generate_can_retry(db: Session, extra: ChatGenerateOut) -> bool:
    if extra.status == "failed":
        return True
    if extra.status != "running":
        return False
    if not extra.task_ids:
        return True
    from app.services.business_id_service import get_task_by_business_id

    tasks = [get_task_by_business_id(db, task_id) for task_id in extra.task_ids]
    loaded = [task for task in tasks if task is not None]
    if not loaded:
        return True
    if any((task.status or "") in ACTIVE_TASK_STATUSES for task in loaded):
        return False
    return all((task.status or "") == "failed" for task in loaded)


def _start_chat_generate_tasks(
    db: Session,
    *,
    user: User,
    message: ChatMessage,
    extra: ChatGenerateOut,
    body: ChatGenerateActionRequest,
) -> ChatMessage:
    prompt = extra.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有可生成的提示词")

    refs = extra.reference_images
    expected_type = SCENE_TYPE_IMAGE_EDIT if refs else SCENE_TYPE_GENERATE
    model_key = (body.model or extra.model or "").strip()
    if not model_key:
        model_key = _default_image_edit_model_key(db) if refs else get_default_generation_model_key(db)
    binding = _enabled_scene(db, model_key)
    scene_type = (binding.scene_type or "").strip()
    if scene_type != expected_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请选择与当前模式匹配的生图模型",
        )
    require_scene_config(db, model_key)

    custom_size = "" if binding.hide_custom_size else (body.custom_size or "").strip()
    if custom_size:
        size = ""
        resolution = ""
    else:
        size = "" if binding.hide_aspect_ratio else (body.size or extra.size or "").strip()
        resolution = "" if binding.hide_resolution else (body.resolution or extra.resolution or "").strip()
    num_images = max(1, min(8, int(body.num_images or extra.num_images or 1)))

    try:
        from app.workers.generation import get_generation_dispatch_mode
        get_generation_dispatch_mode()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    extra.status = "running"
    extra.model = model_key
    extra.num_images = num_images
    extra.size = size
    extra.resolution = resolution
    extra.custom_size = custom_size
    extra.task_ids = []
    extra.error_message = ""
    message.extra_json = dump_generate_extra(extra)
    db.add(message)
    db.flush()

    tasks = create_tasks(
        db,
        user_id=user.id,
        model=model_key,
        source="web",
        mode="generate",
        prompt=prompt,
        num_images=num_images,
        size=size,
        resolution=resolution,
        custom_size=custom_size,
        reference_images=refs or None,
    )
    message = db.get(ChatMessage, int(message.id)) or message

    extra.task_ids = [task_external_id(task) for task in tasks]
    message.extra_json = dump_generate_extra(extra)
    db.add(message)
    db.commit()
    db.refresh(message)

    try:
        _dispatch_created_tasks(db, user, tasks, mode="generate", model=model_key)
    except HTTPException as exc:
        extra.status = "failed"
        extra.error_message = str(exc.detail or "任务队列暂不可用，请稍后重试")
        message.extra_json = dump_generate_extra(extra)
        db.add(message)
        db.commit()
        db.refresh(message)
    return message


def confirm_or_cancel_chat_generate(
    db: Session,
    user: User,
    session_id: str,
    message_id: int,
    body: ChatGenerateActionRequest,
) -> ChatMessageOut:
    from app.services.chat_service import _require_session, _serialize_message

    session = _require_session(db, user.id, session_id)
    message = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.id == message_id,
            ChatMessage.session_id == session.id,
            ChatMessage.role == "assistant",
        )
        .with_for_update()
        .first()
    )
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息不存在")

    extra = parse_generate_extra(getattr(message, "extra_json", None))
    if not extra or extra.status not in {"pending_confirm", "running", "success", "failed", "cancelled"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="这条消息没有可确认的生图")

    public_id = (session.session_id or "").strip()
    if body.action == "cancel":
        if extra.status != "pending_confirm":
            return _serialize_message(message, public_session_id=public_id)
        extra.status = "cancelled"
        extra.error_message = ""
        message.extra_json = dump_generate_extra(extra)
        db.add(message)
        db.commit()
        db.refresh(message)
        return _serialize_message(message, public_session_id=public_id)

    if body.action == "retry":
        if not _chat_generate_can_retry(db, extra):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前生图任务还不能重试")
        message = _start_chat_generate_tasks(db, user=user, message=message, extra=extra, body=body)
        return _serialize_message(message, public_session_id=public_id)

    if extra.status != "pending_confirm":
        return _serialize_message(message, public_session_id=public_id)

    message = _start_chat_generate_tasks(db, user=user, message=message, extra=extra, body=body)
    return _serialize_message(message, public_session_id=public_id)
