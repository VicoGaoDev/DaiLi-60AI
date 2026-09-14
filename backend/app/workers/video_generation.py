from __future__ import annotations

import base64
import json
import logging
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.database import SessionLocal
from app.models.video_result import VideoResult
from app.models.video_task import VideoTask
from app.models.video_task_api_attempt import VideoTaskApiAttempt
from app.services.cos_service import load_image_bytes
from app.services.external_api_config_service import (
    build_external_poll_request_kwargs,
    build_external_request_kwargs,
    build_secret_variables,
    parse_http_statuses_json,
    parse_string_list_json,
    read_value_by_path,
    render_config,
    render_poll_config,
)
from app.services.image_delivery_service import get_optional_cos_config, serialize_asset_urls
from app.services.video_external_api_config_service import (
    resolve_mapped_video_resolution,
    resolve_video_scene_generation_configs,
)
from app.services.video_task_service import refund_video_task_credit_for_failure_if_needed
from app.utils.datetime_utils import now_local

logger = logging.getLogger(__name__)
MAX_ERROR_MESSAGE_LENGTH = 1800
MAX_RESPONSE_PREVIEW_LENGTH = 1200


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


def _clip_error_message(message: str) -> str:
    cleaned = (message or "").strip()
    if len(cleaned) <= MAX_ERROR_MESSAGE_LENGTH:
        return cleaned
    return cleaned[:MAX_ERROR_MESSAGE_LENGTH] + "..."


def _clip_response_preview(payload: object) -> str:
    try:
        preview = json.dumps(payload, ensure_ascii=False)
    except Exception:
        preview = str(payload)
    preview = (preview or "").strip() or "(空响应)"
    if len(preview) <= MAX_RESPONSE_PREVIEW_LENGTH:
        return preview
    return preview[:MAX_RESPONSE_PREVIEW_LENGTH] + "..."


def _compose_result_error(message: str, payload: object) -> str:
    normalized_message = (message or "").strip() or "视频生成失败"
    preview = _clip_response_preview(payload)
    if not preview or preview == "(空响应)":
        return normalized_message
    return f"{normalized_message}\n轮询结果: {preview}"


def _compose_http_error(message: str, response_body: str) -> str:
    normalized_message = (message or "").strip() or "视频生成失败"
    preview = (response_body or "").strip() or "(空响应)"
    if len(preview) > MAX_RESPONSE_PREVIEW_LENGTH:
        preview = preview[:MAX_RESPONSE_PREVIEW_LENGTH] + "..."
    return f"{normalized_message}\n返回内容: {preview}"


def _normalize_status(value: object) -> str:
    return str(value or "").strip()


def _extract_text_value(payload: object, field_path: str) -> str:
    raw_value, _parent = read_value_by_path(payload, field_path or "")
    return str(raw_value or "").strip()


def _read_file_as_base64(image_url: str) -> tuple[str, str] | None:
    result = load_image_bytes(image_url)
    if not result:
        return None
    data, mime_type = result
    return mime_type, base64.b64encode(data).decode("ascii")


def _build_reference_image_payload(image_url: str) -> dict[str, object] | None:
    ref = _read_file_as_base64(image_url)
    if not ref:
        return None
    mime_type, b64 = ref
    return {
        "mime_type": mime_type,
        "base64": b64,
        "data_url": f"data:{mime_type};base64,{b64}",
        "inline_part": {
            "inlineData": {
                "mimeType": mime_type,
                "data": b64,
            }
        },
    }


def _parse_reference_images(task: VideoTask) -> list[str]:
    if not task.reference_images:
        return []
    try:
        parsed = json.loads(task.reference_images)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(item or "").strip() for item in parsed if str(item or "").strip()]


def _add_frame_alias_variables(render_variables: dict[str, object], index: int, reference_payload: dict[str, object]) -> None:
    if index not in (1, 2):
        return
    prefix = "first_frame" if index == 1 else "last_frame"
    inline_part = reference_payload["inline_part"]
    render_variables[f"{prefix}_image"] = inline_part
    render_variables[f"{prefix}_image_base64"] = reference_payload["base64"]
    render_variables[f"{prefix}_image_mime_type"] = reference_payload["mime_type"]
    render_variables[f"{prefix}_image_data_url"] = reference_payload["data_url"]


def _infer_video_format(video_url: str, mime_type: str) -> str:
    if mime_type:
        return mime_type.split("/")[-1].lower()
    path = urlparse(video_url or "").path.lower()
    if "." in path:
        return path.rsplit(".", 1)[-1]
    return "mp4"


def _extract_video_result_payload(
    payload: object,
    *,
    video_url_field: str,
    cover_url_field: str,
) -> tuple[dict | None, str]:
    video_url = _extract_text_value(payload, video_url_field) if video_url_field else ""
    cover_url = _extract_text_value(payload, cover_url_field) if cover_url_field else ""
    if video_url:
        return {
            "video_url": video_url,
            "cover_url": cover_url,
            "video_format": _infer_video_format(video_url, ""),
            "video_size_bytes": 0,
        }, ""

    return None, _compose_result_error("视频接口返回内容缺少视频结果 URL，请检查结果 URL 路径配置", payload)


def _call_sync_video_generation_api_once(db, *, config, task: VideoTask) -> tuple[dict | None, str, int | None, int | None]:
    request_started_perf = time.perf_counter()
    try:
        mapped_resolution = resolve_mapped_video_resolution(db, task.model or "", task.resolution or "")
        cos_config = get_optional_cos_config(db)
        reference_images = _parse_reference_images(task)
        render_variables = {
            **build_secret_variables(db),
            "prompt": task.prompt or "",
            "duration_seconds": int(task.duration_seconds or 0),
            "aspect_ratio": task.aspect_ratio or "",
            "resolution": task.resolution or "",
            "mapped_resolution": mapped_resolution,
            "generation_mode": task.generation_mode or "",
            "reference_image_count": 0,
        }
        reference_count = 0
        for ref_url in reference_images:
            reference_count += 1
            index = reference_count
            render_variables[f"reference_image_{index}_url"] = serialize_asset_urls(ref_url, cos_config=cos_config)["image_url"]
            if index in (1, 2):
                render_variables[f"{'first_frame' if index == 1 else 'last_frame'}_image_url"] = render_variables[f"reference_image_{index}_url"]
            reference_payload = _build_reference_image_payload(ref_url)
            if not reference_payload:
                continue
            inline_part = reference_payload["inline_part"]
            if not isinstance(inline_part, dict):
                continue
            render_variables[f"reference_image_{index}"] = inline_part
            render_variables[f"reference_image_{index}_base64"] = reference_payload["base64"]
            render_variables[f"reference_image_{index}_mime_type"] = reference_payload["mime_type"]
            render_variables[f"reference_image_{index}_data_url"] = reference_payload["data_url"]
            _add_frame_alias_variables(render_variables, index, reference_payload)
        render_variables["reference_image_count"] = reference_count
        rendered = render_config(config, render_variables)
        request_kwargs = build_external_request_kwargs(rendered)
        with httpx.Client(timeout=settings.AI_TIMEOUT, trust_env=False) as client:
            response = client.post(rendered.request_url, **request_kwargs)
        duration_ms = max(int(round((time.perf_counter() - request_started_perf) * 1000)), 0)
        if response.status_code < 200 or response.status_code >= 300:
            return None, _clip_error_message(_compose_http_error(f"视频接口返回 HTTP {response.status_code}", response.text or "")), response.status_code, duration_ms
        payload = response.json()
        result, error_message = _extract_video_result_payload(
            payload,
            video_url_field=config.result_video_url_field or "",
            cover_url_field=config.result_cover_url_field or "",
        )
        return result, _clip_error_message(error_message), None, duration_ms
    except Exception as exc:
        duration_ms = max(int(round((time.perf_counter() - request_started_perf) * 1000)), 0)
        return None, _clip_error_message(f"视频接口调用异常: {exc}"), None, duration_ms


def _poll_async_video_result(db, *, task: VideoTask, config) -> tuple[dict | None, str]:
    poll_interval_seconds = max(int(config.poll_interval_seconds or 5), 1)
    poll_timeout_seconds = max(int(config.poll_timeout_seconds or 600), 1)
    success_values = {item.strip().lower() for item in parse_string_list_json(config.result_success_values_json) if item.strip()}
    failed_values = {item.strip().lower() for item in parse_string_list_json(config.result_failed_values_json) if item.strip()}
    if not success_values:
        success_values = {"success", "succeeded", "completed"}
    if not failed_values:
        failed_values = {"failed", "error", "cancelled"}

    started_at = time.time()
    while True:
        if time.time() - started_at > poll_timeout_seconds:
            return None, f"异步视频任务轮询超时（超过 {poll_timeout_seconds} 秒）"

        time.sleep(poll_interval_seconds)
        mapped_resolution = resolve_mapped_video_resolution(db, task.model or "", task.resolution or "")
        rendered = render_poll_config(
            config,
            {
                **build_secret_variables(db),
                "provider_task_id": task.provider_task_id,
                "task_id": task.provider_task_id,
                "prompt": task.prompt or "",
                "duration_seconds": int(task.duration_seconds or 0),
                "aspect_ratio": task.aspect_ratio or "",
                "resolution": task.resolution or "",
                "mapped_resolution": mapped_resolution,
                "generation_mode": task.generation_mode or "",
            },
        )
        request_kwargs = build_external_poll_request_kwargs(rendered)
        try:
            with httpx.Client(timeout=settings.AI_TIMEOUT, trust_env=False) as client:
                response = client.request(rendered.method, rendered.request_url, **request_kwargs)
            if response.status_code < 200 or response.status_code >= 300:
                task.provider_error_message = _clip_error_message(
                    _compose_http_error(f"异步视频轮询返回 HTTP {response.status_code}", response.text or "")
                )
                task.last_polled_at = now_local()
                task.poll_count = int(task.poll_count or 0) + 1
                db.commit()
                continue
            payload = response.json()
        except Exception as exc:
            task.provider_error_message = _clip_error_message(f"异步视频轮询异常: {exc}")
            task.last_polled_at = now_local()
            task.poll_count = int(task.poll_count or 0) + 1
            db.commit()
            continue

        provider_status = _normalize_status(_extract_text_value(payload, config.result_status_field or "")) or "processing"
        task.provider_status = provider_status
        task.provider_response_preview = _clip_response_preview(payload)
        task.provider_error_message = ""
        task.last_polled_at = now_local()
        task.poll_count = int(task.poll_count or 0) + 1
        db.commit()

        normalized_status = provider_status.lower()
        if normalized_status in success_values:
            return _extract_video_result_payload(
                payload,
                video_url_field=config.poll_result_video_url_field or "",
                cover_url_field=config.poll_result_cover_url_field or "",
            )
        if normalized_status in failed_values:
            error_message = _extract_text_value(payload, config.result_error_field or "") or f"异步视频任务失败，状态为 {provider_status}"
            return None, _clip_error_message(_compose_result_error(error_message, payload))


def _submit_async_video_generation_api_once(db, *, config, task: VideoTask) -> tuple[dict | None, str, int | None, int | None]:
    request_started_perf = time.perf_counter()
    try:
        mapped_resolution = resolve_mapped_video_resolution(db, task.model or "", task.resolution or "")
        cos_config = get_optional_cos_config(db)
        reference_images = _parse_reference_images(task)
        render_variables = {
            **build_secret_variables(db),
            "prompt": task.prompt or "",
            "duration_seconds": int(task.duration_seconds or 0),
            "aspect_ratio": task.aspect_ratio or "",
            "resolution": task.resolution or "",
            "mapped_resolution": mapped_resolution,
            "generation_mode": task.generation_mode or "",
            "reference_image_count": 0,
        }
        reference_count = 0
        for ref_url in reference_images:
            reference_count += 1
            index = reference_count
            render_variables[f"reference_image_{index}_url"] = serialize_asset_urls(ref_url, cos_config=cos_config)["image_url"]
            if index in (1, 2):
                render_variables[f"{'first_frame' if index == 1 else 'last_frame'}_image_url"] = render_variables[f"reference_image_{index}_url"]
            reference_payload = _build_reference_image_payload(ref_url)
            if not reference_payload:
                continue
            inline_part = reference_payload["inline_part"]
            if not isinstance(inline_part, dict):
                continue
            render_variables[f"reference_image_{index}"] = inline_part
            render_variables[f"reference_image_{index}_base64"] = reference_payload["base64"]
            render_variables[f"reference_image_{index}_mime_type"] = reference_payload["mime_type"]
            render_variables[f"reference_image_{index}_data_url"] = reference_payload["data_url"]
            _add_frame_alias_variables(render_variables, index, reference_payload)
        render_variables["reference_image_count"] = reference_count
        rendered = render_config(config, render_variables)
        request_kwargs = build_external_request_kwargs(rendered)
        with httpx.Client(timeout=settings.AI_TIMEOUT, trust_env=False) as client:
            response = client.post(rendered.request_url, **request_kwargs)
        duration_ms = max(int(round((time.perf_counter() - request_started_perf) * 1000)), 0)
        success_statuses = parse_http_statuses_json(config.submit_success_statuses_json) or [200, 201, 202]
        if response.status_code not in success_statuses:
            return None, _clip_error_message(_compose_http_error(f"异步视频提交返回 HTTP {response.status_code}", response.text or "")), response.status_code, duration_ms
        payload = response.json()
        provider_task_id = _extract_text_value(payload, config.task_id_field or "")
        if not provider_task_id:
            return None, _clip_error_message(_compose_result_error("异步视频提交成功，但未解析到第三方任务 ID", payload)), response.status_code, duration_ms
        task.provider_api_config_id = config.id
        task.provider_task_id = provider_task_id
        task.provider_status = _extract_text_value(payload, config.result_status_field or "") or "submitted"
        task.provider_response_preview = _clip_response_preview(payload)
        task.provider_error_message = ""
        db.commit()
        result_payload, error_message = _poll_async_video_result(db, task=task, config=config)
        duration_ms = max(int(round((time.perf_counter() - request_started_perf) * 1000)), 0)
        return result_payload, error_message, None, duration_ms
    except Exception as exc:
        duration_ms = max(int(round((time.perf_counter() - request_started_perf) * 1000)), 0)
        return None, _clip_error_message(f"异步视频提交异常: {exc}"), None, duration_ms


def _record_api_attempts(db, *, task: VideoTask, attempts: list[ApiAttemptRecord]) -> None:
    if not attempts:
        return
    used_fallback = False
    for attempt in attempts:
        used_fallback = used_fallback or attempt.is_fallback
        db.add(
            VideoTaskApiAttempt(
                task_id=task.id,
                api_config_id=attempt.api_config_id,
                api_config_name=attempt.api_config_name,
                attempt_index=attempt.attempt_index,
                is_fallback=attempt.is_fallback,
                status=attempt.status,
                http_status=attempt.http_status,
                error_message=attempt.error_message,
                duration_ms=attempt.duration_ms,
            )
        )
    task.used_fallback_api = used_fallback
    db.add(task)


def _ensure_result_row(db, task: VideoTask) -> VideoResult:
    result = task.results[0] if task.results else None
    if result is None:
        result = VideoResult(task_id=task.id, status="pending", error_message="")
        db.add(result)
        db.flush()
    return result


def _process_video_task(task_id: int) -> None:
    db = SessionLocal()
    try:
        task = db.query(VideoTask).filter(VideoTask.id == task_id).first()
        if not task or task.status not in {"pending", "queued", "processing"}:
            return
        result_row = _ensure_result_row(db, task)
        task.status = "processing"
        task.error_message = ""
        task.request_started_at = task.request_started_at or now_local()
        db.commit()

        primary_config, backup_config = resolve_video_scene_generation_configs(db, task.model or "")
        configs_to_try = [(primary_config, False)]
        if backup_config is not None:
            configs_to_try.append((backup_config, True))

        attempts: list[ApiAttemptRecord] = []
        result_payload = None
        error_message = "视频生成失败"
        for attempt_index, (config, is_fallback) in enumerate(configs_to_try, start=1):
            task.provider_api_config_id = config.id
            db.commit()
            result_payload, error_message, http_status, duration_ms = _submit_async_video_generation_api_once(
                db,
                config=config,
                task=task,
            )
            attempts.append(
                ApiAttemptRecord(
                    api_config_id=config.id,
                    api_config_name=config.name or "",
                    attempt_index=attempt_index,
                    is_fallback=is_fallback,
                    status="success" if result_payload else "failed",
                    http_status=http_status,
                    error_message="" if result_payload else _clip_error_message(error_message),
                    duration_ms=duration_ms,
                )
            )
            if result_payload:
                break

        _record_api_attempts(db, task=task, attempts=attempts)

        if result_payload:
            result_row.video_url = result_payload.get("video_url", "")
            result_row.cover_url = result_payload.get("cover_url", "")
            result_row.video_format = result_payload.get("video_format", "")
            result_row.video_size_bytes = int(result_payload.get("video_size_bytes", 0) or 0)
            result_row.duration_seconds = int(task.duration_seconds or 0)
            result_row.status = "success"
            result_row.error_message = ""
            task.status = "success"
            task.error_message = ""
            task.provider_error_message = ""
        else:
            result_row.video_url = ""
            result_row.cover_url = ""
            result_row.video_format = ""
            result_row.video_size_bytes = 0
            result_row.duration_seconds = int(task.duration_seconds or 0)
            result_row.status = "failed"
            result_row.error_message = _clip_error_message(error_message)
            task.status = "failed"
            task.error_message = _clip_error_message(error_message)
            task.provider_error_message = _clip_error_message(error_message)
            refund_video_task_credit_for_failure_if_needed(db, task)

        task.request_finished_at = now_local()
        db.commit()
    except Exception as exc:
        logger.exception("Video task processing crashed: task_id=%s", task_id)
        db.rollback()
        task = db.query(VideoTask).filter(VideoTask.id == task_id).first()
        if task:
            result_row = _ensure_result_row(db, task)
            task.status = "failed"
            task.error_message = _clip_error_message(f"视频任务处理异常: {exc}")
            task.provider_error_message = task.error_message
            task.request_finished_at = now_local()
            result_row.status = "failed"
            result_row.error_message = task.error_message
            refund_video_task_credit_for_failure_if_needed(db, task)
            db.commit()
    finally:
        db.close()


def dispatch_video_generation_task(task_id: int) -> str:
    thread = threading.Thread(
        target=_process_video_task,
        args=(task_id,),
        name=f"video-task-{task_id}",
        daemon=True,
    )
    thread.start()
    return "thread"
