import json
import re
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, lazyload, load_only, selectinload
from app.models.credit_log import CreditLog
from app.models.external_api_config import ExternalApiConfig
from app.models.external_api_scene_binding import ExternalApiSceneBinding
from app.models.history_pin import HistoryPin
from app.models.image import Image
from app.models.prompt_history import PromptHistory
from app.models.prompt_optimize_task import PromptOptimizeTask
from app.models.task import Task
from app.models.task_api_attempt import TaskApiAttempt
from app.models.user import User
from app.models.user_canvas import UserCanvas
from app.services.content_safety_service import build_exclude_content_safety_failed_task_clause
from app.services.prompt_optimize_service import (
    PROMPT_OPTIMIZE_MODE,
    PROMPT_OPTIMIZE_MODEL,
)
from app.services.prompt_reverse_service import (
    PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION,
    PROMPT_REVERSE_MODE,
    PROMPT_REVERSE_MODEL,
)
from app.services.task_type_service import (
    TASK_TYPE_IMAGE_EDIT,
    TASK_TYPE_INPAINT,
    TASK_TYPE_SMART_CUTOUT,
    TASK_TYPE_PROMPT_OPTIMIZE,
    TASK_TYPE_PROMPT_REVERSE,
    TASK_TYPE_TEXT_GENERATE,
    get_task_scene_type_map,
    get_task_scene_type_subset,
    resolve_task_type_for_task,
)
from app.services.image_delivery_service import (
    format_generation_public_error_message,
    get_optional_cos_config,
    resolve_user_avatar_url,
    serialize_asset_urls,
    serialize_image,
)
from app.services.business_id_service import task_external_id, user_external_id
from app.services.board_service import validate_user_board_id
from app.services.task_service import (
    ENQUEUE_FAILURE_DESCRIPTION,
    TASK_FAILURE_REFUND_DESCRIPTION,
    is_task_generation_failure_credit_refunded,
)
from app.services.external_api_config_service import (
    build_secret_variables,
    render_config,
    resolve_mapped_resolution,
    resolve_scene_generation_configs,
    resolve_smart_cutout_prompt,
)
from app.utils.datetime_utils import now_local
from app.utils.business_id import normalize_business_id

TASK_CREDIT_REFUND_DESCRIPTIONS = (
    ENQUEUE_FAILURE_DESCRIPTION,
    TASK_FAILURE_REFUND_DESCRIPTION,
)
PROMPT_HISTORY_MODES = (PROMPT_REVERSE_MODE,)
PROMPT_HISTORY_MODE_TO_TASK_TYPE = {
    PROMPT_REVERSE_MODE: TASK_TYPE_PROMPT_REVERSE,
}
PROMPT_HISTORY_MODE_TO_MODEL = {
    PROMPT_REVERSE_MODE: PROMPT_REVERSE_MODEL,
}
PROMPT_HISTORY_MODE_TO_DISPLAY_PREFIX = {
    PROMPT_REVERSE_MODE: "PR",
}
PROMPT_OPTIMIZE_HISTORY_ITEM_TYPE = "prompt_optimize_task"
PROMPT_OPTIMIZE_IMAGE_ID_OFFSET = 1_000_000_000


def _exclude_example_template_seed_task_clause():
    return Task.is_example_template_seed.is_(False)


def _get_restricted_user_ids(db: Session) -> list[int]:
    return [
        int(user_id)
        for (user_id,) in (
            db.query(User.id)
            .filter(User.role == "superadmin")
            .all()
        )
    ]


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


def _is_prompt_history_mode(value: str | None) -> bool:
    return (value or "").strip() in PROMPT_HISTORY_MODES


def _resolve_prompt_history_task_type(value: str | None) -> str:
    return PROMPT_HISTORY_MODE_TO_TASK_TYPE.get((value or "").strip(), TASK_TYPE_PROMPT_REVERSE)


def _resolve_prompt_history_model(value: str | None) -> str:
    return PROMPT_HISTORY_MODE_TO_MODEL.get((value or "").strip(), PROMPT_REVERSE_MODEL)


def _build_prompt_optimize_pin_keys(row: PromptOptimizeTask) -> list[str]:
    keys = [_build_history_pin_key(PROMPT_OPTIMIZE_HISTORY_ITEM_TYPE, history_id=row.id)]
    if isinstance(row.legacy_prompt_history_id, int):
        keys.append(_build_history_pin_key("prompt_history", history_id=row.legacy_prompt_history_id))
    return keys


def _resolve_prompt_optimize_pin(history_pin_map: dict[str, HistoryPin], row: PromptOptimizeTask) -> tuple[bool, datetime | None]:
    for key in _build_prompt_optimize_pin_keys(row):
        pin = history_pin_map.get(key)
        if pin:
            return _serialize_history_pin(pin)
    return False, None


def _calculate_task_run_time(task: Task | None) -> int | None:
    if not task or not task.request_finished_at:
        return None
    started_at = task.request_started_at or task.created_at
    if not started_at:
        return None
    return max(0, int((task.request_finished_at - started_at).total_seconds()))


def _get_task_canvas_project_id(task: Task | None) -> str:
    canvas = task.canvas if task else None
    return canvas.project_id if canvas else ""


def _build_history_pin_key(item_type: str, image_id: int | None = None, history_id: int | None = None) -> str:
    if item_type == "task" and isinstance(image_id, int):
        return f"task:{image_id}"
    if item_type == "prompt_history" and isinstance(history_id, int):
        return f"prompt_history:{history_id}"
    if item_type == PROMPT_OPTIMIZE_HISTORY_ITEM_TYPE and isinstance(history_id, int):
        return f"{PROMPT_OPTIMIZE_HISTORY_ITEM_TYPE}:{history_id}"
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
    public_error_message: bool = False,
) -> list[dict]:
    result: list[dict] = []
    for img in sorted(images, key=lambda item: item.id, reverse=True):
        if not include_deleted and img.is_deleted:
            continue
        result.append(serialize_image(img, cos_config=cos_config, public_error_message=public_error_message))
    return result


BASE64_PLACEHOLDER = "<base64>"
BASE64_IMAGE_PLACEHOLDER = "<base64 image>"
BASE64_DATA_URL_PLACEHOLDER = "data:image/png;base64,<base64>"


def _is_base64_like_text(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    if text.startswith("data:") and ";base64," in text[:80]:
        return True
    if len(text) < 160:
        return False
    compact = re.sub(r"\s+", "", text)
    return bool(compact) and len(compact) >= 160 and re.fullmatch(r"[A-Za-z0-9+/=]+", compact) is not None


def _image_mime_from_data_url(value: str) -> str:
    if not value.startswith("data:"):
        return "image/png"
    header = value.split(",", 1)[0]
    return (header[5:].split(";", 1)[0] or "image/png").strip() or "image/png"


def _base64_data_url_placeholder(value: str) -> str:
    return f"data:{_image_mime_from_data_url(value).replace(' ', '')};base64,{BASE64_PLACEHOLDER}" if value.startswith("data:") else BASE64_DATA_URL_PLACEHOLDER


def _redact_payload_value(value: Any, key: str = "") -> Any:
    normalized_key = key.lower()
    if isinstance(value, dict):
        return {item_key: _redact_payload_value(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact_payload_value(item) for item in value]
    if isinstance(value, str):
        if any(marker in normalized_key for marker in ("api_key", "apikey", "authorization", "token", "secret")):
            return "xxx" if value else value
        if normalized_key in {"data", "b64_json", "base64", "image_base64", "source_image_base64", "mask_image_base64"}:
            return BASE64_PLACEHOLDER if value else value
        if normalized_key.endswith("data_url") and _is_base64_like_text(value):
            return _base64_data_url_placeholder(value)
        if _is_base64_like_text(value):
            return _base64_data_url_placeholder(value) if value.startswith("data:") else BASE64_PLACEHOLDER
    return value


def _redact_header_value(name: str, value: Any) -> str:
    header_name = (name or "").strip()
    header_value = str(value or "")
    lowered_name = header_name.lower()
    lowered_value = header_value.lower()
    if lowered_name in {"authorization", "x-api-key", "api-key", "x-key", "key", "token", "x-token"}:
        if lowered_value.startswith("bearer "):
            return "Bearer xxx"
        return "xxx"
    if "authorization" in lowered_name or "token" in lowered_name or "secret" in lowered_name:
        return "xxx"
    if lowered_value.startswith("bearer "):
        return "Bearer xxx"
    return header_value


def _public_image_url_or_placeholder(raw: str, *, cos_config) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if _is_base64_like_text(value):
        return BASE64_IMAGE_PLACEHOLDER
    return serialize_asset_urls(value, cos_config=cos_config)["image_url"] or value


def _inline_image_part_placeholder(raw: str) -> dict:
    return {
        "inlineData": {
            "mimeType": _image_mime_from_data_url(raw),
            "data": BASE64_PLACEHOLDER,
        }
    }


def _build_task_render_variables(db: Session, task: Task, *, cos_config) -> dict[str, Any]:
    mode = (task.mode or "generate").strip() or "generate"
    if mode == "inpaint":
        scene_key = TASK_TYPE_INPAINT
    elif mode == "smart_cutout":
        scene_key = TASK_TYPE_SMART_CUTOUT
    else:
        scene_key = task.model or ""
    mapped_resolution = resolve_mapped_resolution(db, scene_key, task.size or "", task.resolution or "")
    parts: list[dict] = []
    variables: dict[str, Any] = {
        **build_secret_variables(db),
        "prompt": task.prompt or "",
        "aspect_ratio": task.size or "",
        "image_size": task.resolution or "",
        "custom_size": task.custom_size or "",
        "mapped_resolution": mapped_resolution,
        "resolved_resolution": (task.custom_size or "").strip() or mapped_resolution,
        "generation_config": {},
        "mode": mode,
        "reference_image_count": 0,
    }

    if mode == "inpaint":
        if task.source_image:
            source_part = _inline_image_part_placeholder(task.source_image)
            parts.append(source_part)
            variables["source_image"] = source_part
            variables["source_image_url"] = _public_image_url_or_placeholder(task.source_image, cos_config=cos_config)
            variables["source_image_base64"] = BASE64_PLACEHOLDER
            variables["source_image_mime_type"] = _image_mime_from_data_url(task.source_image)
            variables["source_image_data_url"] = _base64_data_url_placeholder(task.source_image)
        if task.mask_image:
            mask_part = _inline_image_part_placeholder(task.mask_image)
            parts.append(mask_part)
            variables["mask_image"] = mask_part
            variables["mask_image_base64"] = BASE64_PLACEHOLDER
            variables["mask_image_mime_type"] = _image_mime_from_data_url(task.mask_image)
            variables["mask_image_data_url"] = _base64_data_url_placeholder(task.mask_image)
        parts.append({
            "text": (
                "请基于第1张原图进行局部重绘，第2张图是蒙版：白色区域需要重绘，"
                "黑色区域必须保持原样。严格保留未遮罩区域的主体、构图、光影与细节。"
                f"重绘要求：{task.prompt or ''}"
            )
        })
    else:
        reference_count = 0
        for index, ref_url in enumerate(_parse_refs(task.reference_images), start=1):
            inline_part = _inline_image_part_placeholder(ref_url)
            parts.append(inline_part)
            reference_count += 1
            variables[f"reference_image_{index}"] = inline_part
            variables[f"reference_image_{index}_url"] = _public_image_url_or_placeholder(ref_url, cos_config=cos_config)
            variables[f"reference_image_{index}_base64"] = BASE64_PLACEHOLDER
            variables[f"reference_image_{index}_mime_type"] = _image_mime_from_data_url(ref_url)
            variables[f"reference_image_{index}_data_url"] = _base64_data_url_placeholder(ref_url)
        variables["reference_image_count"] = reference_count
        if mode == "smart_cutout":
            cutout_prompt = resolve_smart_cutout_prompt(task.prompt or "", reference_count)
            variables["prompt"] = cutout_prompt
            parts.append({"text": cutout_prompt})
        else:
            parts.append({"text": task.prompt or ""})

    generation_config = {"responseModalities": ["IMAGE"]}
    if mode != "inpaint":
        generation_config["imageConfig"] = {"aspectRatio": task.size or ""}
        if task.resolution:
            generation_config["imageConfig"]["imageSize"] = task.resolution
    variables["contents_parts"] = parts
    variables["generation_config"] = generation_config
    return variables


def _render_request_preview(config: ExternalApiConfig, variables: dict[str, Any]) -> dict | None:
    try:
        rendered = render_config(config, variables)
    except Exception:
        return None
    return {
        "request_url": rendered.request_url,
        "headers": {
            str(name): _redact_header_value(str(name), value)
            for name, value in (rendered.headers or {}).items()
        },
        "payload": _redact_payload_value(rendered.payload),
    }


def _resolve_task_bound_generation_configs(db: Session, task: Task) -> tuple[ExternalApiConfig | None, ExternalApiConfig | None]:
    mode = (task.mode or "generate").strip() or "generate"
    if mode == "inpaint":
        scene_key = TASK_TYPE_INPAINT
    elif mode == "smart_cutout":
        scene_key = TASK_TYPE_SMART_CUTOUT
    else:
        scene_key = task.model or ""
    if not scene_key:
        return None, None
    try:
        return resolve_scene_generation_configs(db, scene_key)
    except Exception:
        pass
    candidates = []
    for item in (scene_key, scene_key.strip().lower()):
        if item and item not in candidates:
            candidates.append(item)
    binding = (
        db.query(ExternalApiSceneBinding)
        .filter(
            ExternalApiSceneBinding.scene_key.in_(candidates),
            ExternalApiSceneBinding.is_deleted.is_(False),
        )
        .first()
    )
    if not binding:
        return None, None
    primary_config = (
        db.query(ExternalApiConfig)
        .filter(ExternalApiConfig.id == binding.api_config_id)
        .first()
        if binding.api_config_id
        else None
    )
    backup_config = (
        db.query(ExternalApiConfig)
        .filter(ExternalApiConfig.id == binding.backup_api_config_id)
        .first()
        if binding.backup_api_config_id and binding.backup_api_config_id != binding.api_config_id
        else None
    )
    return primary_config, backup_config


def _build_admin_request_previews_for_attempts(
    db: Session,
    task: Task,
    attempts: list[TaskApiAttempt],
    *,
    cos_config,
) -> dict[int, dict]:
    config_ids = sorted({int(attempt.api_config_id) for attempt in attempts if attempt.api_config_id})
    config_names = sorted({(attempt.api_config_name or "").strip() for attempt in attempts if (attempt.api_config_name or "").strip()})
    configs: dict[int, ExternalApiConfig] = {}
    configs_by_name: dict[str, ExternalApiConfig] = {}
    filters = []
    if config_ids:
        filters.append(ExternalApiConfig.id.in_(config_ids))
    if config_names:
        filters.append(ExternalApiConfig.name.in_(config_names))
    if filters:
        config_rows = db.query(ExternalApiConfig).filter(or_(*filters)).all()
        configs = {
            int(config.id): config
            for config in config_rows
        }
        for config in config_rows:
            config_name = (config.name or "").strip()
            if config_name and config_name not in configs_by_name:
                configs_by_name[config_name] = config
    variables = _build_task_render_variables(db, task, cos_config=cos_config)
    preview_by_config_id: dict[int, dict] = {}
    for config_id, config in configs.items():
        preview = _render_request_preview(config, variables)
        if not preview:
            continue
        preview_by_config_id[config_id] = preview
    preview_by_config_name: dict[str, dict] = {}
    for config_name, config in configs_by_name.items():
        if int(config.id) in preview_by_config_id:
            preview_by_config_name[config_name] = preview_by_config_id[int(config.id)]
            continue
        preview = _render_request_preview(config, variables)
        if not preview:
            continue
        preview_by_config_name[config_name] = preview
    bound_primary_config, bound_backup_config = _resolve_task_bound_generation_configs(db, task)
    bound_primary_preview = _render_request_preview(bound_primary_config, variables) if bound_primary_config else None
    bound_backup_preview = _render_request_preview(bound_backup_config, variables) if bound_backup_config else None

    result: dict[int, dict] = {}
    for attempt in attempts:
        if not attempt.id:
            continue
        preview = bound_backup_preview if attempt.is_fallback and bound_backup_preview else bound_primary_preview
        if not preview:
            preview = (
                preview_by_config_id.get(int(attempt.api_config_id or 0))
                or preview_by_config_name.get((attempt.api_config_name or "").strip())
            )
        if preview:
            result[int(attempt.id)] = preview
    return result


def _serialize_task_api_attempts(
    attempts: list[TaskApiAttempt],
    *,
    request_previews: dict[int, dict] | None = None,
) -> list[dict]:
    serialized: list[dict] = []
    preview_map = request_previews or {}
    for attempt in sorted(
        attempts,
        key=lambda item: (
            item.image_index or 0,
            item.image_id or 0,
            item.attempt_index or 0,
            item.id or 0,
        ),
    ):
        serialized.append({
            "id": attempt.id,
            "image_id": attempt.image_id,
            "image_index": attempt.image_index,
            "api_config_id": attempt.api_config_id,
            "api_config_name": attempt.api_config_name or "",
            "attempt_index": int(attempt.attempt_index or 1),
            "is_fallback": bool(attempt.is_fallback),
            "status": attempt.status or "failed",
            "http_status": attempt.http_status,
            "error_message": attempt.error_message or "",
            "duration_ms": attempt.duration_ms,
            "external_http_ms": attempt.external_http_ms,
            "result_download_ms": attempt.result_download_ms,
            "cos_upload_ms": attempt.cos_upload_ms,
            "response_preview": attempt.response_preview or "",
            "created_at": attempt.created_at,
            "request_preview": preview_map.get(int(attempt.id or 0)),
        })
    return serialized


def _load_task_attempts_map(db: Session, task_ids: list[int]) -> dict[int, list[TaskApiAttempt]]:
    normalized_task_ids = [int(task_id) for task_id in task_ids if task_id]
    if not normalized_task_ids:
        return {}
    rows = (
        db.query(TaskApiAttempt)
        .filter(TaskApiAttempt.task_id.in_(normalized_task_ids))
        .order_by(
            TaskApiAttempt.task_id.asc(),
            TaskApiAttempt.image_index.asc(),
            TaskApiAttempt.attempt_index.asc(),
            TaskApiAttempt.id.asc(),
        )
        .all()
    )
    attempts_map: dict[int, list[TaskApiAttempt]] = {}
    for row in rows:
        attempts_map.setdefault(int(row.task_id), []).append(row)
    return attempts_map


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


def _serialize_task_history_detail(
    task: Task,
    *,
    cos_config,
    scene_type_map: dict[str, str] | None = None,
    api_attempts: list[TaskApiAttempt] | None = None,
    include_request_previews: bool = False,
    include_provider_diagnostics: bool = True,
) -> dict:
    primary_image = next(
        (img for img in sorted(task.images, key=lambda item: item.id, reverse=True) if not img.is_deleted),
        None,
    )
    primary_image_payload = serialize_image(
        primary_image,
        cos_config=cos_config,
        public_error_message=not include_provider_diagnostics,
    ) if primary_image else {
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
    visible_images = _serialize_history_images(
        task.images,
        cos_config=cos_config,
        public_error_message=not include_provider_diagnostics,
    )
    task_credit_cost = int(task.credit_cost or 0)
    credit_refunded = False
    if task.status == "failed" and task_credit_cost > 0:
        db = Session.object_session(task)
        credit_refunded = bool(db and is_task_generation_failure_credit_refunded(db, task.id))
    resolved_attempts = api_attempts
    if resolved_attempts is None:
        db = Session.object_session(task)
        resolved_attempts = (
            db.query(TaskApiAttempt)
            .filter(TaskApiAttempt.task_id == task.id)
            .order_by(TaskApiAttempt.image_index.asc(), TaskApiAttempt.attempt_index.asc(), TaskApiAttempt.id.asc())
            .all()
            if db and task.id
            else []
        )
    request_previews: dict[int, dict] = {}
    if include_request_previews and resolved_attempts:
        db = Session.object_session(task)
        if db:
            request_previews = _build_admin_request_previews_for_attempts(
                db,
                task,
                resolved_attempts,
                cos_config=cos_config,
            )
    return {
        "history_id": None,
        "item_type": "task",
        "display_id": task_external_id(task),
        "task_id": task_external_id(task),
        "canvas_id": task.canvas_id,
        "canvas_project_id": _get_task_canvas_project_id(task),
        "image_id": primary_image.id if primary_image else None,
            "user_id": user_external_id(task.user),
            "username": task.user.username if task.user else "",
            "avatar_url": resolve_user_avatar_url(task.user, cos_config=cos_config),
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
        "used_fallback_api": bool(task.used_fallback_api),
        "created_at": task.created_at,
        "request_started_at": task.request_started_at,
        "request_finished_at": task.request_finished_at,
        "run_time": _calculate_task_run_time(task),
        "error_message": (
            (task.error_message or "")
            if include_provider_diagnostics
            else format_generation_public_error_message(task.error_message)
        ),
        "provider_error_message": (task.provider_error_message or "") if include_provider_diagnostics else "",
        "images": visible_images,
        "api_attempts": (
            _serialize_task_api_attempts(
                resolved_attempts or [],
                request_previews=request_previews,
            )
            if include_provider_diagnostics
            else []
        ),
    }


def _serialize_prompt_history_detail(row: PromptHistory, *, cos_config) -> dict:
    source_asset = serialize_asset_urls(row.source_image or "", cos_config=cos_config)
    db = Session.object_session(row)
    user = db.query(User).filter(User.id == row.user_id).first() if db else None
    prompt_history_mode = (row.mode or "").strip()
    return {
        "history_id": row.id,
        "item_type": "prompt_history",
        "display_id": f"{PROMPT_HISTORY_MODE_TO_DISPLAY_PREFIX.get(prompt_history_mode, 'PR')}-{row.id}",
        "task_id": None,
        "image_id": -row.id,
        "user_id": user_external_id(user),
        "username": user.username if user else "",
        "avatar_url": resolve_user_avatar_url(user, cos_config=cos_config),
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
        "task_type": _resolve_prompt_history_task_type(prompt_history_mode),
        "model": _resolve_prompt_history_model(prompt_history_mode),
        "source": "web",
        "mode": prompt_history_mode or PROMPT_REVERSE_MODE,
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
        "used_fallback_api": False,
        "created_at": row.created_at,
        "error_message": "",
        "images": [],
        "api_attempts": [],
    }


def _serialize_prompt_optimize_detail(row: PromptOptimizeTask, *, cos_config) -> dict:
    source_asset = serialize_asset_urls(row.source_image or "", cos_config=cos_config)
    reference_assets = [serialize_asset_urls(ref, cos_config=cos_config) for ref in _parse_refs(row.reference_images_json)]
    db = Session.object_session(row)
    user = db.query(User).filter(User.id == row.user_id).first() if db else None
    optimized_prompt = (row.optimized_prompt or row.original_prompt or "").strip()
    return {
        "history_id": row.id,
        "item_type": PROMPT_OPTIMIZE_HISTORY_ITEM_TYPE,
        "style_id": row.style_id,
        "style_name": (row.style_name_snapshot or "").strip(),
        "display_id": f"PO-{row.id}",
        "task_id": None,
        "image_id": -(PROMPT_OPTIMIZE_IMAGE_ID_OFFSET + int(row.id)),
        "user_id": user_external_id(user),
        "username": user.username if user else "",
        "avatar_url": resolve_user_avatar_url(user, cos_config=cos_config),
        "is_pinned": False,
        "pinned_at": None,
        "image_url": "",
        "preview_url": "",
        "thumb_url": "",
        "status": (row.status or "success").strip() or "success",
        "image_format": "",
        "image_size_bytes": 0,
        "task_is_deleted": False,
        "is_soft_deleted": False,
        "task_type": TASK_TYPE_PROMPT_OPTIMIZE,
        "model": PROMPT_OPTIMIZE_MODEL,
        "source": (row.source or "web").strip() or "web",
        "mode": PROMPT_OPTIMIZE_MODE,
        "prompt": optimized_prompt,
        "reference_images": [asset["image_url"] for asset in reference_assets],
        "reference_image_thumbs": [asset["thumb_url"] for asset in reference_assets],
        "source_image": source_asset["image_url"],
        "source_image_thumb": source_asset["thumb_url"],
        "mask_image": "",
        "mask_image_thumb": "",
        "num_images": 0,
        "size": "-",
        "resolution": "",
        "custom_size": "",
        "credit_cost": int(row.credit_cost or 0),
        "used_fallback_api": False,
        "created_at": row.created_at,
        "error_message": "",
        "images": [],
        "api_attempts": [],
    }


def get_user_history(
    db: Session,
    user_id: int,
    page: int = 1,
    page_size: int = 20,
    current_user: User | None = None,
    respect_pins: bool = True,
    include_prompt_reverse: bool = True,
    mode: str | None = None,
    source: str | None = None,
    model: str | None = None,
    prompt: str | None = None,
    status: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    board_id: int | None = None,
    board_scope: str | None = None,
):
    cos_config = get_optional_cos_config(db)
    scene_type_map: dict[str, str] = {}
    if mode in {TASK_TYPE_TEXT_GENERATE, TASK_TYPE_IMAGE_EDIT}:
        scene_type_map = get_task_scene_type_map(db)
    current_user = current_user if current_user and current_user.id == user_id else db.query(User).filter(User.id == user_id).first()
    current_user_external_id = user_external_id(current_user)
    current_username = current_user.username if current_user else ""
    current_avatar_url = resolve_user_avatar_url(current_user, cos_config=cos_config)
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
        .options(
            selectinload(Image.task).options(
                selectinload(Task.images),
                lazyload(Task.api_attempts),
            )
        )
        .filter(Task.user_id == user_id)
        .filter(Task.is_deleted.is_(False))
        .filter(Task.canvas_id.is_(None))
        .filter(Image.is_deleted.is_(False))
    )
    prompt_reverse_query = None
    prompt_optimize_query = None
    if include_prompt_reverse:
        prompt_reverse_query = (
            db.query(PromptHistory)
            .filter(
                PromptHistory.user_id == user_id,
                PromptHistory.mode == PROMPT_REVERSE_MODE,
            )
        )
        prompt_optimize_query = (
            db.query(PromptOptimizeTask)
            .filter(PromptOptimizeTask.user_id == user_id)
        )
    if board_scope == "default":
        image_query = image_query.filter(Task.board_id.is_(None))
        prompt_reverse_query = None
        prompt_optimize_query = None
    elif board_id is not None:
        validate_user_board_id(db, user_id, board_id)
        image_query = image_query.filter(Task.board_id == board_id)
        prompt_reverse_query = None
        prompt_optimize_query = None
    if mode:
        if mode == TASK_TYPE_PROMPT_REVERSE:
            image_query = image_query.filter(Task.id.is_(None))
            prompt_optimize_query = None
        elif mode == TASK_TYPE_PROMPT_OPTIMIZE:
            image_query = image_query.filter(Task.id.is_(None))
            prompt_reverse_query = None
        elif mode == TASK_TYPE_INPAINT:
            image_query = image_query.filter(or_(Task.mode == "inpaint", Task.model == "inpaint"))
            prompt_reverse_query = None
            prompt_optimize_query = None
        elif mode == TASK_TYPE_SMART_CUTOUT:
            image_query = image_query.filter(or_(Task.mode == "smart_cutout", Task.model == "smart_cutout"))
            prompt_reverse_query = None
            prompt_optimize_query = None
        elif mode == TASK_TYPE_TEXT_GENERATE:
            text_generate_models = [key for key, value in scene_type_map.items() if value == "generate"]
            image_query = image_query.filter(Task.mode == "generate")
            image_query = image_query.filter(Task.model.in_(text_generate_models)) if text_generate_models else image_query.filter(Task.id.is_(None))
            prompt_reverse_query = None
            prompt_optimize_query = None
        elif mode == TASK_TYPE_IMAGE_EDIT:
            image_edit_models = [key for key, value in scene_type_map.items() if value == "image_edit"]
            image_query = image_query.filter(Task.mode == "generate")
            image_query = image_query.filter(Task.model.in_(image_edit_models)) if image_edit_models else image_query.filter(Task.id.is_(None))
            prompt_reverse_query = None
            prompt_optimize_query = None
        else:
            image_query = image_query.filter(Task.mode == mode)
            if mode not in PROMPT_HISTORY_MODES:
                prompt_reverse_query = None
            if mode != TASK_TYPE_PROMPT_OPTIMIZE:
                prompt_optimize_query = None
    if source:
        image_query = image_query.filter(Task.source == source)
        if source != "web":
            prompt_reverse_query = None
        if prompt_optimize_query is not None:
            prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.source == source)
    if model:
        image_query = image_query.filter(Task.model == model)
        if model != PROMPT_REVERSE_MODEL:
            prompt_reverse_query = None
        if model != PROMPT_OPTIMIZE_MODEL:
            prompt_optimize_query = None
    if prompt:
        keyword = prompt.strip()
        if keyword:
            image_query = image_query.filter(Task.prompt.ilike(f"%{keyword}%"))
            if prompt_reverse_query is not None:
                prompt_reverse_query = prompt_reverse_query.filter(PromptHistory.prompt.ilike(f"%{keyword}%"))
            if prompt_optimize_query is not None:
                prompt_optimize_query = prompt_optimize_query.filter(or_(
                    PromptOptimizeTask.optimized_prompt.ilike(f"%{keyword}%"),
                    PromptOptimizeTask.original_prompt.ilike(f"%{keyword}%"),
                ))
    if status:
        if status == "processing":
            image_query = image_query.filter(Image.status == "pending", Task.status == "processing")
            prompt_reverse_query = None
            prompt_optimize_query = None
        elif status == "pending":
            image_query = image_query.filter(Image.status == "pending", Task.status.in_(["pending", "queued"]))
            prompt_reverse_query = None
            prompt_optimize_query = None
        elif status == "failed":
            image_query = image_query.filter(or_(Image.status == "failed", and_(Image.status == "pending", Task.status == "failed")))
            prompt_reverse_query = None
            prompt_optimize_query = None
        else:
            image_query = image_query.filter(Image.status == status)
            if prompt_optimize_query is not None:
                prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.status == status)
    if start_date:
        image_query = image_query.filter(Task.created_at >= start_date)
        if prompt_reverse_query is not None:
            prompt_reverse_query = prompt_reverse_query.filter(PromptHistory.created_at >= start_date)
        if prompt_optimize_query is not None:
            prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.created_at >= start_date)
    if end_date:
        image_query = image_query.filter(Task.created_at <= end_date)
        if prompt_reverse_query is not None:
            prompt_reverse_query = prompt_reverse_query.filter(PromptHistory.created_at <= end_date)
        if prompt_optimize_query is not None:
            prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.created_at <= end_date)
    start_index = (page - 1) * page_size
    fetch_limit = start_index + page_size
    if respect_pins:
        images = image_query.order_by(Task.created_at.desc(), Image.id.desc()).all()
        prompt_reverse_rows = (
            prompt_reverse_query.order_by(PromptHistory.created_at.desc(), PromptHistory.id.desc()).all()
            if prompt_reverse_query is not None
            else []
        )
        prompt_optimize_rows = (
            prompt_optimize_query.order_by(PromptOptimizeTask.created_at.desc(), PromptOptimizeTask.id.desc()).all()
            if prompt_optimize_query is not None
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
        prompt_optimize_rows = (
            prompt_optimize_query
            .order_by(PromptOptimizeTask.created_at.desc(), PromptOptimizeTask.id.desc())
            .limit(fetch_limit)
            .all()
            if prompt_optimize_query is not None
            else []
        )
    task_ids = list({int(image.task_id) for image in images if image.task_id})
    refunded_task_ids = _get_refunded_task_ids(db, task_ids)
    if not scene_type_map:
        scene_type_map = get_task_scene_type_subset(
            db,
            {
                (image.task.model or "").strip()
                for image in images
                if image.task and (image.task.model or "").strip()
            },
        )
    task_shared_payloads: dict[int, dict] = {}
    items = []
    for image in images:
        task = image.task
        task_id = int(task.id)
        shared_payload = task_shared_payloads.get(task_id)
        if shared_payload is None:
            task_credit_cost = int(task.credit_cost or 0)
            source_asset = serialize_asset_urls(task.source_image or "", cos_config=cos_config)
            mask_asset = serialize_asset_urls(task.mask_image or "", cos_config=cos_config)
            reference_assets = [serialize_asset_urls(ref, cos_config=cos_config) for ref in _parse_refs(task.reference_images)]
            shared_payload = {
                "display_id": task_external_id(task),
                "canvas_project_id": _get_task_canvas_project_id(task),
                "task_type": resolve_task_type_for_task(task, scene_type_map=scene_type_map),
                "source": task.source or "web",
                "mode": task.mode or "generate",
                "prompt": task.prompt or "",
                "reference_images": [asset["image_url"] for asset in reference_assets],
                "reference_image_thumbs": [asset["thumb_url"] for asset in reference_assets],
                "source_image": source_asset["image_url"],
                "source_image_thumb": source_asset["thumb_url"],
                "mask_image": mask_asset["image_url"],
                "mask_image_thumb": mask_asset["thumb_url"],
                "task_credit_cost": task_credit_cost,
                "credit_refunded": bool(
                    task.status == "failed"
                    and task_credit_cost > 0
                    and task_id in refunded_task_ids
                ),
                "visible_images": _serialize_history_images(
                    task.images,
                    cos_config=cos_config,
                    public_error_message=True,
                ),
            }
            task_shared_payloads[task_id] = shared_payload
        image_payload = serialize_image(image, cos_config=cos_config, public_error_message=True)
        is_pinned, pinned_at = _serialize_history_pin(history_pin_map.get(_build_history_pin_key("task", image_id=image.id)))
        items.append({
            "history_id": None,
            "item_type": "task",
            "display_id": shared_payload["display_id"],
            "task_id": shared_payload["display_id"],
            "canvas_id": task.canvas_id,
            "canvas_project_id": shared_payload["canvas_project_id"],
            "image_id": image.id,
            "user_id": current_user_external_id,
            "username": current_username,
            "avatar_url": current_avatar_url,
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
            "task_type": shared_payload["task_type"],
            "model": task.model or "",
            "source": shared_payload["source"],
            "mode": shared_payload["mode"],
            "prompt": shared_payload["prompt"],
            "reference_images": shared_payload["reference_images"],
            "reference_image_thumbs": shared_payload["reference_image_thumbs"],
            "source_image": shared_payload["source_image"],
            "source_image_thumb": shared_payload["source_image_thumb"],
            "mask_image": shared_payload["mask_image"],
            "mask_image_thumb": shared_payload["mask_image_thumb"],
            "num_images": task.num_images or 1,
            "size": task.size or "",
            "resolution": task.resolution or "",
            "custom_size": task.custom_size or "",
            "credit_cost": shared_payload["task_credit_cost"],
            "credit_refunded": shared_payload["credit_refunded"],
            "created_at": task.created_at,
            "error_message": format_generation_public_error_message(task.error_message),
            "provider_error_message": "",
            "images": shared_payload["visible_images"],
        })

    for row in prompt_reverse_rows:
        source_asset = serialize_asset_urls(row.source_image or "", cos_config=cos_config)
        prompt_history_mode = (row.mode or "").strip()
        is_pinned, pinned_at = _serialize_history_pin(history_pin_map.get(_build_history_pin_key("prompt_history", history_id=row.id)))
        items.append({
            "history_id": row.id,
            "item_type": "prompt_history",
            "display_id": f"{PROMPT_HISTORY_MODE_TO_DISPLAY_PREFIX.get(prompt_history_mode, 'PR')}-{row.id}",
            "task_id": None,
            "image_id": -row.id,
            "user_id": current_user_external_id,
            "username": current_username,
            "avatar_url": current_avatar_url,
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
            "task_type": _resolve_prompt_history_task_type(prompt_history_mode),
            "model": _resolve_prompt_history_model(prompt_history_mode),
            "source": "web",
            "mode": prompt_history_mode or PROMPT_REVERSE_MODE,
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

    for row in prompt_optimize_rows:
        item = _serialize_prompt_optimize_detail(row, cos_config=cos_config)
        is_pinned, pinned_at = _resolve_prompt_optimize_pin(history_pin_map, row)
        item["is_pinned"] = is_pinned
        item["pinned_at"] = pinned_at
        item["user_id"] = current_user_external_id
        item["username"] = current_username
        item["avatar_url"] = current_avatar_url
        items.append(item)

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
    candidate_keys = [item_key]

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
                PromptHistory.mode.in_(PROMPT_HISTORY_MODES),
            )
            .first()
        )
        if not prompt_history_exists:
            raise LookupError("history_item_not_found")
    elif item_type == PROMPT_OPTIMIZE_HISTORY_ITEM_TYPE:
        if not isinstance(history_id, int):
            raise ValueError("invalid_history_pin_target")
        prompt_optimize_task = (
            db.query(PromptOptimizeTask)
            .filter(
                PromptOptimizeTask.id == history_id,
                PromptOptimizeTask.user_id == user_id,
            )
            .first()
        )
        if not prompt_optimize_task:
            raise LookupError("history_item_not_found")
        candidate_keys = _build_prompt_optimize_pin_keys(prompt_optimize_task)
    else:
        raise ValueError("invalid_history_pin_target")

    pins = (
        db.query(HistoryPin)
        .filter(HistoryPin.user_id == user_id, HistoryPin.item_key.in_(candidate_keys))
        .all()
    )
    if pins:
        for pin in pins:
            db.delete(pin)
        db.commit()
        return {"is_pinned": False, "pinned_at": None}

    pin = HistoryPin(
        user_id=user_id,
        item_type=item_type,
        item_key=item_key,
        image_id=image_id if item_type == "task" else None,
        history_id=history_id if item_type in {"prompt_history", PROMPT_OPTIMIZE_HISTORY_ITEM_TYPE} else None,
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
    canvas_task_filter: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    include_unsafe_tasks: bool = True,
):
    cos_config = get_optional_cos_config(db)
    scene_type_map = get_task_scene_type_map(db)
    visible_user_clause = [User.role != "superadmin"]
    if user_id:
        visible_user_clause.append(User.id == user_id)

    task_query = (
        db.query(Task)
        .join(User, User.id == Task.user_id)
        .filter(*visible_user_clause)
        .filter(_exclude_example_template_seed_task_clause())
    )
    reverse_query = (
        db.query(CreditLog)
        .join(User, User.id == CreditLog.user_id)
        .filter(
            *visible_user_clause,
            CreditLog.type == "consume",
            CreditLog.description == PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION,
        )
    )
    prompt_optimize_query = (
        db.query(PromptOptimizeTask)
        .join(User, User.id == PromptOptimizeTask.user_id)
        .filter(*visible_user_clause)
    )

    if status:
        task_query = task_query.filter(Task.status == status)
        if status != "success":
            reverse_query = reverse_query.filter(CreditLog.id.is_(None))
            prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.id.is_(None))
    if source:
        task_query = task_query.filter(Task.source == source)
        if source != "web":
            reverse_query = reverse_query.filter(CreditLog.id.is_(None))
        prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.source == source)
    if model:
        task_query = task_query.filter(Task.model == model)
        if model != PROMPT_REVERSE_MODEL:
            reverse_query = reverse_query.filter(CreditLog.id.is_(None))
        if model != PROMPT_OPTIMIZE_MODEL:
            prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.id.is_(None))
    if canvas_task_filter == "canvas":
        task_query = task_query.filter(Task.canvas_id.is_not(None))
        reverse_query = reverse_query.filter(CreditLog.id.is_(None))
        prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.id.is_(None))
    elif canvas_task_filter == "non_canvas":
        task_query = task_query.filter(Task.canvas_id.is_(None))
    if not include_unsafe_tasks:
        task_query = task_query.filter(build_exclude_content_safety_failed_task_clause(Task.status, Task.error_message))
    if mode:
        if mode == TASK_TYPE_PROMPT_REVERSE:
            task_query = task_query.filter(Task.id.is_(None))
            prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.id.is_(None))
        elif mode == TASK_TYPE_PROMPT_OPTIMIZE:
            task_query = task_query.filter(Task.id.is_(None))
            reverse_query = reverse_query.filter(CreditLog.id.is_(None))
        elif mode == TASK_TYPE_INPAINT:
            task_query = task_query.filter(or_(Task.mode == "inpaint", Task.model == "inpaint"))
        elif mode == TASK_TYPE_SMART_CUTOUT:
            task_query = task_query.filter(or_(Task.mode == "smart_cutout", Task.model == "smart_cutout"))
            reverse_query = reverse_query.filter(CreditLog.id.is_(None))
            prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.id.is_(None))
        elif mode == TASK_TYPE_TEXT_GENERATE:
            text_generate_models = [key for key, value in scene_type_map.items() if value == "generate"]
            task_query = task_query.filter(Task.mode == "generate")
            task_query = task_query.filter(Task.model.in_(text_generate_models)) if text_generate_models else task_query.filter(Task.id.is_(None))
            reverse_query = reverse_query.filter(CreditLog.id.is_(None))
            prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.id.is_(None))
        elif mode == TASK_TYPE_IMAGE_EDIT:
            image_edit_models = [key for key, value in scene_type_map.items() if value == "image_edit"]
            task_query = task_query.filter(Task.mode == "generate")
            task_query = task_query.filter(Task.model.in_(image_edit_models)) if image_edit_models else task_query.filter(Task.id.is_(None))
            reverse_query = reverse_query.filter(CreditLog.id.is_(None))
            prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.id.is_(None))
        else:
            task_query = task_query.filter(Task.mode == mode)
            if mode != PROMPT_REVERSE_MODE:
                reverse_query = reverse_query.filter(CreditLog.id.is_(None))
            if mode != PROMPT_OPTIMIZE_MODE:
                prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.id.is_(None))
    if start_date:
        task_query = task_query.filter(Task.created_at >= start_date)
        reverse_query = reverse_query.filter(CreditLog.created_at >= start_date)
        prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.created_at >= start_date)
    if end_date:
        task_query = task_query.filter(Task.created_at <= end_date)
        reverse_query = reverse_query.filter(CreditLog.created_at <= end_date)
        prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.created_at <= end_date)

    task_total = int(task_query.order_by(None).with_entities(func.count(Task.id)).scalar() or 0)
    reverse_total = int(reverse_query.order_by(None).with_entities(func.count(CreditLog.id)).scalar() or 0)
    prompt_optimize_total = int(
        prompt_optimize_query.order_by(None).with_entities(func.count(PromptOptimizeTask.id)).scalar() or 0
    )
    total = task_total + reverse_total + prompt_optimize_total

    task_credit_total = int(
        task_query.order_by(None).with_entities(func.coalesce(func.sum(Task.credit_cost), 0)).scalar() or 0
    )
    refunded_task_ids_query = (
        db.query(CreditLog.task_id.label("task_id"))
        .filter(
            CreditLog.task_id.is_not(None),
            CreditLog.type == "allocate",
            CreditLog.description.in_(TASK_CREDIT_REFUND_DESCRIPTIONS),
        )
        .distinct()
        .subquery()
    )
    refunded_credit_total = int(
        task_query.order_by(None)
        .with_entities(Task.id, Task.credit_cost, Task.status)
        .join(refunded_task_ids_query, Task.id == refunded_task_ids_query.c.task_id)
        .filter(Task.status == "failed", Task.credit_cost > 0)
        .with_entities(func.coalesce(func.sum(Task.credit_cost), 0))
        .scalar()
        or 0
    )
    reverse_credit_total = int(
        reverse_query.with_entities(func.coalesce(func.sum(-CreditLog.amount), 0)).scalar() or 0
    )
    prompt_optimize_credit_total = int(
        prompt_optimize_query.with_entities(func.coalesce(func.sum(PromptOptimizeTask.credit_cost), 0)).scalar() or 0
    )
    total_credit_cost = task_credit_total - refunded_credit_total + reverse_credit_total + prompt_optimize_credit_total

    start_index = (page - 1) * page_size
    fetch_limit = start_index + page_size
    tasks = (
        task_query
        .options(
            load_only(
                Task.id,
                Task.business_id,
                Task.user_id,
                Task.canvas_id,
                Task.model,
                Task.source,
                Task.mode,
                Task.prompt,
                Task.num_images,
                Task.size,
                Task.resolution,
                Task.custom_size,
                Task.reference_images,
                Task.credit_cost,
                Task.status,
                Task.error_message,
                Task.provider_error_message,
                Task.used_fallback_api,
                Task.is_deleted,
                Task.created_at,
            ),
            selectinload(Task.user).load_only(
                User.id,
                User.business_id,
                User.username,
                User.avatar_url,
            ),
            selectinload(Task.canvas).load_only(UserCanvas.id, UserCanvas.project_id),
            lazyload(Task.images),
            lazyload(Task.api_attempts),
        )
        .order_by(Task.created_at.desc(), Task.id.desc())
        .limit(fetch_limit)
        .all()
    )
    reverse_logs = (
        reverse_query
        .order_by(CreditLog.created_at.desc(), CreditLog.id.desc())
        .limit(fetch_limit)
        .all()
    )
    prompt_optimize_rows = (
        prompt_optimize_query
        .order_by(PromptOptimizeTask.created_at.desc(), PromptOptimizeTask.id.desc())
        .limit(fetch_limit)
        .all()
    )
    refunded_task_ids = _get_refunded_task_ids(db, [task.id for task in tasks])
    deleted_image_count_map = {
        int(task_id): int(count)
        for task_id, count in (
            db.query(Image.task_id, func.count(Image.id))
            .filter(
                Image.task_id.in_([task.id for task in tasks]),
                Image.is_deleted.is_(True),
            )
            .group_by(Image.task_id)
            .all()
            if tasks
            else []
        )
    }

    user_cache: dict[int, dict[str, str]] = {}

    def _cache_user(user: User | None, fallback_user_id: int) -> dict[str, str]:
        cached = user_cache.get(fallback_user_id)
        if cached:
            return cached
        payload = {
            "user_id": user_external_id(user),
            "username": user.username if user else "未知",
            "avatar_url": resolve_user_avatar_url(user, cos_config=cos_config),
        }
        user_cache[fallback_user_id] = payload
        return payload

    page_user_ids = {task.user_id for task in tasks} | {log.user_id for log in reverse_logs} | {row.user_id for row in prompt_optimize_rows}
    if page_user_ids:
        for user in db.query(User).filter(User.id.in_(page_user_ids)).all():
            _cache_user(user, user.id)

    items = []
    for task in tasks:
        user_info = _cache_user(task.user, task.user_id)
        soft_deleted_count = deleted_image_count_map.get(int(task.id), 0)

        items.append({
            "item_type": "task",
            "task_id": task_external_id(task),
            "canvas_id": task.canvas_id,
            "canvas_project_id": _get_task_canvas_project_id(task),
            "history_id": None,
            "display_id": task_external_id(task),
            "user_id": user_info["user_id"],
            "username": user_info["username"],
            "avatar_url": user_info["avatar_url"],
            "task_type": resolve_task_type_for_task(task, scene_type_map=scene_type_map),
            "model": task.model or "",
            "source": task.source or "web",
            "mode": task.mode or "generate",
            "prompt": task.prompt or "",
            "reference_images": [],
            "num_images": task.num_images or 1,
            "size": task.size or "",
            "resolution": task.resolution or "",
            "custom_size": task.custom_size or "",
            "credit_cost": 0 if task.id in refunded_task_ids else int(task.credit_cost or 0),
            "status": task.status,
            "error_message": task.error_message or "",
            "provider_error_message": task.provider_error_message or "",
            "task_is_deleted": bool(task.is_deleted),
            "is_soft_deleted": soft_deleted_count > 0,
            "soft_deleted_count": soft_deleted_count,
            "created_at": task.created_at,
            "images": [],
        })

    for log in reverse_logs:
        user_info = _cache_user(None, log.user_id)

        items.append({
            "item_type": "prompt_history",
            "task_id": None,
            "history_id": log.id,
            "display_id": f"PR-{log.id}",
            "user_id": user_info["user_id"],
            "username": user_info["username"],
            "avatar_url": user_info["avatar_url"],
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

    for row in prompt_optimize_rows:
        user_info = _cache_user(None, row.user_id)

        items.append({
            "item_type": PROMPT_OPTIMIZE_HISTORY_ITEM_TYPE,
            "task_id": None,
            "history_id": row.id,
            "style_id": row.style_id,
            "style_name": (row.style_name_snapshot or "").strip(),
            "display_id": f"PO-{row.id}",
            "user_id": user_info["user_id"],
            "username": user_info["username"],
            "avatar_url": user_info["avatar_url"],
            "task_type": TASK_TYPE_PROMPT_OPTIMIZE,
            "model": PROMPT_OPTIMIZE_MODEL,
            "source": (row.source or "web").strip() or "web",
            "mode": PROMPT_OPTIMIZE_MODE,
            "prompt": (row.optimized_prompt or row.original_prompt or "").strip(),
            "reference_images": _parse_refs(row.reference_images_json),
            "num_images": 0,
            "size": "-",
            "resolution": "",
            "custom_size": "",
            "credit_cost": int(row.credit_cost or 0),
            "status": (row.status or "success").strip() or "success",
            "error_message": "",
            "task_is_deleted": False,
            "is_soft_deleted": False,
            "soft_deleted_count": 0,
            "created_at": row.created_at,
            "images": [],
        })

    items.sort(key=lambda item: item["created_at"] or datetime.min, reverse=True)
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
    exclude_failed: bool = False,
    used_fallback_api: bool | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    board_id: int | None = None,
    board_scope: str | None = None,
    include_provider_diagnostics: bool = True,
):
    cos_config = get_optional_cos_config(db)
    scene_type_map = get_task_scene_type_map(db)
    running_statuses = ["pending", "queued", "processing"]
    restricted_user_ids = _get_restricted_user_ids(db) if not include_restricted_users else []
    task_query = (
        db.query(Task)
        .options(
            selectinload(Task.images),
            selectinload(Task.canvas),
            lazyload(Task.api_attempts),
        )
        .filter(_exclude_example_template_seed_task_clause())
    )
    if not include_restricted_users:
        if restricted_user_ids:
            task_query = task_query.filter(Task.user_id.notin_(restricted_user_ids))
    if not include_deleted_tasks:
        task_query = task_query.filter(Task.is_deleted.is_(False))
    prompt_reverse_query = None
    prompt_optimize_query = None
    if include_prompt_reverse:
        prompt_reverse_query = (
            db.query(PromptHistory)
            .filter(
                PromptHistory.mode == PROMPT_REVERSE_MODE,
            )
        )
        if not include_restricted_users:
            if restricted_user_ids:
                prompt_reverse_query = prompt_reverse_query.filter(PromptHistory.user_id.notin_(restricted_user_ids))
        prompt_optimize_query = (
            db.query(PromptOptimizeTask)
        )
        if not include_restricted_users:
            if restricted_user_ids:
                prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.user_id.notin_(restricted_user_ids))

    if user_id is not None:
        task_query = task_query.filter(Task.user_id == user_id)
        if prompt_reverse_query is not None:
            prompt_reverse_query = prompt_reverse_query.filter(PromptHistory.user_id == user_id)
        if prompt_optimize_query is not None:
            prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.user_id == user_id)
    if board_scope == "default":
        task_query = task_query.filter(Task.board_id.is_(None))
        prompt_reverse_query = None
        prompt_optimize_query = None
    elif board_id is not None:
        if user_id is not None:
            validate_user_board_id(db, user_id, board_id)
        task_query = task_query.filter(Task.board_id == board_id)
        prompt_reverse_query = None
        prompt_optimize_query = None
    if mode:
        if mode == TASK_TYPE_PROMPT_REVERSE:
            task_query = task_query.filter(Task.id.is_(None))
            prompt_optimize_query = None
        elif mode == TASK_TYPE_PROMPT_OPTIMIZE:
            task_query = task_query.filter(Task.id.is_(None))
            prompt_reverse_query = None
        elif mode == TASK_TYPE_INPAINT:
            task_query = task_query.filter(or_(Task.mode == "inpaint", Task.model == "inpaint"))
        elif mode == TASK_TYPE_SMART_CUTOUT:
            task_query = task_query.filter(or_(Task.mode == "smart_cutout", Task.model == "smart_cutout"))
            prompt_reverse_query = None
            prompt_optimize_query = None
        elif mode == TASK_TYPE_TEXT_GENERATE:
            text_generate_models = [key for key, value in scene_type_map.items() if value == "generate"]
            task_query = task_query.filter(Task.mode == "generate")
            task_query = task_query.filter(Task.model.in_(text_generate_models)) if text_generate_models else task_query.filter(Task.id.is_(None))
            prompt_reverse_query = None
            prompt_optimize_query = None
        elif mode == TASK_TYPE_IMAGE_EDIT:
            image_edit_models = [key for key, value in scene_type_map.items() if value == "image_edit"]
            task_query = task_query.filter(Task.mode == "generate")
            task_query = task_query.filter(Task.model.in_(image_edit_models)) if image_edit_models else task_query.filter(Task.id.is_(None))
            prompt_reverse_query = None
            prompt_optimize_query = None
        else:
            task_query = task_query.filter(Task.mode == mode)
            if mode not in PROMPT_HISTORY_MODES:
                prompt_reverse_query = None
            if mode != TASK_TYPE_PROMPT_OPTIMIZE:
                prompt_optimize_query = None
    if source:
        task_query = task_query.filter(Task.source == source)
        if source != "web":
            prompt_reverse_query = None
        if prompt_optimize_query is not None:
            prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.source == source)
    if model:
        task_query = task_query.filter(Task.model == model)
        if model != PROMPT_REVERSE_MODEL:
            prompt_reverse_query = None
        if model != PROMPT_OPTIMIZE_MODEL:
            prompt_optimize_query = None
    if prompt:
        keyword = prompt.strip()
        if keyword:
            task_query = task_query.filter(Task.prompt.ilike(f"%{keyword}%"))
            if prompt_reverse_query is not None:
                prompt_reverse_query = prompt_reverse_query.filter(PromptHistory.prompt.ilike(f"%{keyword}%"))
            if prompt_optimize_query is not None:
                prompt_optimize_query = prompt_optimize_query.filter(or_(
                    PromptOptimizeTask.optimized_prompt.ilike(f"%{keyword}%"),
                    PromptOptimizeTask.original_prompt.ilike(f"%{keyword}%"),
                ))
    if used_fallback_api is not None:
        task_query = task_query.filter(Task.used_fallback_api.is_(bool(used_fallback_api)))
        prompt_reverse_query = None
        prompt_optimize_query = None
    if status:
        if status == "processing":
            task_query = task_query.filter(Task.status == "processing")
            prompt_reverse_query = None
            prompt_optimize_query = None
        elif status == "pending":
            task_query = task_query.filter(Task.status.in_(["pending", "queued"]))
            prompt_reverse_query = None
            prompt_optimize_query = None
        elif status == "failed":
            task_query = task_query.filter(or_(
                Task.status == "failed",
                Task.images.any(and_(Image.is_deleted.is_(False), Image.status == "failed")),
            ))
            prompt_reverse_query = None
            prompt_optimize_query = None
        else:
            task_query = task_query.filter(or_(
                Task.status == status,
                Task.images.any(and_(Image.is_deleted.is_(False), Image.status == status)),
            ))
            if prompt_optimize_query is not None:
                prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.status == status)
    if exclude_failed and status != "failed":
        task_query = task_query.filter(Task.status != "failed")
        if prompt_optimize_query is not None:
            prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.status != "failed")
    if start_date:
        task_query = task_query.filter(Task.created_at >= start_date)
        if prompt_reverse_query is not None:
            prompt_reverse_query = prompt_reverse_query.filter(PromptHistory.created_at >= start_date)
        if prompt_optimize_query is not None:
            prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.created_at >= start_date)
    if end_date:
        task_query = task_query.filter(Task.created_at <= end_date)
        if prompt_reverse_query is not None:
            prompt_reverse_query = prompt_reverse_query.filter(PromptHistory.created_at <= end_date)
        if prompt_optimize_query is not None:
            prompt_optimize_query = prompt_optimize_query.filter(PromptOptimizeTask.created_at <= end_date)

    start_index = (page - 1) * page_size
    fetch_limit = start_index + page_size + 1
    if exclude_failed and status == "failed":
        return {"total": 0, "items": []}
    prompt_reverse_rows = (
        prompt_reverse_query
        .order_by(PromptHistory.created_at.desc(), PromptHistory.id.desc())
        .limit(fetch_limit)
        .all()
        if prompt_reverse_query is not None
        else []
    )
    prompt_optimize_rows = (
        prompt_optimize_query
        .order_by(PromptOptimizeTask.created_at.desc(), PromptOptimizeTask.id.desc())
        .limit(fetch_limit)
        .all()
        if prompt_optimize_query is not None
        else []
    )
    task_candidate_limit = max(fetch_limit * 4, 80)
    max_task_candidate_limit = max(task_candidate_limit, 10000)
    images: list[Image] = []
    running_tasks: list[Task] = []
    tasks_without_images: list[Task] = []

    while True:
        images = []
        running_tasks = []
        tasks_without_images = []
        candidate_task_ids = [
            int(task_id)
            for (task_id,) in (
                task_query
                .enable_eagerloads(False)
                .with_entities(Task.id)
                .order_by(Task.created_at.desc(), Task.id.desc())
                .limit(task_candidate_limit)
                .all()
            )
        ]
        loaded_tasks = {
            int(task.id): task
            for task in (
                db.query(Task)
                .options(
                    load_only(
                        Task.id,
                        Task.business_id,
                        Task.user_id,
                        Task.board_id,
                        Task.canvas_id,
                        Task.model,
                        Task.source,
                        Task.mode,
                        Task.prompt,
                        Task.num_images,
                        Task.size,
                        Task.resolution,
                        Task.custom_size,
                        Task.reference_images,
                        Task.source_image,
                        Task.mask_image,
                        Task.credit_cost,
                        Task.status,
                        Task.error_message,
                        Task.provider_error_message,
                        Task.used_fallback_api,
                        Task.is_deleted,
                        Task.created_at,
                        Task.request_started_at,
                        Task.request_finished_at,
                    ),
                    selectinload(Task.images),
                    selectinload(Task.canvas),
                    lazyload(Task.api_attempts),
                )
                .filter(Task.id.in_(candidate_task_ids))
                .all()
            )
        } if candidate_task_ids else {}
        candidate_tasks = [
            loaded_tasks[task_id]
            for task_id in candidate_task_ids
            if task_id in loaded_tasks
        ]

        for task in candidate_tasks:
            visible_images = sorted(
                [image for image in task.images if not image.is_deleted],
                key=lambda image: image.id,
                reverse=True,
            )
            if exclude_failed:
                visible_images = [image for image in visible_images if image.status != "failed"]
            if status in {"processing", "pending"}:
                if not task.is_deleted:
                    running_tasks.append(task)
                continue
            if status == "failed":
                matching_images = [
                    image for image in visible_images
                    if image.status == "failed" or (image.status == "pending" and task.status == "failed")
                ]
                if matching_images:
                    images.extend(matching_images)
                elif not visible_images and task.status == "failed":
                    tasks_without_images.append(task)
                continue
            if status:
                matching_images = [image for image in visible_images if image.status == status]
                if matching_images:
                    images.extend(matching_images)
                elif not visible_images and task.status == status:
                    tasks_without_images.append(task)
                continue
            if task.status in running_statuses:
                if not task.is_deleted:
                    running_tasks.append(task)
            elif visible_images:
                images.extend(visible_images)
            elif not exclude_failed or task.status != "failed":
                tasks_without_images.append(task)

        task_item_count = len(images) + len(running_tasks) + len(tasks_without_images)
        if (
            task_item_count + len(prompt_reverse_rows) > fetch_limit
            or len(candidate_task_ids) < task_candidate_limit
            or task_candidate_limit >= max_task_candidate_limit
        ):
            break
        task_candidate_limit = min(task_candidate_limit * 2, max_task_candidate_limit)

    user_ids = (
        {image.task.user_id for image in images if image.task}
        | {task.user_id for task in running_tasks}
        | {task.user_id for task in tasks_without_images}
        | {row.user_id for row in prompt_reverse_rows}
        | {row.user_id for row in prompt_optimize_rows}
    )
    user_cache = {
        user.id: user
        for user in db.query(User).filter(User.id.in_(user_ids)).all()
    } if user_ids else {}
    failed_task_ids = {
        int(task.id)
        for task in (
            [image.task for image in images if image.task]
            + list(tasks_without_images)
        )
        if task
        and task.id
        and task.status == "failed"
        and int(task.credit_cost or 0) > 0
    }
    refunded_task_ids = _get_refunded_task_ids(db, list(failed_task_ids))
    items = []
    for image in images:
        task = image.task
        task_user = user_cache.get(task.user_id) if task else None
        task_credit_cost = int(task.credit_cost or 0) if task else 0
        credit_refunded = bool(task and task.id and int(task.id) in refunded_task_ids)
        image_payload = serialize_image(image, cos_config=cos_config)
        source_asset = serialize_asset_urls(task.source_image or "", cos_config=cos_config)
        mask_asset = serialize_asset_urls(task.mask_image or "", cos_config=cos_config)
        reference_assets = [serialize_asset_urls(ref, cos_config=cos_config) for ref in _parse_refs(task.reference_images)]
        visible_images = _serialize_history_images(
            task.images,
            cos_config=cos_config,
            public_error_message=not include_provider_diagnostics,
        )
        items.append({
            "history_id": None,
            "item_type": "task",
            "_task_db_id": task.id,
            "display_id": task_external_id(task),
            "task_id": task_external_id(task),
            "canvas_id": task.canvas_id if task else None,
            "canvas_project_id": _get_task_canvas_project_id(task),
            "image_id": image.id,
            "user_id": user_external_id(task_user),
            "username": task_user.username if task_user else "",
            "avatar_url": resolve_user_avatar_url(task_user, cos_config=cos_config),
            "is_pinned": False,
            "pinned_at": None,
            "image_url": image_payload["image_url"],
            "preview_url": image_payload["preview_url"],
            "thumb_url": image_payload["thumb_url"],
            "status": _resolve_history_card_status(task.status, image.status),
            "image_format": image_payload["image_format"],
            "image_size_bytes": image_payload["image_size_bytes"],
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
            "used_fallback_api": bool(task.used_fallback_api),
            "created_at": task.created_at,
            "request_started_at": task.request_started_at,
            "request_finished_at": task.request_finished_at,
            "run_time": _calculate_task_run_time(task),
            "error_message": (
                (task.error_message or "")
                if include_provider_diagnostics
                else format_generation_public_error_message(task.error_message)
            ),
            "provider_error_message": (task.provider_error_message or "") if include_provider_diagnostics else "",
            "images": visible_images,
            "api_attempts": [] if not include_provider_diagnostics else [],
        })

    for task in running_tasks:
        task_user = user_cache.get(task.user_id)
        source_asset = serialize_asset_urls(task.source_image or "", cos_config=cos_config)
        mask_asset = serialize_asset_urls(task.mask_image or "", cos_config=cos_config)
        reference_assets = [serialize_asset_urls(ref, cos_config=cos_config) for ref in _parse_refs(task.reference_images)]
        visible_images = _serialize_history_images(
            task.images,
            cos_config=cos_config,
            public_error_message=not include_provider_diagnostics,
        )
        primary_image = next((image for image in visible_images if not image.get("is_deleted")), None)
        items.append({
            "history_id": None,
            "item_type": "task",
            "_task_db_id": task.id,
            "display_id": task_external_id(task),
            "task_id": task_external_id(task),
            "canvas_id": task.canvas_id,
            "canvas_project_id": _get_task_canvas_project_id(task),
            "image_id": primary_image["id"] if primary_image else None,
            "user_id": user_external_id(task_user),
            "username": task_user.username if task_user else "",
            "avatar_url": resolve_user_avatar_url(task_user, cos_config=cos_config),
            "is_pinned": False,
            "pinned_at": None,
            "image_url": primary_image["image_url"] if primary_image else "",
            "preview_url": primary_image["preview_url"] if primary_image else "",
            "thumb_url": primary_image["thumb_url"] if primary_image else "",
            "status": task.status or "pending",
            "image_format": primary_image["image_format"] if primary_image else "",
            "image_size_bytes": primary_image["image_size_bytes"] if primary_image else 0,
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
            "credit_cost": int(task.credit_cost or 0),
            "credit_refunded": False,
            "used_fallback_api": bool(task.used_fallback_api),
            "created_at": task.created_at,
            "request_started_at": task.request_started_at,
            "request_finished_at": task.request_finished_at,
            "run_time": _calculate_task_run_time(task),
            "error_message": (
                (task.error_message or "")
                if include_provider_diagnostics
                else format_generation_public_error_message(task.error_message)
            ),
            "provider_error_message": (task.provider_error_message or "") if include_provider_diagnostics else "",
            "images": visible_images,
            "api_attempts": [] if not include_provider_diagnostics else [],
        })

    for task in tasks_without_images:
        task_user = user_cache.get(task.user_id)
        task_credit_cost = int(task.credit_cost or 0)
        credit_refunded = bool(task.id and int(task.id) in refunded_task_ids)
        source_asset = serialize_asset_urls(task.source_image or "", cos_config=cos_config)
        mask_asset = serialize_asset_urls(task.mask_image or "", cos_config=cos_config)
        reference_assets = [serialize_asset_urls(ref, cos_config=cos_config) for ref in _parse_refs(task.reference_images)]
        items.append({
            "history_id": None,
            "item_type": "task",
            "_task_db_id": task.id,
            "display_id": task_external_id(task),
            "task_id": task_external_id(task),
            "canvas_id": task.canvas_id,
            "canvas_project_id": _get_task_canvas_project_id(task),
            "image_id": None,
            "user_id": user_external_id(task_user),
            "username": task_user.username if task_user else "",
            "avatar_url": resolve_user_avatar_url(task_user, cos_config=cos_config),
            "is_pinned": False,
            "pinned_at": None,
            "image_url": "",
            "preview_url": "",
            "thumb_url": "",
            "status": task.status or "pending",
            "image_format": "",
            "image_size_bytes": 0,
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
            "used_fallback_api": bool(task.used_fallback_api),
            "created_at": task.created_at,
            "request_started_at": task.request_started_at,
            "request_finished_at": task.request_finished_at,
            "run_time": _calculate_task_run_time(task),
            "error_message": (
                (task.error_message or "")
                if include_provider_diagnostics
                else format_generation_public_error_message(task.error_message)
            ),
            "provider_error_message": (task.provider_error_message or "") if include_provider_diagnostics else "",
            "images": [],
            "api_attempts": [] if not include_provider_diagnostics else [],
        })

    for row in prompt_reverse_rows:
        row_user = user_cache.get(row.user_id)
        source_asset = serialize_asset_urls(row.source_image or "", cos_config=cos_config)
        prompt_history_mode = (row.mode or "").strip()
        items.append({
            "history_id": row.id,
            "item_type": "prompt_history",
            "display_id": f"{PROMPT_HISTORY_MODE_TO_DISPLAY_PREFIX.get(prompt_history_mode, 'PR')}-{row.id}",
            "task_id": None,
            "image_id": -row.id,
            "user_id": user_external_id(row_user),
            "username": row_user.username if row_user else "",
            "avatar_url": resolve_user_avatar_url(row_user, cos_config=cos_config),
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
            "task_type": _resolve_prompt_history_task_type(prompt_history_mode),
            "model": _resolve_prompt_history_model(prompt_history_mode),
            "source": "web",
            "mode": prompt_history_mode or PROMPT_REVERSE_MODE,
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
            "used_fallback_api": False,
            "created_at": row.created_at,
            "error_message": "",
            "images": [],
            "api_attempts": [],
        })

    for row in prompt_optimize_rows:
        item = _serialize_prompt_optimize_detail(row, cos_config=cos_config)
        row_user = user_cache.get(row.user_id)
        item["user_id"] = user_external_id(row_user)
        item["username"] = row_user.username if row_user else ""
        item["avatar_url"] = resolve_user_avatar_url(row_user, cos_config=cos_config)
        items.append(item)

    items.sort(key=lambda item: item.get("created_at") or datetime.min, reverse=True)
    page_items = items[start_index:start_index + page_size]
    for item in page_items:
        item.pop("_task_db_id", None)
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
            .options(selectinload(Task.images), selectinload(Task.canvas), selectinload(Task.user))
            .filter(Task.business_id == normalized_task_id)
            .first()
        )
        if not task:
            raise LookupError("task_not_found")
        return _serialize_task_history_detail(
            task,
            cos_config=cos_config,
            scene_type_map=scene_type_map,
            include_request_previews=True,
        )

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

    if item_type == PROMPT_OPTIMIZE_HISTORY_ITEM_TYPE:
        if not isinstance(history_id, int):
            raise ValueError("invalid_history_id")
        row = (
            db.query(PromptOptimizeTask)
            .filter(PromptOptimizeTask.id == history_id)
            .first()
        )
        if not row:
            raise LookupError("prompt_optimize_task_not_found")
        return _serialize_prompt_optimize_detail(row, cos_config=cos_config)

    raise ValueError("invalid_item_type")
