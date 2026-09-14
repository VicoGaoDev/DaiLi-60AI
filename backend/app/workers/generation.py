"""
AI image generation worker using configurable external APIs.

Supports multiple reference images (base64) and marks outputs as failed when
generation or persistence fails.
"""

import base64
import json
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta

import httpx
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import and_, or_

from app.config import settings
from app.database import SessionLocal
from app.models.external_api_config import ExternalApiConfig
from app.models.image import Image
from app.models.regenerate_log import RegenerateLog
from app.models.task import Task
from app.models.task_api_attempt import TaskApiAttempt
from app.services.business_id_service import task_external_id, user_external_id
from app.services.distributed_lock_service import acquire_redis_lock, release_redis_lock
from app.services.cos_service import build_object_key, load_image_bytes, upload_bytes_to_cos
from app.services.external_api_config_service import (
    build_external_poll_request_kwargs,
    build_external_request_kwargs,
    build_secret_variables,
    parse_http_statuses_json,
    parse_string_list_json,
    render_config,
    render_poll_config,
    resolve_scene_generation_configs,
    resolve_mapped_resolution,
    resolve_smart_cutout_prompt,
    SCENE_INPAINT,
    SCENE_SMART_CUTOUT,
    should_use_multipart_request,
)
from app.services.image_delivery_service import get_optional_cos_config, serialize_asset_urls
from app.services.task_service import refund_task_credit_for_generation_failure_if_needed
from app.utils.datetime_utils import now_local

logger = logging.getLogger(__name__)
MAX_ERROR_MESSAGE_LENGTH = 1800
MAX_RESPONSE_PREVIEW_LENGTH = 1200
MAX_ATTEMPT_RESPONSE_PREVIEW_LENGTH = 32768
QUEUE_UNAVAILABLE_ERROR = "任务队列暂不可用，请稍后重试"
TASK_LOCK_UNAVAILABLE_ERROR = "任务锁服务不可用，请稍后重试"
PROCESSING_TASK_TIMEOUT_ERROR = "任务处理超时，已自动关闭"
GENERIC_GENERATION_FAILURE_MESSAGES = {
    "生图失败",
    "生成失败",
    "生图失败，请反馈给我们处理",
    "生成失败，请重试",
}
INVALID_ASPECT_RATIO_ERROR_MESSAGE = "当前宽高比不受支持，请更换其他宽高比后重试"
INVALID_ASPECT_RATIO_ERROR_PATTERN = re.compile(
    r"n?put\.aspect_ratio is invalid|aspect_ratio is invalid",
    re.IGNORECASE,
)
ASYNC_PROVIDER_TIMEOUT_GRACE_SECONDS = 60
ASYNC_POLL_TRANSIENT_ERROR_RETRY_LIMIT = 3
ASYNC_POLL_RECOVERY_INTERVAL_SECONDS = 30
ASYNC_POLL_RECOVERY_BATCH_SIZE = 100
ASYNC_POLL_CLAIM_LEASE_SECONDS = max(int(settings.AI_TIMEOUT or 0) + 60, 120)
TASK_PROCESSING_LOCK_TIMEOUT_SECONDS = max(int(settings.AI_TIMEOUT or 0) + 600, 900)
SINGLE_IMAGE_LOCK_TIMEOUT_SECONDS = max(int(settings.AI_TIMEOUT or 0) + 600, 900)
SYNC_GENERATION_MAX_WORKERS = max(int(settings.SYNC_GENERATION_MAX_WORKERS or 0), 1)
_sync_generation_semaphore = threading.BoundedSemaphore(SYNC_GENERATION_MAX_WORKERS)
_async_poll_recovery_lock = threading.Lock()
_async_poll_recovery_started = False


@dataclass
class ApiAttemptRecord:
    api_config_id: int | None
    api_config_name: str
    attempt_index: int
    is_fallback: bool
    status: str
    http_status: int | None
    error_message: str
    duration_ms: int | None
    external_http_ms: int | None = None
    result_download_ms: int | None = None
    cos_upload_ms: int | None = None
    response_preview: str = ""


@dataclass
class ApiCallResult:
    result: tuple[bytes, str] | None
    error_message: str
    http_status_code: int | None
    attempts: list[ApiAttemptRecord]
    deferred: bool = False
    result_download_ms: int | None = None


@dataclass
class AsyncSubmitResult:
    provider_task_id: str | None
    provider_status: str
    error_message: str
    http_status_code: int | None
    duration_ms: int | None
    response_preview: str
    external_http_ms: int | None = None


def _clip_error_message(message: str) -> str:
    cleaned = (message or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= MAX_ERROR_MESSAGE_LENGTH:
        return cleaned
    return cleaned[:MAX_ERROR_MESSAGE_LENGTH] + "..."


def _is_invalid_aspect_ratio_error(message: str | None) -> bool:
    return bool(INVALID_ASPECT_RATIO_ERROR_PATTERN.search((message or "").strip()))


def _to_user_facing_generation_error(message: str | None, *, fallback: str = "生图失败") -> str:
    cleaned = _clip_error_message(message or "")
    if not cleaned:
        return fallback
    if _is_invalid_aspect_ratio_error(cleaned):
        return INVALID_ASPECT_RATIO_ERROR_MESSAGE
    return cleaned


def _resolve_generation_error(*messages: str, fallback: str = "生图失败") -> str:
    generic_message = ""
    for message in messages:
        cleaned = _clip_error_message(message or "")
        if not cleaned:
            continue
        if cleaned in GENERIC_GENERATION_FAILURE_MESSAGES:
            generic_message = generic_message or cleaned
            continue
        return _to_user_facing_generation_error(cleaned, fallback=fallback)
    return _to_user_facing_generation_error(generic_message, fallback=fallback)


def _clip_response_preview(payload: object) -> str:
    try:
        preview = json.dumps(payload, ensure_ascii=False)
    except Exception:
        preview = str(payload)
    preview = (preview or "").strip() or "(空响应)"
    if len(preview) <= MAX_RESPONSE_PREVIEW_LENGTH:
        return preview
    return preview[:MAX_RESPONSE_PREVIEW_LENGTH] + "..."


def _looks_like_base64(value: str) -> bool:
    cleaned = value.strip()
    if len(cleaned) < 1024 or len(cleaned) % 4 != 0:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9+/=\s]+", cleaned))


def _sanitize_response_preview_value(value: object, *, key: str = "") -> object:
    if isinstance(value, dict):
        return {
            str(item_key): _sanitize_response_preview_value(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_response_preview_value(item) for item in value]
    if not isinstance(value, str):
        return value

    stripped = value.strip()
    if stripped.startswith("data:") and ";base64," in stripped[:128]:
        return f"<data-url omitted, length={len(value)}>"

    normalized_key = key.lower()
    if normalized_key in {"b64_json", "base64", "b64", "data"} and len(stripped) > 256:
        return f"<base64 omitted, length={len(value)}>"
    if _looks_like_base64(stripped):
        return f"<base64 omitted, length={len(value)}>"
    return value


def _build_attempt_response_preview(payload: object) -> str:
    try:
        if isinstance(payload, (dict, list)):
            rendered = json.dumps(_sanitize_response_preview_value(payload), ensure_ascii=False)
        else:
            rendered = str(_sanitize_response_preview_value(payload))
    except Exception:
        rendered = str(payload)
    return rendered[:MAX_ATTEMPT_RESPONSE_PREVIEW_LENGTH]


def _measure_elapsed_seconds(started_perf: float | None) -> float | None:
    if started_perf is None:
        return None
    return round(max(time.perf_counter() - started_perf, 0), 2)


def _measure_elapsed_ms(started_perf: float | None) -> int | None:
    if started_perf is None:
        return None
    return max(int(round(max(time.perf_counter() - started_perf, 0) * 1000)), 0)


def _format_elapsed_fragment(elapsed_seconds: float | None) -> str:
    if elapsed_seconds is None:
        return ""
    return f"（实际耗时 {elapsed_seconds} 秒）"


def _should_use_fallback_api(_http_status: int | None, _error_message: str) -> bool:
    """主接口任意失败都切换备用接口。"""
    return True


def _classify_generation_request_exception(
    exc: Exception,
    *,
    started_perf: float | None,
) -> tuple[str, tuple[object, ...], str]:
    elapsed_seconds = _measure_elapsed_seconds(started_perf)
    elapsed_fragment = _format_elapsed_fragment(elapsed_seconds)

    if isinstance(exc, httpx.ConnectTimeout):
        return (
            "Generation API connect timed out after %s seconds (configured timeout=%s seconds)",
            (elapsed_seconds if elapsed_seconds is not None else "unknown", settings.AI_TIMEOUT),
            f"生图接口连接超时{elapsed_fragment or f'（配置超时 {settings.AI_TIMEOUT} 秒）'}",
        )
    if isinstance(exc, httpx.ReadTimeout):
        return (
            "Generation API read timed out after %s seconds (configured timeout=%s seconds)",
            (elapsed_seconds if elapsed_seconds is not None else "unknown", settings.AI_TIMEOUT),
            f"生图接口响应读取超时{elapsed_fragment or f'（配置超时 {settings.AI_TIMEOUT} 秒）'}",
        )
    if isinstance(exc, httpx.WriteTimeout):
        return (
            "Generation API write timed out after %s seconds (configured timeout=%s seconds)",
            (elapsed_seconds if elapsed_seconds is not None else "unknown", settings.AI_TIMEOUT),
            f"生图接口请求发送超时{elapsed_fragment or f'（配置超时 {settings.AI_TIMEOUT} 秒）'}",
        )
    if isinstance(exc, httpx.PoolTimeout):
        return (
            "Generation API pool timed out after %s seconds (configured timeout=%s seconds)",
            (elapsed_seconds if elapsed_seconds is not None else "unknown", settings.AI_TIMEOUT),
            f"生图接口连接池等待超时{elapsed_fragment or f'（配置超时 {settings.AI_TIMEOUT} 秒）'}",
        )
    if isinstance(exc, httpx.RemoteProtocolError):
        return (
            "Generation API upstream connection closed unexpectedly after %s seconds: %s",
            (elapsed_seconds if elapsed_seconds is not None else "unknown", str(exc)),
            _clip_error_message(f"生图接口连接被上游异常断开{elapsed_fragment}: {exc}"),
        )
    if isinstance(exc, httpx.ConnectError):
        return (
            "Generation API connect error after %s seconds: %s",
            (elapsed_seconds if elapsed_seconds is not None else "unknown", str(exc)),
            _clip_error_message(f"生图接口连接失败{elapsed_fragment}: {exc}"),
        )
    if isinstance(exc, httpx.ReadError):
        return (
            "Generation API read error after %s seconds: %s",
            (elapsed_seconds if elapsed_seconds is not None else "unknown", str(exc)),
            _clip_error_message(f"生图接口响应读取失败{elapsed_fragment}: {exc}"),
        )
    if isinstance(exc, httpx.WriteError):
        return (
            "Generation API write error after %s seconds: %s",
            (elapsed_seconds if elapsed_seconds is not None else "unknown", str(exc)),
            _clip_error_message(f"生图接口请求发送失败{elapsed_fragment}: {exc}"),
        )
    if isinstance(exc, httpx.CloseError):
        return (
            "Generation API connection close error after %s seconds: %s",
            (elapsed_seconds if elapsed_seconds is not None else "unknown", str(exc)),
            _clip_error_message(f"生图接口连接关闭异常{elapsed_fragment}: {exc}"),
        )
    if isinstance(exc, httpx.ProtocolError):
        return (
            "Generation API protocol error after %s seconds: %s",
            (elapsed_seconds if elapsed_seconds is not None else "unknown", str(exc)),
            _clip_error_message(f"生图接口协议异常{elapsed_fragment}: {exc}"),
        )
    if isinstance(exc, httpx.NetworkError):
        return (
            "Generation API network error after %s seconds: %s",
            (elapsed_seconds if elapsed_seconds is not None else "unknown", str(exc)),
            _clip_error_message(f"生图接口网络异常{elapsed_fragment}: {exc}"),
        )
    if isinstance(exc, httpx.TimeoutException):
        if elapsed_seconds is not None:
            return (
                "Generation API request timed out after %s seconds (configured timeout=%s seconds)",
                (elapsed_seconds, settings.AI_TIMEOUT),
                f"生图接口请求超时（实际耗时 {elapsed_seconds} 秒，配置超时 {settings.AI_TIMEOUT} 秒）",
            )
        return (
            "Generation API request timed out after %s seconds (configured timeout=%s seconds)",
            ("unknown", settings.AI_TIMEOUT),
            f"生图接口请求超时（配置超时 {settings.AI_TIMEOUT} 秒）",
        )
    return (
        "Generation API request failed after %s seconds: %s",
        (elapsed_seconds if elapsed_seconds is not None else "unknown", str(exc)),
        _clip_error_message(f"生图接口请求失败{elapsed_fragment}: {exc}"),
    )


def _mark_task_request_started(task: Task) -> bool:
    if task.request_started_at is not None and task.request_finished_at is None:
        return False
    task.request_started_at = now_local()
    task.request_finished_at = None
    return True


def _mark_task_request_finished(task: Task) -> None:
    task.request_finished_at = now_local()


def _mark_image_request_started(image: Image) -> None:
    if image.request_started_at is None or image.request_finished_at is not None:
        image.request_started_at = now_local()
    image.request_finished_at = None


def _mark_image_request_finished(image: Image) -> None:
    if image.request_started_at is not None:
        image.request_finished_at = now_local()


def _mark_task_external_attempt_started(task: Task) -> None:
    attempt_started_at = now_local()
    if task.request_started_at is None or task.request_finished_at is not None:
        task.request_started_at = attempt_started_at
    task.request_finished_at = None
    task.updated_at = attempt_started_at


def _elapsed_ms_since(started_at) -> int | None:
    if started_at is None:
        return None
    return max(int(round((now_local() - started_at).total_seconds() * 1000)), 0)


def _read_file_as_base64(ref_url: str) -> tuple[str, str] | None:
    """Read a local or remote image and return (mime_type, base64_data)."""
    result = load_image_bytes(ref_url)
    if not result:
        return None
    data, mime_type = result
    return mime_type, base64.b64encode(data).decode("utf-8")


def _build_reference_image_payload(image_url: str) -> dict[str, object] | None:
    ref = _read_file_as_base64(image_url)
    if not ref:
        return None
    mime_type, b64_data = ref
    return {
        "inline_part": {"inlineData": {"mimeType": mime_type, "data": b64_data}},
        "base64": b64_data,
        "mime_type": mime_type,
        "data_url": f"data:{mime_type};base64,{b64_data}",
    }


def _resolve_smart_cutout_prompt(prompt: str, reference_count: int) -> str:
    return resolve_smart_cutout_prompt(prompt, reference_count)


def _apply_smart_cutout_rendered_payload(payload: object, cutout_prompt: str) -> object:
    if not isinstance(payload, dict):
        return payload
    next_payload = dict(payload)
    next_payload["prompt"] = cutout_prompt
    if isinstance(next_payload.get("size"), str) and not next_payload["size"].strip():
        next_payload.pop("size", None)
    return next_payload


def _build_inline_image_part(image_url: str) -> dict | None:
    reference_payload = _build_reference_image_payload(image_url)
    if not reference_payload:
        return None
    inline_part = reference_payload.get("inline_part")
    return inline_part if isinstance(inline_part, dict) else None


def _append_inline_image(parts: list[dict], image_url: str) -> bool:
    inline_part = _build_inline_image_part(image_url)
    if not inline_part:
        return False
    parts.append(inline_part)
    return True


def _split_field_path(field_path: str) -> list[str]:
    normalized = re.sub(r"\[(\d+)\]", r".\1", (field_path or "").strip()).strip(".")
    return [segment for segment in normalized.split(".") if segment]


def _read_value_by_path(payload: object, field_path: str) -> tuple[object | None, object | None]:
    current = payload
    parent: object | None = None
    for segment in _split_field_path(field_path):
        parent = current
        if isinstance(current, dict):
            if segment not in current:
                return None, parent
            current = current[segment]
            continue
        if isinstance(current, list):
            if not segment.isdigit():
                return None, parent
            index = int(segment)
            if index < 0 or index >= len(current):
                return None, parent
            current = current[index]
            continue
        return None, parent
    return current, parent


def _normalize_provider_status(value: object) -> str:
    return str(value or "").strip()


def _build_async_request_context(provider_task_id: str, request_url: str) -> str:
    normalized_task_id = str(provider_task_id or "").strip() or "-"
    normalized_request_url = str(request_url or "").strip() or "-"
    return f"第三方taskId={normalized_task_id}，轮询地址={normalized_request_url}"


def _get_async_provider_started_at(task: Task):
    return (
        task.provider_started_at
        or task.request_started_at
        or task.enqueued_at
        or task.created_at
        or task.updated_at
    )


def _is_async_provider_poll_timed_out(task: Task, poll_timeout_seconds: int, *, now_value=None) -> bool:
    started_at = _get_async_provider_started_at(task)
    if started_at is None:
        return False
    current_time = now_value or now_local()
    return started_at <= current_time - timedelta(seconds=max(int(poll_timeout_seconds or 0), 1))


def _mark_async_provider_poll_timeout(
    db,
    task: Task,
    *,
    poll_timeout_seconds: int,
    provider_task_id: str,
    request_url: str,
    response_preview: str = "",
    poll_count: int | None = None,
) -> ApiCallResult:
    request_context = _build_async_request_context(provider_task_id, request_url)
    task.provider_error_message = _clip_error_message(
        f"异步生图轮询超时（超过 {poll_timeout_seconds} 秒，{request_context}）"
    )
    task.provider_status = "timeout"
    task.provider_response_preview = _clip_response_preview(response_preview) if response_preview else task.provider_response_preview
    task.last_polled_at = now_local()
    if poll_count is not None:
        task.poll_count = poll_count
    task.next_poll_at = None
    db.commit()
    return ApiCallResult(
        result=None,
        error_message=task.provider_error_message,
        http_status_code=None,
        attempts=[_build_async_terminal_attempt(db, task, ApiCallResult(
            result=None,
            error_message=task.provider_error_message,
            http_status_code=None,
            attempts=[],
        ))],
    )


def _parse_poll_retry_status(status_value: str) -> int:
    match = re.fullmatch(r"poll_retry_(\d+)", (status_value or "").strip())
    if not match:
        return 0
    return max(int(match.group(1)), 0)


def _defer_async_poll_retry(
    db,
    task: Task,
    *,
    config: ExternalApiConfig,
    error_message: str,
    provider_task_id: str,
    request_url: str,
    response_preview: str = "",
    http_status_code: int | None = None,
) -> ApiCallResult:
    retry_count = _parse_poll_retry_status(task.provider_status) + 1
    request_context = _build_async_request_context(provider_task_id, request_url)
    clipped_error = _clip_error_message(f"{error_message}（{request_context}）")
    task.provider_error_message = clipped_error
    task.provider_response_preview = response_preview or task.provider_response_preview or ""
    task.last_polled_at = now_local()
    task.poll_count = int(task.poll_count or 0) + 1

    if retry_count <= ASYNC_POLL_TRANSIENT_ERROR_RETRY_LIMIT:
        poll_interval_seconds = max(int(config.poll_interval_seconds or 0), 1)
        task.provider_status = f"poll_retry_{retry_count}"
        task.next_poll_at = now_local() + timedelta(seconds=poll_interval_seconds)
        db.commit()
        return ApiCallResult(result=None, error_message="", http_status_code=http_status_code, attempts=[], deferred=True)

    task.provider_status = "poll_failed"
    task.next_poll_at = None
    db.commit()
    return ApiCallResult(result=None, error_message=clipped_error, http_status_code=http_status_code, attempts=[])


def _extract_configured_text_value(payload: dict, field_path: str) -> str:
    if not field_path.strip():
        return ""
    value, _parent = _read_value_by_path(payload, field_path)
    return str(value or "").strip()


def _extract_async_result_data(
    payload: dict,
    *,
    base64_field_path: str,
    url_field_path: str,
) -> tuple[tuple[bytes, str] | None, str, int | None]:
    normalized_base64_field = (base64_field_path or "").strip()
    normalized_url_field = (url_field_path or "").strip()

    if normalized_base64_field:
        result, error_message, result_download_ms = _extract_configured_image_data(payload, normalized_base64_field)
        if result:
            return result, "", result_download_ms
        if error_message and not normalized_url_field:
            return None, error_message, result_download_ms

    if normalized_url_field:
        image_url, _parent = _read_value_by_path(payload, normalized_url_field)
        result, error_message, result_download_ms = _extract_image_from_url_value(image_url)
        if result:
            return result, "", result_download_ms
        if error_message:
            return None, error_message, result_download_ms

    if normalized_base64_field:
        return None, _clip_error_message(f"轮询成功，但未能从 {normalized_base64_field} 或配置的图片 URL 字段中解析结果图"), None
    if normalized_url_field:
        return None, _clip_error_message(f"轮询成功，但未能从 {normalized_url_field} 解析结果图"), None
    return None, "轮询成功，但未配置结果图解析字段", None


def _extract_image_from_url_value(image_url: object) -> tuple[tuple[bytes, str] | None, str, int | None]:
    if not isinstance(image_url, str) or not image_url.strip():
        return None, "", None

    started_perf = time.perf_counter()
    result = load_image_bytes(image_url.strip())
    result_download_ms = _measure_elapsed_ms(started_perf)
    if not result:
        return None, _clip_error_message(f"生图接口返回了结果图地址，但图片下载失败：{image_url}"), result_download_ms
    return result, "", result_download_ms


def _extract_first_inline_image_from_parts(payload: dict) -> tuple[tuple[bytes, str] | None, str]:
    candidates = payload.get("candidates", [])
    if not candidates:
        return None, ""

    for part in candidates[0].get("content", {}).get("parts", []):
        if not isinstance(part, dict):
            continue
        inline = part.get("inlineData")
        if not isinstance(inline, dict):
            continue
        b64_str = inline.get("data")
        if not isinstance(b64_str, str) or not b64_str.strip():
            continue
        mime = str(inline.get("mimeType") or "image/png")
        try:
            img_bytes = base64.b64decode(b64_str)
        except Exception as exc:
            return None, _clip_error_message(f"生图接口返回的 base64 数据解析失败: {exc}")
        logger.info(
            "Generation API success from inlineData parts fallback, mime=%s, image size: %d bytes",
            mime,
            len(img_bytes),
        )
        return (img_bytes, mime), ""
    return None, ""


def _extract_configured_image_url_data(
    payload: dict,
    field_path: str,
    parent: object | None = None,
) -> tuple[tuple[bytes, str] | None, str, int | None]:
    candidate_paths: list[str] = []
    if isinstance(parent, dict):
        candidate_paths.append(f"{field_path.rsplit('.', 1)[0]}.url" if "." in field_path else "url")
    candidate_paths.append("data.0.url")

    seen_paths: set[str] = set()
    last_error_message = ""
    for candidate_path in candidate_paths:
        normalized_path = candidate_path.strip()
        if not normalized_path or normalized_path in seen_paths:
            continue
        seen_paths.add(normalized_path)
        image_url, _ = _read_value_by_path(payload, normalized_path)
        result, error_message, result_download_ms = _extract_image_from_url_value(image_url)
        if result:
            logger.info(
                "Generation API fallback to image url succeeded: configured_field=%s, url_field=%s",
                field_path,
                normalized_path,
            )
            return result, "", result_download_ms
        if error_message:
            logger.warning(
                "Generation API fallback image url download failed: configured_field=%s, url_field=%s, error=%s",
                field_path,
                normalized_path,
                error_message,
            )
            last_error_message = error_message
    return None, last_error_message, None


def _extract_configured_image_data(
    payload: dict,
    field_path: str,
) -> tuple[tuple[bytes, str] | None, str, int | None]:
    image_b64, parent = _read_value_by_path(payload, field_path)
    if not isinstance(image_b64, str) or not image_b64.strip():
        fallback_result, fallback_error, result_download_ms = _extract_configured_image_url_data(payload, field_path, parent)
        if fallback_result:
            return fallback_result, "", result_download_ms
        parts_result, parts_error = _extract_first_inline_image_from_parts(payload)
        if parts_result:
            logger.info(
                "Generation API fallback to first inlineData part succeeded: configured_field=%s",
                field_path,
            )
            return parts_result, "", None
        preview = _clip_response_preview(payload)
        logger.warning(
            "Generation API configured field missing: path=%s, response_preview=%s",
            field_path,
            preview,
        )
        if parts_error:
            return None, parts_error, result_download_ms
        if fallback_error:
            return None, fallback_error, result_download_ms
        return None, _clip_error_message(
            f"生图接口返回内容缺少配置路径 {field_path} 对应的 base64 数据；响应摘要：{preview}"
        ), result_download_ms

    mime = "image/png"
    if isinstance(parent, dict):
        mime = str(parent.get("mimeType") or parent.get("mime_type") or mime)

    try:
        return (base64.b64decode(image_b64), mime), "", None
    except Exception as exc:
        return None, _clip_error_message(f"生图接口返回的 base64 数据解析失败: {exc}"), None


def _extract_legacy_image_data(payload: dict) -> tuple[tuple[bytes, str] | None, str]:
    candidates = payload.get("candidates", [])
    if not candidates:
        logger.warning("Generation API returned no candidates: %s", str(payload)[:300])
        return None, _clip_error_message(
            f"生图接口返回内容缺少 candidates: {str(payload)[:300]}"
        )

    result, error_message = _extract_first_inline_image_from_parts(payload)
    if result:
        return result, ""
    if error_message:
        return None, error_message

    logger.warning("Generation API response has no inlineData in parts")
    return None, "生图接口返回内容缺少图片数据 inlineData"


def _call_generation_api_once(
    db,
    *,
    config: ExternalApiConfig,
    scene_key: str,
    prompt: str,
    aspect_ratio: str,
    image_size: str,
    custom_size: str,
    reference_images: list[str] | None = None,
    mode: str = "generate",
    source_image: str = "",
    mask_image: str = "",
) -> tuple[tuple[bytes, str] | None, str, int | None, int | None, int | None, int | None, str]:
    request_started_perf: float | None = None
    external_http_ms: int | None = None
    try:
        config_name = config.name
        configured_field_path = (config.result_base64_field or "").strip()
        mapped_resolution = resolve_mapped_resolution(db, scene_key, aspect_ratio, image_size)
        cos_config = get_optional_cos_config(db)

        parts: list[dict] = []
        render_variables = {
            **build_secret_variables(db),
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
            "custom_size": custom_size,
            "mapped_resolution": mapped_resolution,
            "resolved_resolution": (custom_size or "").strip() or mapped_resolution,
            "generation_config": {},
            "mode": mode,
            "reference_image_count": 0,
        }
        if mode == "inpaint":
            source_payload = _build_reference_image_payload(source_image)
            if not source_payload:
                logger.warning("Inpaint source image not found: %s", source_image)
                return None, "图编辑原图不存在或无法读取", None, None, None, None, ""
            source_inline_part = source_payload.get("inline_part")
            if not isinstance(source_inline_part, dict):
                logger.warning("Inpaint source image payload malformed: %s", source_image)
                return None, "图编辑原图格式无效", None, None, None, None, ""
            parts.append(source_inline_part)
            render_variables["source_image"] = source_inline_part
            render_variables["source_image_url"] = serialize_asset_urls(source_image, cos_config=cos_config)["image_url"]
            render_variables["source_image_base64"] = source_payload["base64"]
            render_variables["source_image_mime_type"] = source_payload["mime_type"]
            render_variables["source_image_data_url"] = source_payload["data_url"]

            mask_payload = _build_reference_image_payload(mask_image)
            if not mask_payload:
                logger.warning("Inpaint mask image not found: %s", mask_image)
                return None, "图编辑蒙版不存在或无法读取", None, None, None, None, ""
            mask_inline_part = mask_payload.get("inline_part")
            if not isinstance(mask_inline_part, dict):
                logger.warning("Inpaint mask image payload malformed: %s", mask_image)
                return None, "图编辑蒙版格式无效", None, None, None, None, ""
            parts.append(mask_inline_part)
            render_variables["mask_image"] = mask_inline_part
            render_variables["mask_image_base64"] = mask_payload["base64"]
            render_variables["mask_image_mime_type"] = mask_payload["mime_type"]
            render_variables["mask_image_data_url"] = mask_payload["data_url"]
            parts.append({
                "text": (
                    "请基于第1张原图进行局部重绘，第2张图是蒙版：白色区域需要重绘，"
                    "黑色区域必须保持原样。严格保留未遮罩区域的主体、构图、光影与细节。"
                    f"重绘要求：{prompt}"
                )
            })
        else:
            reference_count = 0
            for index, ref_url in enumerate(reference_images or [], start=1):
                reference_payload = _build_reference_image_payload(ref_url)
                if not reference_payload:
                    logger.warning("Reference image not found or unreadable: index=%d, url=%s", index, ref_url)
                    continue
                inline_part = reference_payload["inline_part"]
                if not isinstance(inline_part, dict):
                    logger.warning("Reference image payload malformed: index=%d, url=%s", index, ref_url)
                    continue
                parts.append(inline_part)
                reference_count += 1
                render_variables[f"reference_image_{index}"] = inline_part
                render_variables[f"reference_image_{index}_url"] = serialize_asset_urls(ref_url, cos_config=cos_config)["image_url"]
                render_variables[f"reference_image_{index}_base64"] = reference_payload["base64"]
                render_variables[f"reference_image_{index}_mime_type"] = reference_payload["mime_type"]
                render_variables[f"reference_image_{index}_data_url"] = reference_payload["data_url"]
            render_variables["reference_image_count"] = reference_count
            if mode == "smart_cutout":
                cutout_prompt = _resolve_smart_cutout_prompt(prompt, reference_count)
                render_variables["prompt"] = cutout_prompt
                parts.append({"text": cutout_prompt})
            else:
                parts.append({"text": prompt})

        generation_config = {"responseModalities": ["IMAGE"]}
        if mode != "inpaint":
            generation_config["imageConfig"] = {
                "aspectRatio": aspect_ratio,
            }
            if image_size:
                generation_config["imageConfig"]["imageSize"] = image_size

        render_variables["contents_parts"] = parts
        render_variables["generation_config"] = generation_config
        rendered = render_config(config, render_variables)
        if mode == "smart_cutout":
            rendered.payload = _apply_smart_cutout_rendered_payload(
                rendered.payload,
                str(render_variables.get("prompt") or _resolve_smart_cutout_prompt(prompt, int(render_variables.get("reference_image_count") or 0))),
            )
        request_kwargs = build_external_request_kwargs(rendered)
        # End the read transaction before the slow HTTP call without detaching
        # task/image ORM objects that the caller still needs to update.
        db.commit()

        auth_value = rendered.headers.get("Authorization", "")
        logger.info(
            "Calling generation API: config=%s, mode=%s, prompt=%s, ratio=%s, size=%s, custom_size=%s, ref_count=%d, auth_prefix=%s, request_mode=%s",
            config_name,
            mode,
            prompt[:60],
            aspect_ratio,
            image_size,
            custom_size,
            len(reference_images or []),
            (auth_value[:8] + "...") if auth_value else "none",
            "multipart" if should_use_multipart_request(rendered) else "json",
        )

        request_started_perf = time.perf_counter()
        with httpx.Client(timeout=settings.AI_TIMEOUT, trust_env=False) as client:
            http_started_perf = time.perf_counter()
            resp = client.post(rendered.request_url, **request_kwargs)
            external_http_ms = _measure_elapsed_ms(http_started_perf)

            if resp.status_code != 200:
                logger.error("Generation API HTTP %s: %s", resp.status_code, resp.text[:500])
                return (
                    None,
                    _clip_error_message(f"生图接口返回 HTTP {resp.status_code}: {resp.text[:500] or '(空响应)'}"),
                    resp.status_code,
                    _measure_elapsed_ms(request_started_perf),
                    external_http_ms,
                    None,
                    _build_attempt_response_preview(resp.text),
                )

            try:
                data = resp.json()
            except Exception as exc:
                return (
                    None,
                    _clip_error_message(f"生图接口响应不是合法 JSON: {exc}"),
                    None,
                    _measure_elapsed_ms(request_started_perf),
                    external_http_ms,
                    None,
                    _build_attempt_response_preview(resp.text),
                )
            response_preview = _build_attempt_response_preview(data)

        if configured_field_path:
            result, error_message, result_download_ms = _extract_configured_image_data(data, configured_field_path)
            if result:
                img_bytes, mime = result
                logger.info(
                    "Generation API success, configured field=%s, mime=%s, image size: %d bytes",
                    configured_field_path, mime, len(img_bytes),
                )
                return result, "", None, _measure_elapsed_ms(request_started_perf), external_http_ms, result_download_ms, response_preview
            logger.warning("Generation API configured field extraction failed: %s", error_message)
            return None, error_message, None, _measure_elapsed_ms(request_started_perf), external_http_ms, result_download_ms, response_preview

        result, error_message = _extract_legacy_image_data(data)
        return result, error_message, None, _measure_elapsed_ms(request_started_perf), external_http_ms, None, response_preview
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        logger.error("Generation API config error: %s", detail)
        return None, _clip_error_message(detail), None, _measure_elapsed_ms(request_started_perf), external_http_ms, None, ""
    except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError) as exc:
        external_http_ms = external_http_ms or _measure_elapsed_ms(request_started_perf)
        log_message, log_args, user_message = _classify_generation_request_exception(
            exc,
            started_perf=request_started_perf,
        )
        logger.error(log_message, *log_args)
        return None, user_message, None, _measure_elapsed_ms(request_started_perf), external_http_ms, None, ""
    except Exception as exc:
        logger.error("Generation API error: %s", exc, exc_info=True)
        return None, _clip_error_message(f"生图接口调用异常: {exc}"), None, _measure_elapsed_ms(request_started_perf), external_http_ms, None, ""


def _submit_async_generation_api_once(
    db,
    *,
    config: ExternalApiConfig,
    scene_key: str,
    prompt: str,
    aspect_ratio: str,
    image_size: str,
    custom_size: str,
    reference_images: list[str] | None = None,
    mode: str = "generate",
    source_image: str = "",
    mask_image: str = "",
) -> AsyncSubmitResult:
    request_started_perf: float | None = None
    external_http_ms: int | None = None
    try:
        mapped_resolution = resolve_mapped_resolution(db, scene_key, aspect_ratio, image_size)
        cos_config = get_optional_cos_config(db)

        parts: list[dict] = []
        render_variables = {
            **build_secret_variables(db),
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
            "custom_size": custom_size,
            "mapped_resolution": mapped_resolution,
            "resolved_resolution": (custom_size or "").strip() or mapped_resolution,
            "generation_config": {},
            "mode": mode,
            "reference_image_count": 0,
        }
        if mode == "inpaint":
            source_payload = _build_reference_image_payload(source_image)
            if not source_payload:
                return AsyncSubmitResult(None, "", "图编辑原图不存在或无法读取", None, None, "")
            source_inline_part = source_payload.get("inline_part")
            if not isinstance(source_inline_part, dict):
                return AsyncSubmitResult(None, "", "图编辑原图格式无效", None, None, "")
            parts.append(source_inline_part)
            render_variables["source_image"] = source_inline_part
            render_variables["source_image_url"] = serialize_asset_urls(source_image, cos_config=cos_config)["image_url"]
            render_variables["source_image_base64"] = source_payload["base64"]
            render_variables["source_image_mime_type"] = source_payload["mime_type"]
            render_variables["source_image_data_url"] = source_payload["data_url"]

            mask_payload = _build_reference_image_payload(mask_image)
            if not mask_payload:
                return AsyncSubmitResult(None, "", "图编辑蒙版不存在或无法读取", None, None, "")
            mask_inline_part = mask_payload.get("inline_part")
            if not isinstance(mask_inline_part, dict):
                return AsyncSubmitResult(None, "", "图编辑蒙版格式无效", None, None, "")
            parts.append(mask_inline_part)
            render_variables["mask_image"] = mask_inline_part
            render_variables["mask_image_base64"] = mask_payload["base64"]
            render_variables["mask_image_mime_type"] = mask_payload["mime_type"]
            render_variables["mask_image_data_url"] = mask_payload["data_url"]
            parts.append({
                "text": (
                    "请基于第1张原图进行局部重绘，第2张图是蒙版：白色区域需要重绘，"
                    "黑色区域必须保持原样。严格保留未遮罩区域的主体、构图、光影与细节。"
                    f"重绘要求：{prompt}"
                )
            })
        else:
            reference_count = 0
            for index, ref_url in enumerate(reference_images or [], start=1):
                reference_payload = _build_reference_image_payload(ref_url)
                if not reference_payload:
                    continue
                inline_part = reference_payload["inline_part"]
                if not isinstance(inline_part, dict):
                    continue
                parts.append(inline_part)
                reference_count += 1
                render_variables[f"reference_image_{index}"] = inline_part
                render_variables[f"reference_image_{index}_url"] = serialize_asset_urls(ref_url, cos_config=cos_config)["image_url"]
                render_variables[f"reference_image_{index}_base64"] = reference_payload["base64"]
                render_variables[f"reference_image_{index}_mime_type"] = reference_payload["mime_type"]
                render_variables[f"reference_image_{index}_data_url"] = reference_payload["data_url"]
            render_variables["reference_image_count"] = reference_count
            if mode == "smart_cutout":
                cutout_prompt = _resolve_smart_cutout_prompt(prompt, reference_count)
                render_variables["prompt"] = cutout_prompt
                parts.append({"text": cutout_prompt})
            else:
                parts.append({"text": prompt})

        generation_config = {"responseModalities": ["IMAGE"]}
        if mode != "inpaint":
            generation_config["imageConfig"] = {"aspectRatio": aspect_ratio}
            if image_size:
                generation_config["imageConfig"]["imageSize"] = image_size

        render_variables["contents_parts"] = parts
        render_variables["generation_config"] = generation_config
        rendered = render_config(config, render_variables)
        if mode == "smart_cutout":
            rendered.payload = _apply_smart_cutout_rendered_payload(
                rendered.payload,
                str(render_variables.get("prompt") or _resolve_smart_cutout_prompt(prompt, int(render_variables.get("reference_image_count") or 0))),
            )
        request_kwargs = build_external_request_kwargs(rendered)
        db.commit()

        request_started_perf = time.perf_counter()
        with httpx.Client(timeout=settings.AI_TIMEOUT, trust_env=False) as client:
            http_started_perf = time.perf_counter()
            resp = client.post(rendered.request_url, **request_kwargs)
            external_http_ms = _measure_elapsed_ms(http_started_perf)
        preview = (resp.text or "")[:MAX_RESPONSE_PREVIEW_LENGTH]
        success_statuses = parse_http_statuses_json(config.submit_success_statuses_json) or [200, 201, 202]
        if resp.status_code not in success_statuses:
            return AsyncSubmitResult(
                None,
                "",
                _clip_error_message(f"异步生图提交返回 HTTP {resp.status_code}: {preview or '(空响应)'}"),
                resp.status_code,
                _measure_elapsed_ms(request_started_perf),
                preview,
                external_http_ms,
            )
        try:
            payload = resp.json()
        except Exception as exc:
            return AsyncSubmitResult(
                None,
                "",
                _clip_error_message(f"异步生图提交成功，但响应不是合法 JSON: {exc}"),
                resp.status_code,
                _measure_elapsed_ms(request_started_perf),
                preview,
                external_http_ms,
            )
        task_id_value, _parent = _read_value_by_path(payload, config.task_id_field or "")
        provider_task_id = str(task_id_value or "").strip()
        if not provider_task_id:
            return AsyncSubmitResult(
                None,
                "",
                _clip_error_message(f"异步生图提交成功，但未从 {config.task_id_field or '(未配置)'} 解析到 taskId；响应摘要：{_clip_response_preview(payload)}"),
                resp.status_code,
                _measure_elapsed_ms(request_started_perf),
                _clip_response_preview(payload),
                external_http_ms,
            )
        provider_status_value = ""
        if (config.result_status_field or "").strip():
            raw_status, _parent = _read_value_by_path(payload, config.result_status_field)
            provider_status_value = _normalize_provider_status(raw_status)
        return AsyncSubmitResult(
            provider_task_id,
            provider_status_value or "submitted",
            "",
            resp.status_code,
            _measure_elapsed_ms(request_started_perf),
            _clip_response_preview(payload),
            external_http_ms,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return AsyncSubmitResult(None, "", _clip_error_message(detail), None, _measure_elapsed_ms(request_started_perf), "", external_http_ms)
    except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError) as exc:
        external_http_ms = external_http_ms or _measure_elapsed_ms(request_started_perf)
        log_message, log_args, user_message = _classify_generation_request_exception(
            exc,
            started_perf=request_started_perf,
        )
        logger.error(log_message, *log_args)
        return AsyncSubmitResult(None, "", user_message, None, _measure_elapsed_ms(request_started_perf), "", external_http_ms)
    except Exception as exc:
        logger.error("Async generation submit error: %s", exc, exc_info=True)
        return AsyncSubmitResult(None, "", _clip_error_message(f"异步生图提交异常: {exc}"), None, _measure_elapsed_ms(request_started_perf), "", external_http_ms)


def _poll_async_generation_once(
    db,
    task: Task,
    *,
    config: ExternalApiConfig,
) -> ApiCallResult:
    provider_task_id = (task.provider_task_id or "").strip()
    if not provider_task_id:
        return ApiCallResult(
            result=None,
            error_message="缺少第三方任务 ID，无法轮询结果",
            http_status_code=None,
            attempts=[],
        )

    poll_interval_seconds = max(int(config.poll_interval_seconds or 0), 1)
    poll_timeout_seconds = max(int(config.poll_timeout_seconds or 0), 1)
    success_values = {item.strip().lower() for item in parse_string_list_json(config.result_success_values_json) if item.strip()}
    failed_values = {item.strip().lower() for item in parse_string_list_json(config.result_failed_values_json) if item.strip()}
    if not success_values:
        success_values = {"success", "succeeded", "completed"}
    if not failed_values:
        failed_values = {"failed", "error", "cancelled"}

    current_poll_count = int(task.poll_count or 0)

    mapped_resolution = resolve_mapped_resolution(
        db,
        _resolve_task_mode_and_scene_key(task)[1],
        task.size or "",
        task.resolution or "",
    )
    poll_variables = {
        **build_secret_variables(db),
        "provider_task_id": provider_task_id,
        "task_id": provider_task_id,
        "prompt": task.prompt or "",
        "mode": task.mode or "generate",
        "aspect_ratio": task.size or "",
        "image_size": task.resolution or "",
        "custom_size": task.custom_size or "",
        "mapped_resolution": mapped_resolution,
        "resolved_resolution": (task.custom_size or "").strip() or mapped_resolution,
    }
    rendered = render_poll_config(config, poll_variables)
    request_kwargs = build_external_poll_request_kwargs(rendered)
    request_started_perf = time.perf_counter()
    external_http_ms: int | None = None
    try:
        with httpx.Client(timeout=settings.AI_TIMEOUT, trust_env=False) as client:
            http_started_perf = time.perf_counter()
            response = client.request(rendered.method, rendered.request_url, **request_kwargs)
            external_http_ms = _measure_elapsed_ms(http_started_perf)
        preview = (response.text or "")[:MAX_RESPONSE_PREVIEW_LENGTH]
        if response.status_code < 200 or response.status_code >= 300:
            if _is_async_provider_poll_timed_out(task, poll_timeout_seconds):
                return _mark_async_provider_poll_timeout(
                    db,
                    task,
                    poll_timeout_seconds=poll_timeout_seconds,
                    provider_task_id=provider_task_id,
                    request_url=rendered.request_url,
                    response_preview=preview,
                    poll_count=current_poll_count + 1,
                )
            return _defer_async_poll_retry(
                db,
                task,
                config=config,
                error_message=f"异步生图轮询返回 HTTP {response.status_code}: {preview or '(空响应)'}",
                provider_task_id=provider_task_id,
                request_url=rendered.request_url,
                response_preview=preview,
                http_status_code=response.status_code,
            )

        try:
            payload = response.json()
        except Exception as exc:
            if _is_async_provider_poll_timed_out(task, poll_timeout_seconds):
                return _mark_async_provider_poll_timeout(
                    db,
                    task,
                    poll_timeout_seconds=poll_timeout_seconds,
                    provider_task_id=provider_task_id,
                    request_url=rendered.request_url,
                    response_preview=preview,
                    poll_count=current_poll_count + 1,
                )
            return _defer_async_poll_retry(
                db,
                task,
                config=config,
                error_message=f"异步生图轮询响应不是合法 JSON: {exc}",
                provider_task_id=provider_task_id,
                request_url=rendered.request_url,
                response_preview=preview,
                http_status_code=response.status_code,
            )

        provider_status = _extract_configured_text_value(payload, config.result_status_field) or task.provider_status or "processing"
        response_preview = _clip_response_preview(payload)
        attempt_response_preview = _build_attempt_response_preview(payload)
        next_poll_count = current_poll_count + 1
        normalized_status = provider_status.strip().lower()

        if normalized_status in success_values:
            result, error_message, result_download_ms = _extract_async_result_data(
                payload,
                base64_field_path=config.poll_result_base64_field or "",
                url_field_path=config.poll_result_url_field or "",
            )
            task.next_poll_at = None
            task.provider_status = provider_status
            task.provider_response_preview = response_preview
            task.last_polled_at = now_local()
            task.poll_count = next_poll_count
            attempt_record = ApiAttemptRecord(
                api_config_id=config.id,
                api_config_name=config.name or "",
                attempt_index=1,
                is_fallback=_is_fallback_poll_config(db, task, config),
                status="success" if result else "failed",
                http_status=response.status_code,
                error_message="" if result else _clip_error_message(error_message),
                duration_ms=_elapsed_ms_since(_get_async_provider_started_at(task)),
                external_http_ms=None,
                result_download_ms=result_download_ms,
                response_preview=attempt_response_preview,
            )
            if result:
                task.provider_error_message = ""
                db.commit()
                return ApiCallResult(
                    result=result,
                    error_message="",
                    http_status_code=None,
                    attempts=[attempt_record],
                    result_download_ms=result_download_ms,
                )
            request_context = _build_async_request_context(provider_task_id, rendered.request_url)
            task.provider_error_message = _clip_error_message(
                f"{error_message or '异步生图已完成，但结果图解析失败'}（{request_context}）"
            )
            db.commit()
            attempt_record.error_message = task.provider_error_message
            return ApiCallResult(result=None, error_message=task.provider_error_message, http_status_code=None, attempts=[attempt_record])

        if normalized_status in failed_values:
            request_context = _build_async_request_context(provider_task_id, rendered.request_url)
            provider_error = _extract_configured_text_value(payload, config.result_error_field) or _clip_error_message(
                f"异步生图任务失败，状态为 {provider_status or 'failed'}（{request_context}）"
            )
            if request_context not in provider_error:
                provider_error = _clip_error_message(f"{provider_error}（{request_context}）")
            task.provider_status = provider_status
            task.provider_response_preview = response_preview
            task.last_polled_at = now_local()
            task.poll_count = next_poll_count
            task.provider_error_message = provider_error
            task.next_poll_at = None
            db.commit()
            return ApiCallResult(
                result=None,
                error_message=provider_error,
                http_status_code=response.status_code,
                attempts=[ApiAttemptRecord(
                    api_config_id=config.id,
                    api_config_name=config.name or "",
                    attempt_index=1,
                    is_fallback=_is_fallback_poll_config(db, task, config),
                    status="failed",
                    http_status=response.status_code,
                    error_message=provider_error,
                    duration_ms=_elapsed_ms_since(_get_async_provider_started_at(task)),
                    response_preview=attempt_response_preview,
                )],
            )

        if _is_async_provider_poll_timed_out(task, poll_timeout_seconds):
            return _mark_async_provider_poll_timeout(
                db,
                task,
                poll_timeout_seconds=poll_timeout_seconds,
                provider_task_id=provider_task_id,
                request_url=rendered.request_url,
                response_preview=response_preview,
                poll_count=next_poll_count,
            )

        task.provider_status = provider_status
        task.provider_response_preview = response_preview
        task.provider_error_message = ""
        task.last_polled_at = now_local()
        task.poll_count = next_poll_count
        task.next_poll_at = now_local() + timedelta(seconds=poll_interval_seconds)
        db.commit()
        return ApiCallResult(result=None, error_message="", http_status_code=None, attempts=[], deferred=True)
    except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError) as exc:
        log_message, log_args, user_message = _classify_generation_request_exception(
            exc,
            started_perf=request_started_perf,
        )
        logger.error(log_message, *log_args)
        if _is_async_provider_poll_timed_out(task, poll_timeout_seconds):
            return _mark_async_provider_poll_timeout(
                db,
                task,
                poll_timeout_seconds=poll_timeout_seconds,
                provider_task_id=provider_task_id,
                request_url=rendered.request_url,
                poll_count=current_poll_count + 1,
            )
        return _defer_async_poll_retry(
            db,
            task,
            config=config,
            error_message=user_message,
            provider_task_id=provider_task_id,
            request_url=rendered.request_url,
        )
    except Exception as exc:
        logger.exception("Async generation poll error: task_id=%s", task.id)
        request_context = _build_async_request_context(provider_task_id, rendered.request_url)
        error_message = _clip_error_message(f"异步生图轮询异常（{request_context}）: {exc}")
        task.provider_error_message = error_message
        task.provider_status = task.provider_status or "poll_failed"
        task.last_polled_at = now_local()
        task.poll_count = current_poll_count + 1
        task.next_poll_at = None
        db.commit()
        return ApiCallResult(
            result=None,
            error_message=error_message,
            http_status_code=None,
            attempts=[_build_async_terminal_attempt(db, task, ApiCallResult(
                result=None,
                error_message=error_message,
                http_status_code=None,
                attempts=[],
            ))],
        )


def _execute_task_generation(db, task: Task) -> tuple[ApiCallResult, list[ApiAttemptRecord]]:
    ref_urls = _parse_reference_images(task)
    task_mode, scene_key = _resolve_task_mode_and_scene_key(task)
    primary_config, backup_config = resolve_scene_generation_configs(db, scene_key)
    existing_provider_task_id = (task.provider_task_id or "").strip()
    attempts: list[ApiAttemptRecord] = []

    if existing_provider_task_id:
        if not task.provider_api_config_id:
            return ApiCallResult(
                result=None,
                error_message="当前任务已保存第三方 taskId，但缺少对应接口配置",
                http_status_code=None,
                attempts=[],
            ), attempts
        configured = (
            db.query(ExternalApiConfig)
            .filter(
                ExternalApiConfig.id == task.provider_api_config_id,
                ExternalApiConfig.status == "enabled",
            )
            .first()
        )
        call_mode = (configured.call_mode or "sync").strip().lower() if configured else "sync"
        if configured and call_mode == "async":
            return _poll_async_generation_once(db, task, config=configured), attempts
        return ApiCallResult(
            result=None,
            error_message="当前任务已保存第三方 taskId，但对应接口未启用异步轮询",
            http_status_code=None,
            attempts=[],
        ), attempts

    # 主/备各自按 call_mode 处理：支持主同步失败后切备用异步并轮询取结果
    configs_to_try: list[tuple[ExternalApiConfig, bool]] = [(primary_config, False)]
    if backup_config is not None:
        configs_to_try.append((backup_config, True))
    return _submit_generation_with_configs(
        db,
        task=task,
        scene_key=scene_key,
        task_mode=task_mode,
        ref_urls=ref_urls,
        configs_to_try=configs_to_try,
    )


MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _save_image_bytes(db, image_bytes: bytes, mime: str = "image/png") -> str:
    ext = MIME_TO_EXT.get(mime, "png")
    key = build_object_key("generated", f"generated.{ext}", mime)
    return upload_bytes_to_cos(
        db,
        data=image_bytes,
        key=key,
        content_type=mime,
        cache_control=settings.GENERATED_IMAGE_CACHE_CONTROL,
    )


def _cleanup_expired_previews() -> None:
    ttl_seconds = max(int(settings.GENERATED_PREVIEW_TTL_SECONDS or 0), 0)
    if ttl_seconds <= 0:
        return

    preview_dir = Path(settings.UPLOAD_DIR) / "generated_preview"
    if not preview_dir.exists():
        return

    expire_before = max(int(time.time()) - ttl_seconds, 0)
    for file_path in preview_dir.iterdir():
        try:
            if not file_path.is_file():
                continue
            if int(file_path.stat().st_mtime) < expire_before:
                file_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Failed to cleanup preview file: %s", file_path)


def _save_preview_image(image_bytes: bytes, mime: str = "image/png") -> str:
    ext = MIME_TO_EXT.get(mime, "png")
    preview_dir = Path(settings.UPLOAD_DIR) / "generated_preview"
    preview_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_expired_previews()
    file_name = f"{uuid.uuid4().hex}.{ext}"
    file_path = preview_dir / file_name
    file_path.write_bytes(image_bytes)
    return f"/uploads/generated_preview/{file_name}"


def _remove_local_preview(preview_url: str) -> None:
    relative = (preview_url or "").strip().lstrip("/")
    if not relative.startswith("uploads/"):
        return
    file_path = Path(settings.UPLOAD_DIR) / relative[len("uploads/"):]
    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Failed to remove local preview file: %s", file_path)


def _derive_image_format(mime: str) -> str:
    if not mime:
        return ""
    return mime.split("/")[-1].upper()


def _mark_image_storage_fallback(image: Image, error_message: str = "") -> None:
    """
    Preserve the locally saved preview when remote storage upload fails.

    The preview file contains the full generated bytes, so we can safely expose
    it as the downloadable image_url fallback instead of discarding the result.
    """
    fallback_url = image.preview_url or ""
    image.image_url = fallback_url
    image.status = "success" if fallback_url else "failed"
    if not fallback_url:
        image.image_format = ""
        image.image_size_bytes = 0
        image.error_message = _clip_error_message(error_message or "图片已生成，但保存结果失败")


def _mark_generation_failure(image: Image, error_message: str) -> None:
    image.preview_url = ""
    image.image_url = ""
    image.image_format = ""
    image.image_size_bytes = 0
    image.status = "failed"
    image.error_message = _to_user_facing_generation_error(error_message, fallback="生图失败")
    _mark_image_request_finished(image)


def _set_last_attempt_cos_upload_ms(attempts: list[ApiAttemptRecord], cos_upload_ms: int | None) -> None:
    if cos_upload_ms is None:
        return
    for attempt in reversed(attempts):
        if attempt.status == "success":
            attempt.cos_upload_ms = cos_upload_ms
            return


def _is_fallback_poll_config(db, task: Task, config: ExternalApiConfig | None) -> bool:
    if not config:
        return False
    existing = (
        db.query(TaskApiAttempt)
        .filter(
            TaskApiAttempt.task_id == task.id,
            TaskApiAttempt.api_config_id == config.id,
        )
        .order_by(TaskApiAttempt.attempt_index.desc(), TaskApiAttempt.id.desc())
        .first()
    )
    if existing is not None:
        return bool(existing.is_fallback)
    _task_mode, scene_key = _resolve_task_mode_and_scene_key(task)
    _primary_config, backup_config = resolve_scene_generation_configs(db, scene_key)
    return bool(backup_config and backup_config.id == config.id)


def _find_mergeable_async_attempt(
    db,
    *,
    image: Image,
    attempt: ApiAttemptRecord,
) -> TaskApiAttempt | None:
    query = (
        db.query(TaskApiAttempt)
        .filter(
            TaskApiAttempt.image_id == image.id,
            TaskApiAttempt.is_fallback.is_(bool(attempt.is_fallback)),
        )
    )
    if attempt.api_config_id:
        query = query.filter(TaskApiAttempt.api_config_id == attempt.api_config_id)
    elif attempt.api_config_name:
        query = query.filter(TaskApiAttempt.api_config_name == attempt.api_config_name)
    return query.order_by(TaskApiAttempt.attempt_index.desc(), TaskApiAttempt.id.desc()).first()


def _merge_async_poll_into_attempt(existing: TaskApiAttempt, attempt: ApiAttemptRecord) -> None:
    existing.status = attempt.status or existing.status or "failed"
    if attempt.http_status is not None:
        existing.http_status = attempt.http_status
    existing.error_message = _clip_error_message(attempt.error_message)
    if attempt.duration_ms is not None:
        existing.duration_ms = attempt.duration_ms
    if attempt.result_download_ms is not None:
        existing.result_download_ms = attempt.result_download_ms
    if attempt.cos_upload_ms is not None:
        existing.cos_upload_ms = attempt.cos_upload_ms
    if attempt.response_preview:
        existing.response_preview = attempt.response_preview


def _build_async_terminal_attempt(db, task: Task, call_result: ApiCallResult) -> ApiAttemptRecord:
    config = _resolve_async_poll_config(db, task)
    return ApiAttemptRecord(
        api_config_id=task.provider_api_config_id or (config.id if config else None),
        api_config_name=(config.name if config else "") or "",
        attempt_index=1,
        is_fallback=_is_fallback_poll_config(db, task, config),
        status="failed",
        http_status=call_result.http_status_code,
        error_message=_clip_error_message(call_result.error_message),
        duration_ms=_elapsed_ms_since(_get_async_provider_started_at(task)),
        response_preview=task.provider_response_preview or "",
    )


def _record_api_attempts(
    db,
    *,
    task: Task,
    image: Image,
    image_index: int,
    attempts: list[ApiAttemptRecord],
    merge_existing: bool = False,
) -> None:
    if not attempts:
        return
    for attempt in attempts:
        existing = _find_mergeable_async_attempt(db, image=image, attempt=attempt) if merge_existing else None
        if existing is not None:
            _merge_async_poll_into_attempt(existing, attempt)
            continue
        db.add(TaskApiAttempt(
            task_id=task.id,
            image_id=image.id,
            image_index=image_index,
            api_config_id=attempt.api_config_id,
            api_config_name=attempt.api_config_name or "",
            attempt_index=attempt.attempt_index,
            is_fallback=bool(attempt.is_fallback),
            status=attempt.status or "failed",
            http_status=attempt.http_status,
            error_message=_clip_error_message(attempt.error_message),
            duration_ms=attempt.duration_ms,
            external_http_ms=attempt.external_http_ms,
            result_download_ms=attempt.result_download_ms,
            cos_upload_ms=attempt.cos_upload_ms,
            response_preview=attempt.response_preview or "",
        ))
    if any(attempt.is_fallback for attempt in attempts):
        task.used_fallback_api = True


def _record_api_attempts_safely(
    db,
    *,
    task: Task,
    image: Image,
    image_index: int,
    attempts: list[ApiAttemptRecord],
    merge_existing: bool = False,
) -> None:
    try:
        _record_api_attempts(
            db,
            task=task,
            image=image,
            image_index=image_index,
            attempts=attempts,
            merge_existing=merge_existing,
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to record task API attempts; generation result is preserved: task_id=%s image_id=%s",
            task.id,
            image.id,
        )


def _resolve_task_mode_and_scene_key(task: Task) -> tuple[str, str]:
    task_mode = (task.mode or "generate").lower()
    if task_mode == "inpaint":
        return task_mode, SCENE_INPAINT
    if task_mode == "smart_cutout":
        return task_mode, SCENE_SMART_CUTOUT
    return task_mode, (task.model or "")


def _submit_generation_with_configs(
    db,
    *,
    task: Task,
    scene_key: str,
    task_mode: str,
    ref_urls: list[str],
    configs_to_try: list[tuple[ExternalApiConfig, bool]],
) -> tuple[ApiCallResult, list[ApiAttemptRecord]]:
    attempts: list[ApiAttemptRecord] = []
    last_error_message = "生图失败"
    last_http_status: int | None = None
    selected_config: ExternalApiConfig | None = None

    for attempt_index, (config, is_fallback) in enumerate(configs_to_try, start=1):
        current_call_mode = (config.call_mode or "sync").strip().lower() or "sync"
        has_more_configs = attempt_index < len(configs_to_try)
        _mark_task_external_attempt_started(task)
        db.commit()
        if current_call_mode != "async":
            result, error_message, http_status_code, duration_ms, external_http_ms, result_download_ms, response_preview = _call_generation_api_once(
                db,
                config=config,
                scene_key=scene_key,
                prompt=task.prompt,
                aspect_ratio=task.size,
                image_size=task.resolution,
                custom_size=task.custom_size or "",
                reference_images=ref_urls,
                mode=task_mode,
                source_image=task.source_image or "",
                mask_image=task.mask_image or "",
            )
            attempts.append(ApiAttemptRecord(
                api_config_id=config.id,
                api_config_name=config.name or "",
                attempt_index=attempt_index,
                is_fallback=is_fallback,
                status="success" if result else "failed",
                http_status=http_status_code,
                error_message="" if result else _clip_error_message(error_message),
                duration_ms=duration_ms,
                external_http_ms=external_http_ms,
                result_download_ms=result_download_ms,
                response_preview=response_preview,
            ))
            if result:
                return ApiCallResult(
                    result=result,
                    error_message="",
                    http_status_code=None,
                    attempts=attempts,
                ), attempts

            last_error_message = _clip_error_message(error_message or "生图失败")
            last_http_status = http_status_code
            if is_fallback or not has_more_configs or not _should_use_fallback_api(http_status_code, last_error_message):
                break
            continue

        submit_result = _submit_async_generation_api_once(
            db,
            config=config,
            scene_key=scene_key,
            prompt=task.prompt,
            aspect_ratio=task.size,
            image_size=task.resolution,
            custom_size=task.custom_size or "",
            reference_images=ref_urls,
            mode=task_mode,
            source_image=task.source_image or "",
            mask_image=task.mask_image or "",
        )
        attempts.append(ApiAttemptRecord(
            api_config_id=config.id,
            api_config_name=config.name or "",
            attempt_index=attempt_index,
            is_fallback=is_fallback,
            status="success" if submit_result.provider_task_id else "failed",
            http_status=submit_result.http_status_code,
            error_message="" if submit_result.provider_task_id else _clip_error_message(submit_result.error_message),
            duration_ms=submit_result.duration_ms,
            external_http_ms=submit_result.external_http_ms,
            response_preview=submit_result.response_preview,
        ))
        if submit_result.provider_task_id:
            provider_started_at = now_local()
            task.provider_api_config_id = config.id
            task.provider_task_id = submit_result.provider_task_id
            task.provider_status = submit_result.provider_status or "submitted"
            task.provider_error_message = ""
            task.provider_response_preview = submit_result.response_preview
            _mark_task_request_started(task)
            task.provider_started_at = provider_started_at
            task.request_finished_at = None
            task.poll_count = 0
            task.last_polled_at = None
            task.next_poll_at = provider_started_at
            db.commit()
            selected_config = config
            break

        last_error_message = _clip_error_message(submit_result.error_message or "异步生图提交失败")
        last_http_status = submit_result.http_status_code
        if is_fallback or not has_more_configs or not _should_use_fallback_api(submit_result.http_status_code, last_error_message):
            break

    if not selected_config:
        return ApiCallResult(
            result=None,
            error_message=last_error_message,
            http_status_code=last_http_status,
            attempts=attempts,
        ), attempts

    delay_seconds = max(int(selected_config.poll_interval_seconds or 0), 1)
    try:
        _schedule_async_poll_task(task.id, delay_seconds=delay_seconds)
    except Exception as exc:
        logger.exception("Failed to schedule async generation poll; recovery scanner will retry: task_id=%s", task.id)
        task.provider_error_message = _clip_error_message(f"异步轮询调度失败，等待恢复扫描: {exc}")
        task.next_poll_at = now_local()
        db.commit()
    return ApiCallResult(
        result=None,
        error_message="",
        http_status_code=None,
        attempts=attempts,
        deferred=True,
    ), attempts


def _parse_reference_images(task: Task) -> list[str]:
    """Parse reference_images JSON string from task."""
    if not task.reference_images:
        return []
    try:
        refs = json.loads(task.reference_images)
        return refs if isinstance(refs, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _resolve_task_status(images: list[Image]) -> str:
    if any(image.status == "pending" for image in images):
        return "processing"
    if images and all(image.status == "success" for image in images):
        return "success"
    return "failed"


def _clear_task_provider_context(task: Task) -> None:
    task.provider_api_config_id = None
    task.provider_task_id = ""
    task.provider_status = ""
    task.provider_error_message = ""
    task.provider_response_preview = ""
    task.poll_count = 0
    task.last_polled_at = None
    task.next_poll_at = None
    task.provider_started_at = None


def _clear_provider_context_if_more_images_pending(task: Task, images: list[Image]) -> None:
    if any(image.status == "pending" for image in images):
        _clear_task_provider_context(task)


def _next_attempt_index_for_image(db, image: Image) -> int:
    row = (
        db.query(TaskApiAttempt.attempt_index)
        .filter(TaskApiAttempt.image_id == image.id)
        .order_by(TaskApiAttempt.attempt_index.desc(), TaskApiAttempt.id.desc())
        .first()
    )
    if not row or row[0] is None:
        return 1
    return int(row[0]) + 1


def _rebase_attempt_indices(attempts: list[ApiAttemptRecord], start_index: int) -> list[ApiAttemptRecord]:
    rebased: list[ApiAttemptRecord] = []
    for attempt in attempts:
        rebased.append(
            ApiAttemptRecord(
                api_config_id=attempt.api_config_id,
                api_config_name=attempt.api_config_name,
                attempt_index=start_index + max(int(attempt.attempt_index or 1), 1) - 1,
                is_fallback=attempt.is_fallback,
                status=attempt.status,
                http_status=attempt.http_status,
                error_message=attempt.error_message,
                duration_ms=attempt.duration_ms,
                external_http_ms=attempt.external_http_ms,
                result_download_ms=attempt.result_download_ms,
                cos_upload_ms=attempt.cos_upload_ms,
                response_preview=attempt.response_preview,
            )
        )
    return rebased


def _image_index_for_task_image(task: Task, image: Image) -> int:
    return next(
        (
            index
            for index, current in enumerate(sorted(task.images, key=lambda item: item.id), start=1)
            if current.id == image.id
        ),
        1,
    )


def _update_regenerate_log_new_image_url(db, image_id: int, image_url: str) -> None:
    normalized_url = (image_url or "").strip()
    if not normalized_url:
        return
    log = (
        db.query(RegenerateLog)
        .filter(RegenerateLog.image_id == image_id, RegenerateLog.new_image_url == "")
        .order_by(RegenerateLog.created_at.desc(), RegenerateLog.id.desc())
        .first()
    )
    if log:
        log.new_image_url = normalized_url


def _rollback_session_safely(db) -> None:
    try:
        db.rollback()
    except Exception:
        logger.exception("Failed to rollback database session")


def _is_task_processing_timed_out(task: Task) -> bool:
    timeout_seconds = max(int(settings.PROCESSING_TASK_TIMEOUT_SECONDS or 0), 0)
    if timeout_seconds <= 0 or (task.status or "") != "processing":
        return False

    last_progress_at = task.updated_at or task.enqueued_at or task.created_at
    if last_progress_at is None:
        return False

    return last_progress_at <= now_local() - timedelta(seconds=timeout_seconds)


def _get_async_provider_timeout_seconds(db, task: Task) -> int | None:
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


def _is_async_provider_task_still_polling(db, task: Task) -> bool:
    poll_timeout_seconds = _get_async_provider_timeout_seconds(db, task)
    if poll_timeout_seconds is None:
        return False

    started_at = _get_async_provider_started_at(task)
    if started_at is None:
        return False

    allowed_seconds = poll_timeout_seconds + max(int(settings.AI_TIMEOUT or 0), ASYNC_PROVIDER_TIMEOUT_GRACE_SECONDS)
    return started_at > now_local() - timedelta(seconds=allowed_seconds)


def _is_sync_request_in_flight(task: Task, *, now_value=None) -> bool:
    """同步主/备接口调用进行中时，避免按 updated_at 误杀任务。"""
    if task.request_started_at is None or task.request_finished_at is not None:
        return False
    if (task.provider_task_id or "").strip():
        return False
    current_time = now_value or now_local()
    attempt_started_at = task.updated_at or task.request_started_at
    allowed_seconds = max(int(settings.AI_TIMEOUT or 0), 1) + ASYNC_PROVIDER_TIMEOUT_GRACE_SECONDS
    return attempt_started_at > current_time - timedelta(seconds=allowed_seconds)


def _expire_processing_task(
    db,
    task: Task,
    images: list[Image] | None = None,
    *,
    reason: str = PROCESSING_TASK_TIMEOUT_ERROR,
) -> bool:
    if _is_async_provider_task_still_polling(db, task) or _is_sync_request_in_flight(task):
        return False
    if not _is_task_processing_timed_out(task):
        return False

    task_images = images if images is not None else db.query(Image).filter(Image.task_id == task.id).all()
    normalized_error = _clip_error_message(reason)
    for image in task_images:
        if image.status == "pending":
            _mark_generation_failure(image, normalized_error)

    task.status = _resolve_task_status(task_images)
    if task.status == "processing":
        task.status = "failed"
    task.error_message = "" if task.status == "success" else normalized_error
    db.commit()
    _sync_chat_generate_for_task(db, task)
    logger.error(
        "Task processing timed out: task_id=%s, timeout_seconds=%s",
        task.id,
        int(settings.PROCESSING_TASK_TIMEOUT_SECONDS or 0),
        extra={
            "event": "task.worker.timeout",
            "task_id": task_external_id(task),
            "user_id": user_external_id(task.user) if task.user else None,
            "timeout_seconds": int(settings.PROCESSING_TASK_TIMEOUT_SECONDS or 0),
        },
    )
    return True


def _recover_task_after_exception(task_id: int, error_message: str) -> None:
    recovery_db = SessionLocal()
    try:
        task = recovery_db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return

        normalized_error = _clip_error_message(error_message or "生图任务执行异常")
        images = recovery_db.query(Image).filter(Image.task_id == task_id).all()
        for image in images:
            if image.status == "pending":
                _mark_generation_failure(image, normalized_error)

        task.status = _resolve_task_status(images)
        if task.status == "processing":
            task.status = "failed"
        task.error_message = "" if task.status == "success" else normalized_error
        refund_task_credit_for_generation_failure_if_needed(recovery_db, task)
        recovery_db.commit()
        _sync_chat_generate_for_task(recovery_db, task)
    except Exception:
        _rollback_session_safely(recovery_db)
        logger.exception("Failed to recover task after exception: task_id=%s", task_id)
    finally:
        recovery_db.close()


def _recover_single_image_after_exception(image_id: int, error_message: str) -> None:
    recovery_db = SessionLocal()
    try:
        image = recovery_db.query(Image).filter(Image.id == image_id).first()
        if not image:
            return

        normalized_error = _clip_error_message(error_message or "重新生成任务执行异常")
        if image.status == "pending":
            _mark_generation_failure(image, normalized_error)

        task = recovery_db.query(Task).filter(Task.id == image.task_id).first()
        if not task:
            recovery_db.commit()
            return

        images = recovery_db.query(Image).filter(Image.task_id == task.id).all()
        task.status = _resolve_task_status(images)
        if task.status == "processing":
            task.status = "failed"
        task.error_message = "" if task.status == "success" else normalized_error
        recovery_db.commit()
    except Exception:
        _rollback_session_safely(recovery_db)
        logger.exception("Failed to recover image after exception: image_id=%s", image_id)
    finally:
        recovery_db.close()


def _process_task(task_id: int, *, use_distributed_lock: bool = True):
    started_at = time.perf_counter()
    logger.info(
        "task processing started",
        extra={
            "event": "task.worker.started",
            "task_id": task_id,
        },
    )
    task_lock = None
    if use_distributed_lock:
        task_lock = acquire_redis_lock(
            f"banana:task:process:{task_id}",
            timeout_seconds=TASK_PROCESSING_LOCK_TIMEOUT_SECONDS,
        )
        if task_lock.status == "contended":
            logger.info(
                "Skip duplicate task delivery: task_id=%s",
                task_id,
                extra={
                    "event": "task.worker.duplicate_skipped",
                    "task_id": task_id,
                },
            )
            return
        if task_lock.status == "unavailable":
            logger.error(
                "Task lock unavailable: task_id=%s",
                task_id,
                extra={
                    "event": "task.worker.lock_unavailable",
                    "task_id": task_id,
                },
            )
            raise RuntimeError(TASK_LOCK_UNAVAILABLE_ERROR)
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            logger.warning(
                "Task not found when processing started",
                extra={
                    "event": "task.worker.not_found",
                    "task_id": task_id,
                },
            )
            return
        if task.status not in {"pending", "queued", "processing"}:
            logger.info(
                "Skip task processing due to terminal status",
                extra={
                    "event": "task.worker.skipped",
                    "task_id": task_id,
                    "task_status": task.status,
                },
            )
            return
        if _expire_processing_task(db, task):
            return
        queue_duration_ms = None
        total_duration_ms = None
        if task.created_at is not None:
            now_ts = time.time()
            created_ts = task.created_at.timestamp()
            total_duration_ms = round(max(now_ts - created_ts, 0) * 1000, 2)
            if task.enqueued_at is not None:
                queue_duration_ms = round(max(task.enqueued_at.timestamp() - created_ts, 0) * 1000, 2)
            else:
                queue_duration_ms = round(
                    max((now_ts - created_ts) * 1000 - ((time.perf_counter() - started_at) * 1000), 0),
                    2,
                )
        task.status = "processing"
        task.error_message = ""
        db.commit()
        db.refresh(task)
        logger.info(
            "Task status switched to processing",
            extra={
                "event": "task.worker.processing",
                "task_id": task_external_id(task),
                "user_id": user_external_id(task.user),
                "mode": task.mode or "generate",
                "model": task.model or "",
                "queue_duration_ms": queue_duration_ms,
            },
        )

        images = db.query(Image).filter(Image.task_id == task_id).all()
        image_index_map = {
            item.id: index for index, item in enumerate(sorted(images, key=lambda current: current.id), start=1)
        }
        pending_images = [image for image in images if image.status == "pending"]
        if not pending_images:
            task.status = _resolve_task_status(images)
            task.error_message = "" if task.status == "success" else _resolve_generation_error(
                task.error_message,
                task.provider_error_message,
            )
            refund_task_credit_for_generation_failure_if_needed(db, task)
            db.commit()
            _sync_chat_generate_for_task(db, task)
            logger.info(
                "Task finished without pending images",
                extra={
                    "event": "task.worker.completed",
                    "task_id": task_external_id(task),
                    "user_id": user_external_id(task.user),
                    "task_status": task.status,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    "queue_duration_ms": queue_duration_ms,
                    "total_duration_ms": total_duration_ms,
                },
            )
            return
        all_success = all(image.status == "success" for image in images if image.status != "pending")

        for image in pending_images:
            db.refresh(task)
            if _expire_processing_task(db, task, images):
                return
            _mark_image_request_started(image)
            if _mark_task_request_started(task):
                db.commit()
                db.refresh(task)
            db.commit()
            call_result, async_submit_attempts = _execute_task_generation(db, task)
            if not call_result.deferred:
                _mark_task_request_finished(task)
                _mark_image_request_finished(image)
            attempts_to_record = async_submit_attempts or call_result.attempts

            if call_result.deferred:
                _record_api_attempts_safely(
                    db,
                    task=task,
                    image=image,
                    image_index=image_index_map.get(image.id, 1),
                    attempts=attempts_to_record,
                )
                logger.info(
                    "Async generation submitted; polling scheduled",
                    extra={
                        "event": "task.worker.async_deferred",
                        "task_id": task_external_id(task),
                        "provider_task_id": task.provider_task_id,
                    },
                )
                return

            if call_result.result:
                img_bytes, mime = call_result.result
                task.next_poll_at = None
                image.preview_url = _save_preview_image(img_bytes, mime)
                image.image_url = ""
                image.image_format = _derive_image_format(mime)
                image.image_size_bytes = len(img_bytes)
                image.status = "success"
                image.error_message = ""
                db.commit()
                cos_upload_started_perf: float | None = None
                try:
                    local_preview_url = image.preview_url
                    cos_upload_started_perf = time.perf_counter()
                    image.image_url = _save_image_bytes(db, img_bytes, mime)
                    _set_last_attempt_cos_upload_ms(attempts_to_record, _measure_elapsed_ms(cos_upload_started_perf))
                    image.preview_url = ""
                    db.commit()
                    _remove_local_preview(local_preview_url)
                except Exception as exc:
                    _set_last_attempt_cos_upload_ms(
                        attempts_to_record,
                        _measure_elapsed_ms(cos_upload_started_perf),
                    )
                    logger.exception("Failed to persist generated image to storage")
                    _mark_image_storage_fallback(image, f"图片已生成，但保存结果失败: {exc}")
                    if image.status == "failed":
                        task.error_message = image.error_message
                    all_success = image.status == "success" and all_success
                    db.commit()
            else:
                task.next_poll_at = None
                _mark_generation_failure(image, call_result.error_message)
                task.error_message = image.error_message
                all_success = False
                db.commit()

            _record_api_attempts_safely(
                db,
                task=task,
                image=image,
                image_index=image_index_map.get(image.id, 1),
                attempts=attempts_to_record,
            )
            _clear_provider_context_if_more_images_pending(task, images)
            db.commit()

        task.status = "success" if all_success else "failed"
        if task.status == "success":
            task.error_message = ""
            task.provider_error_message = ""
        else:
            task.error_message = _resolve_generation_error(task.error_message, task.provider_error_message)
        refund_task_credit_for_generation_failure_if_needed(db, task)
        db.commit()
        _sync_chat_generate_for_task(db, task)
        logger.info(
            "Task processing finished",
            extra={
                "event": "task.worker.completed",
                "task_id": task_external_id(task),
                "user_id": user_external_id(task.user),
                "task_status": task.status,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "queue_duration_ms": queue_duration_ms,
                "total_duration_ms": round(max(time.time() - task.created_at.timestamp(), 0) * 1000, 2)
                if task.created_at is not None
                else None,
            },
        )
    except Exception as exc:
        _rollback_session_safely(db)
        logger.exception(
            "Task processing crashed: task_id=%s",
            task_id,
            extra={
                "event": "task.worker.crashed",
                "task_id": task_external_id(task) if "task" in locals() and task else str(task_id),
                "user_id": user_external_id(task.user) if "task" in locals() and task else None,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "total_duration_ms": round(max(time.time() - task.created_at.timestamp(), 0) * 1000, 2)
                if "task" in locals() and task and task.created_at is not None
                else None,
            },
        )
        _recover_task_after_exception(task_id, str(exc))
    finally:
        db.close()
        if task_lock is not None:
            release_redis_lock(task_lock)


def _process_single_image(image_id: int, *, use_distributed_lock: bool = True):
    image_lock = None
    if use_distributed_lock:
        image_lock = acquire_redis_lock(
            f"banana:image:process:{image_id}",
            timeout_seconds=SINGLE_IMAGE_LOCK_TIMEOUT_SECONDS,
        )
        if image_lock.status == "contended":
            logger.info("Skip duplicate image delivery: image_id=%s", image_id)
            return
        if image_lock.status == "unavailable":
            logger.error("Image lock unavailable: image_id=%s", image_id)
            raise RuntimeError(TASK_LOCK_UNAVAILABLE_ERROR)
    db = SessionLocal()
    try:
        image = db.query(Image).filter(Image.id == image_id).first()
        if not image:
            return
        if image.status != "pending":
            return

        task = db.query(Task).filter(Task.id == image.task_id).first()
        if not task:
            _mark_generation_failure(image, "关联任务不存在")
            db.commit()
            return
        image_index_map = {
            task_image.id: index
            for index, task_image in enumerate(sorted(task.images, key=lambda current: current.id), start=1)
        }
        if _expire_processing_task(db, task, [image]):
            return

        task.status = "processing"
        task.error_message = ""
        db.commit()
        db.refresh(task)

        if _expire_processing_task(db, task, [image]):
            return

        _mark_image_request_started(image)
        if _mark_task_request_started(task):
            db.commit()
            db.refresh(task)

        db.commit()
        call_result, async_submit_attempts = _execute_task_generation(db, task)
        if not call_result.deferred:
            _mark_task_request_finished(task)
            _mark_image_request_finished(image)
        attempts_to_record = async_submit_attempts or call_result.attempts

        if call_result.deferred:
            _record_api_attempts_safely(
                db,
                task=task,
                image=image,
                image_index=image_index_map.get(image.id, 1),
                attempts=attempts_to_record,
            )
            logger.info(
                "Async regeneration submitted; polling scheduled",
                extra={
                    "event": "image.worker.async_deferred",
                    "task_id": task_external_id(task),
                    "image_id": image.id,
                    "provider_task_id": task.provider_task_id,
                },
            )
            return

        if call_result.result:
            img_bytes, mime = call_result.result
            task.next_poll_at = None
            image.preview_url = _save_preview_image(img_bytes, mime)
            image.image_url = ""
            image.image_format = _derive_image_format(mime)
            image.image_size_bytes = len(img_bytes)
            image.status = "success"
            image.error_message = ""
            db.commit()
            cos_upload_started_perf: float | None = None
            try:
                local_preview_url = image.preview_url
                cos_upload_started_perf = time.perf_counter()
                new_url = _save_image_bytes(db, img_bytes, mime)
                _set_last_attempt_cos_upload_ms(attempts_to_record, _measure_elapsed_ms(cos_upload_started_perf))
                log = (
                    db.query(RegenerateLog)
                    .filter(RegenerateLog.image_id == image_id, RegenerateLog.new_image_url == "")
                    .order_by(RegenerateLog.created_at.desc())
                    .first()
                )
                if log:
                    log.new_image_url = new_url
                image.image_url = new_url
                image.preview_url = ""
                db.commit()
                _remove_local_preview(local_preview_url)
            except Exception as exc:
                _set_last_attempt_cos_upload_ms(attempts_to_record, _measure_elapsed_ms(cos_upload_started_perf))
                logger.exception("Failed to persist regenerated image to storage")
                _mark_image_storage_fallback(image, f"图片已生成，但保存结果失败: {exc}")
                log = (
                    db.query(RegenerateLog)
                    .filter(RegenerateLog.image_id == image_id, RegenerateLog.new_image_url == "")
                    .order_by(RegenerateLog.created_at.desc())
                    .first()
                )
                if log and image.image_url:
                    log.new_image_url = image.image_url
                db.commit()
        else:
            task.next_poll_at = None
            _mark_generation_failure(image, call_result.error_message)
            db.commit()

        _record_api_attempts_safely(
            db,
            task=task,
            image=image,
            image_index=image_index_map.get(image.id, 1),
            attempts=attempts_to_record,
        )

        db.refresh(task)
        task.status = _resolve_task_status(list(task.images))
        task.error_message = "" if task.status == "success" else _resolve_generation_error(
            image.error_message,
            task.error_message,
            task.provider_error_message,
        )
        if task.status == "success":
            task.provider_error_message = ""
        db.commit()
    except Exception as exc:
        _rollback_session_safely(db)
        logger.exception("Image regeneration crashed: image_id=%s", image_id)
        _recover_single_image_after_exception(image_id, str(exc))
    finally:
        db.close()
        if image_lock is not None:
            release_redis_lock(image_lock)


def _resolve_async_poll_config(db, task: Task) -> ExternalApiConfig | None:
    if not task.provider_api_config_id:
        return None
    config = (
        db.query(ExternalApiConfig)
        .filter(
            ExternalApiConfig.id == task.provider_api_config_id,
            ExternalApiConfig.status == "enabled",
        )
        .first()
    )
    if not config or (config.call_mode or "sync").strip().lower() != "async":
        return None
    return config


def _first_pending_image(task: Task) -> Image | None:
    pending_images = [image for image in task.images if image.status == "pending"]
    if not pending_images:
        return None
    return sorted(pending_images, key=lambda image: image.id)[0]


def _is_async_poll_timeout_error(error_message: str) -> bool:
    return "异步生图轮询超时" in (error_message or "")


def _is_async_poll_failed_status(config: ExternalApiConfig, provider_status: str) -> bool:
    failed_values = {item.strip().lower() for item in parse_string_list_json(config.result_failed_values_json) if item.strip()}
    if not failed_values:
        failed_values = {"failed", "error", "cancelled"}
    failed_values.add("timeout")
    return (provider_status or "").strip().lower() in failed_values


def _sync_chat_generate_for_task(db, task: Task) -> None:
    try:
        from app.services.chat_generate_service import sync_chat_generate_status_for_tasks
        sync_chat_generate_status_for_tasks(db, [task_external_id(task)])
    except Exception:
        logger.exception("Failed to sync chat generate status: task_id=%s", task.id)


def _finalize_task_after_async_result(db, task: Task, image: Image) -> None:
    db.refresh(task)
    _mark_task_request_finished(task)
    _mark_image_request_finished(image)
    task.status = _resolve_task_status(list(task.images))
    task.error_message = "" if task.status == "success" else _resolve_generation_error(
        image.error_message,
        task.error_message,
        task.provider_error_message,
    )
    if task.status == "success":
        task.provider_error_message = ""
    refund_task_credit_for_generation_failure_if_needed(db, task)
    db.commit()
    _sync_chat_generate_for_task(db, task)


def _lock_async_result_entities(db, task_id: int, image_id: int) -> tuple[Task | None, Image | None]:
    locked_task = db.query(Task).filter(Task.id == task_id).first()
    if not locked_task:
        return None, None
    locked_image = (
        db.query(Image)
        .filter(Image.id == image_id)
        .with_for_update()
        .first()
    )
    return locked_task, locked_image


def _finish_task_after_async_poll(
    db,
    task: Task,
    image: Image,
    call_result: ApiCallResult,
    *,
    attempts_to_record: list[ApiAttemptRecord] | None = None,
) -> None:
    locked_task, locked_image = _lock_async_result_entities(db, task.id, image.id)
    if not locked_task or not locked_image:
        return
    record_attempts = (
        list(attempts_to_record)
        if attempts_to_record is not None
        else list(call_result.attempts)
    )
    if not record_attempts and (call_result.error_message or not call_result.result):
        record_attempts = [_build_async_terminal_attempt(db, locked_task, call_result)]

    if call_result.result:
        img_bytes, mime = call_result.result
        locked_task.next_poll_at = None
        if (locked_image.image_url or "").strip():
            logger.info(
                "Skip duplicate async result upload because image already has remote URL: task_id=%s image_id=%s",
                locked_task.id,
                locked_image.id,
            )
            _finalize_task_after_async_result(db, locked_task, locked_image)
            return
        if locked_image.status == "success" and (locked_image.preview_url or "").strip():
            logger.info(
                "Skip duplicate async result upload because preview already staged: task_id=%s image_id=%s",
                locked_task.id,
                locked_image.id,
            )
            _finalize_task_after_async_result(db, locked_task, locked_image)
            return

        locked_image.preview_url = _save_preview_image(img_bytes, mime)
        locked_image.image_url = ""
        locked_image.image_format = _derive_image_format(mime)
        locked_image.image_size_bytes = len(img_bytes)
        locked_image.status = "success"
        locked_image.error_message = ""
        db.commit()
        cos_upload_started_perf: float | None = None
        try:
            local_preview_url = locked_image.preview_url
            cos_upload_started_perf = time.perf_counter()
            locked_image.image_url = _save_image_bytes(db, img_bytes, mime)
            _set_last_attempt_cos_upload_ms(record_attempts, _measure_elapsed_ms(cos_upload_started_perf))
            _update_regenerate_log_new_image_url(db, locked_image.id, locked_image.image_url)
            locked_image.preview_url = ""
            db.commit()
            _remove_local_preview(local_preview_url)
        except Exception as exc:
            _set_last_attempt_cos_upload_ms(record_attempts, _measure_elapsed_ms(cos_upload_started_perf))
            logger.exception("Failed to persist async generated image to storage")
            _mark_image_storage_fallback(locked_image, f"图片已生成，但保存结果失败: {exc}")
            _update_regenerate_log_new_image_url(db, locked_image.id, locked_image.image_url)
            db.commit()
    else:
        locked_task.next_poll_at = None
        _mark_generation_failure(locked_image, call_result.error_message)
        locked_task.error_message = locked_image.error_message
        db.commit()

    _record_api_attempts_safely(
        db,
        task=locked_task,
        image=locked_image,
        image_index=_image_index_for_task_image(locked_task, locked_image),
        attempts=record_attempts,
        merge_existing=True,
    )
    _finalize_task_after_async_result(db, locked_task, locked_image)


def _retry_async_poll_with_fallback(
    db,
    *,
    task: Task,
    image: Image,
    config: ExternalApiConfig,
    call_result: ApiCallResult,
) -> tuple[ApiCallResult | None, list[ApiAttemptRecord]]:
    if call_result.deferred or call_result.result:
        return None, []
    if not (
        _is_async_poll_failed_status(config, task.provider_status or "")
        or _is_async_poll_timeout_error(call_result.error_message)
        or _is_async_poll_timeout_error(task.provider_error_message)
    ):
        return None, []
    if not _should_use_fallback_api(call_result.http_status_code, call_result.error_message):
        return None, []

    task_mode, scene_key = _resolve_task_mode_and_scene_key(task)
    primary_config, backup_config = resolve_scene_generation_configs(db, scene_key)
    if backup_config is None or primary_config.id != config.id or backup_config.id == config.id:
        return None, []

    existing_primary = _find_mergeable_async_attempt(
        db,
        image=image,
        attempt=ApiAttemptRecord(
            api_config_id=config.id,
            api_config_name=config.name or "",
            attempt_index=1,
            is_fallback=False,
            status="failed",
            http_status=None,
            error_message="",
            duration_ms=None,
        ),
    )
    primary_attempt_index = int(existing_primary.attempt_index or 1) if existing_primary else 1
    attempts = [
        ApiAttemptRecord(
            api_config_id=config.id,
            api_config_name=config.name or "",
            attempt_index=primary_attempt_index,
            is_fallback=False,
            status="failed",
            http_status=call_result.http_status_code,
            error_message=_clip_error_message(call_result.error_message),
            duration_ms=None,
            response_preview=task.provider_response_preview or "",
        )
    ]

    logger.warning(
        "Async poll failed on primary config; retrying with fallback submit: task_id=%s, primary_config_id=%s, fallback_config_id=%s",
        task.id,
        config.id,
        backup_config.id,
    )
    _clear_task_provider_context(task)
    task.error_message = ""
    db.commit()

    fallback_result, fallback_attempts = _submit_generation_with_configs(
        db,
        task=task,
        scene_key=scene_key,
        task_mode=task_mode,
        ref_urls=_parse_reference_images(task),
        configs_to_try=[(backup_config, True)],
    )
    attempts.extend(_rebase_attempt_indices(fallback_attempts, primary_attempt_index + 1))

    if not fallback_result.deferred and not fallback_result.result and fallback_result.error_message:
        task.provider_error_message = _clip_error_message(fallback_result.error_message)
        db.commit()
    return fallback_result, attempts


def _claim_due_async_poll_task(db, task: Task, now_value) -> bool:
    lease_until = now_value + timedelta(seconds=ASYNC_POLL_CLAIM_LEASE_SECONDS)
    updated_count = (
        db.query(Task)
        .filter(
            Task.id == task.id,
            Task.status == "processing",
            Task.provider_task_id != "",
            Task.next_poll_at.is_not(None),
            Task.next_poll_at <= now_value,
            Task.is_deleted.is_(False),
        )
        .update(
            {Task.next_poll_at: lease_until},
            synchronize_session=False,
        )
    )
    db.commit()
    if not updated_count:
        logger.info(
            "Skip async poll because another web worker claimed it: task_id=%s",
            task.id,
        )
        return False
    db.refresh(task)
    return True


def _process_async_poll_task(task_id: int, *, use_distributed_lock: bool = True):
    poll_lock = None
    if use_distributed_lock:
        poll_lock = acquire_redis_lock(
            f"banana:task:poll:{task_id}",
            timeout_seconds=max(int(settings.AI_TIMEOUT or 0) + 60, 120),
            blocking_timeout_seconds=0,
        )
        if poll_lock.status == "contended":
            logger.info("Skip duplicate async poll delivery: task_id=%s", task_id)
            return
        if poll_lock.status == "unavailable":
            logger.error("Async poll lock unavailable: task_id=%s", task_id)
            raise RuntimeError(TASK_LOCK_UNAVAILABLE_ERROR)

    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return
        if task.status != "processing" or not (task.provider_task_id or "").strip():
            return

        config = _resolve_async_poll_config(db, task)
        if not config:
            task.provider_error_message = "异步轮询配置不存在或未启用"
            image = _first_pending_image(task)
            if image:
                _mark_generation_failure(image, task.provider_error_message)
            task.status = _resolve_task_status(list(task.images))
            task.error_message = _clip_error_message(task.provider_error_message)
            _mark_task_request_finished(task)
            refund_task_credit_for_generation_failure_if_needed(db, task)
            db.commit()
            return

        now_value = now_local()
        if task.next_poll_at and task.next_poll_at > now_value:
            _schedule_async_poll_task(task.id, delay_seconds=max(int((task.next_poll_at - now_value).total_seconds()), 1))
            return
        if not task.next_poll_at or not _claim_due_async_poll_task(db, task, now_value):
            return

        image = _first_pending_image(task)
        if not image:
            task.status = _resolve_task_status(list(task.images))
            _mark_task_request_finished(task)
            db.commit()
            return

        call_result = _poll_async_generation_once(db, task, config=config)
        if call_result.deferred:
            delay_seconds = max(int(config.poll_interval_seconds or 0), 1)
            if task.next_poll_at:
                delay_seconds = max(int((task.next_poll_at - now_local()).total_seconds()), 1)
            _schedule_async_poll_task(task.id, delay_seconds=delay_seconds)
            return

        fallback_result, fallback_attempts = _retry_async_poll_with_fallback(
            db,
            task=task,
            image=image,
            config=config,
            call_result=call_result,
        )
        if fallback_result is not None:
            if fallback_result.deferred:
                _record_api_attempts_safely(
                    db,
                    task=task,
                    image=image,
                    image_index=_image_index_for_task_image(task, image),
                    attempts=fallback_attempts,
                    merge_existing=True,
                )
                logger.info(
                    "Async poll switched to fallback submit",
                    extra={
                        "event": "task.worker.async_fallback_resubmitted",
                        "task_id": task.id,
                        "provider_task_id": task.provider_task_id,
                    },
                )
                return
            _finish_task_after_async_poll(db, task, image, fallback_result, attempts_to_record=fallback_attempts)
            return

        _finish_task_after_async_poll(db, task, image, call_result)
    except RuntimeError:
        raise
    except Exception as exc:
        _rollback_session_safely(db)
        logger.exception("Async poll task crashed: task_id=%s", task_id)
        _recover_task_after_exception(task_id, str(exc))
    finally:
        db.close()
        if poll_lock is not None:
            release_redis_lock(poll_lock)


# --- Celery tasks ---

def _redis_reachable() -> bool:
    """Quick check: can we actually connect to the Redis broker?"""
    try:
        import redis
        r = redis.Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1
        )
        r.ping()
        return True
    except Exception:
        return False


try:
    from app.workers.celery_app import celery_app
    CELERY_AVAILABLE = _redis_reachable()
    if not CELERY_AVAILABLE:
        if settings.allow_sync_generation_fallback:
            logger.info("Redis not reachable — falling back to sync thread mode")
        else:
            logger.warning("Redis not reachable — sync fallback disabled")
except Exception:
    CELERY_AVAILABLE = False
    celery_app = None

if CELERY_AVAILABLE and celery_app:
    @celery_app.task(bind=True, max_retries=2)
    def generate_images_task(self, task_id: int):
        try:
            _process_task(task_id)
        except RuntimeError as exc:
            if str(exc) == TASK_LOCK_UNAVAILABLE_ERROR:
                raise self.retry(exc=exc, countdown=2) from exc
            raise

    @celery_app.task(bind=True, max_retries=2)
    def regenerate_single_image_task(self, image_id: int):
        try:
            _process_single_image(image_id)
        except RuntimeError as exc:
            if str(exc) == TASK_LOCK_UNAVAILABLE_ERROR:
                raise self.retry(exc=exc, countdown=2) from exc
            raise

    @celery_app.task(bind=True, max_retries=2)
    def poll_async_generation_task(self, task_id: int):
        try:
            _process_async_poll_task(task_id)
        except RuntimeError as exc:
            if str(exc) == TASK_LOCK_UNAVAILABLE_ERROR:
                raise self.retry(exc=exc, countdown=2) from exc
            raise
else:
    def generate_images_task():
        raise RuntimeError("Celery not available")

    def regenerate_single_image_task():
        raise RuntimeError("Celery not available")

    def poll_async_generation_task():
        raise RuntimeError("Celery not available")


def _celery_dispatch_available() -> bool:
    if celery_app is None:
        return False
    if not callable(getattr(generate_images_task, "delay", None)):
        return False
    return _redis_reachable()


# --- Sync fallbacks (for dev without Redis) ---

def _run_sync_generation_worker(target, *args) -> None:
    try:
        target(*args, use_distributed_lock=False)
    finally:
        _sync_generation_semaphore.release()


def generate_images_sync(task_id: int):
    if not _sync_generation_semaphore.acquire(blocking=False):
        raise RuntimeError(QUEUE_UNAVAILABLE_ERROR)
    threading.Thread(
        target=_run_sync_generation_worker,
        args=(_process_task, task_id),
        daemon=True,
    ).start()


def regenerate_single_sync(image_id: int):
    if not _sync_generation_semaphore.acquire(blocking=False):
        raise RuntimeError(QUEUE_UNAVAILABLE_ERROR)
    threading.Thread(
        target=_run_sync_generation_worker,
        args=(_process_single_image, image_id),
        daemon=True,
    ).start()


def _run_sync_async_poll_worker(task_id: int) -> None:
    _process_async_poll_task(task_id, use_distributed_lock=False)


def _schedule_async_poll_task(task_id: int, *, delay_seconds: int) -> None:
    normalized_delay = max(int(delay_seconds or 0), 0)
    if _celery_dispatch_available():
        poll_async_generation_task.apply_async(args=[task_id], countdown=normalized_delay)
        logger.info(
            "Scheduled async generation poll via celery",
            extra={
                "event": "task.worker.async_poll_scheduled",
                "task_id": task_id,
                "dispatch_mode": "celery",
                "delay_seconds": normalized_delay,
            },
        )
        return

    if not _sync_fallback_allowed():
        raise RuntimeError(QUEUE_UNAVAILABLE_ERROR)

    timer = threading.Timer(normalized_delay, _run_sync_async_poll_worker, args=(task_id,))
    timer.daemon = True
    timer.start()
    logger.info(
        "Scheduled async generation poll via timer",
        extra={
            "event": "task.worker.async_poll_scheduled",
            "task_id": task_id,
            "dispatch_mode": "sync",
            "delay_seconds": normalized_delay,
        },
    )


def _recover_due_async_poll_tasks_once() -> int:
    recovery_lock = None
    if CELERY_AVAILABLE and celery_app:
        recovery_lock = acquire_redis_lock(
            "banana:task:poll:recovery",
            timeout_seconds=max(ASYNC_POLL_RECOVERY_INTERVAL_SECONDS - 1, 1),
            blocking_timeout_seconds=0,
        )
        if recovery_lock.status == "contended":
            return 0
        if recovery_lock.status == "unavailable":
            recovery_lock = None

    db = SessionLocal()
    try:
        now_value = now_local()
        stale_cutoff = now_value - timedelta(seconds=ASYNC_POLL_RECOVERY_INTERVAL_SECONDS)
        tasks = (
            db.query(Task)
            .filter(
                Task.status == "processing",
                Task.provider_task_id != "",
                Task.is_deleted.is_(False),
                or_(
                    and_(Task.next_poll_at.is_not(None), Task.next_poll_at <= now_value),
                    and_(
                        Task.next_poll_at.is_(None),
                        Task.updated_at.is_not(None),
                        Task.updated_at <= stale_cutoff,
                    ),
                ),
            )
            .order_by(Task.next_poll_at.asc(), Task.id.asc())
            .limit(ASYNC_POLL_RECOVERY_BATCH_SIZE)
            .all()
        )
        recovered_count = 0
        for task in tasks:
            try:
                if task.next_poll_at is None:
                    task.next_poll_at = now_value
                    db.commit()
                _schedule_async_poll_task(task.id, delay_seconds=0)
                recovered_count += 1
            except Exception:
                logger.exception("Failed to recover async poll schedule: task_id=%s", task.id)
        return recovered_count
    finally:
        db.close()
        if recovery_lock is not None:
            release_redis_lock(recovery_lock)


def _async_poll_recovery_loop() -> None:
    while True:
        try:
            recovered_count = _recover_due_async_poll_tasks_once()
            if recovered_count:
                logger.info(
                    "Recovered due async poll tasks",
                    extra={
                        "event": "task.worker.async_poll_recovered",
                        "task_count": recovered_count,
                    },
                )
        except Exception:
            logger.exception("Async poll recovery scanner failed")
        time.sleep(ASYNC_POLL_RECOVERY_INTERVAL_SECONDS)


def _start_async_poll_recovery_scanner() -> None:
    global _async_poll_recovery_started
    with _async_poll_recovery_lock:
        if _async_poll_recovery_started:
            return
        _async_poll_recovery_started = True
    thread = threading.Thread(target=_async_poll_recovery_loop, daemon=True)
    thread.start()


def _sync_fallback_allowed() -> bool:
    return settings.allow_sync_generation_fallback


def get_generation_dispatch_mode() -> str:
    if _celery_dispatch_available():
        return "celery"
    if _sync_fallback_allowed():
        return "sync"
    raise RuntimeError(QUEUE_UNAVAILABLE_ERROR)


def dispatch_generation_task(task_id: int) -> str:
    mode = get_generation_dispatch_mode()
    if mode == "celery":
        try:
            logger.info(
                "Dispatch generation task to celery",
                extra={
                    "event": "task.worker.dispatched",
                    "task_id": task_id,
                    "dispatch_mode": "celery",
                },
            )
            generate_images_task.delay(task_id)
            return "queued"
        except Exception:
            if not _sync_fallback_allowed():
                raise
            logger.exception(
                "Celery dispatch failed, falling back to sync thread mode",
                extra={
                    "event": "task.worker.dispatch_fallback",
                    "task_id": task_id,
                },
            )
    logger.info(
        "Dispatch generation task to sync worker",
        extra={
            "event": "task.worker.dispatched",
            "task_id": task_id,
            "dispatch_mode": "sync",
        },
    )
    generate_images_sync(task_id)
    return "sync"


def dispatch_regenerate_task(image_id: int) -> str:
    mode = get_generation_dispatch_mode()
    if mode == "celery":
        try:
            regenerate_single_image_task.delay(image_id)
            return "queued"
        except Exception:
            if not _sync_fallback_allowed():
                raise
            logger.exception(
                "Celery regenerate dispatch failed, falling back to sync thread mode",
                extra={
                    "event": "task.worker.regenerate_dispatch_fallback",
                    "image_id": image_id,
                },
            )
    regenerate_single_sync(image_id)
    return "sync"


_start_async_poll_recovery_scanner()
