from __future__ import annotations

import json
import re
from urllib.parse import urlparse, urlunparse

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models.image import Image
from app.models.task import Task
from app.models.task_api_attempt import TaskApiAttempt
from app.services.business_id_service import task_external_id
from app.services.cos_service import CosRuntimeConfig, build_cos_public_url, get_cos_config
from app.services.task_service import is_task_generation_failure_credit_refunded

IMAGE_SAFETY_ERROR_MESSAGE = "生成的图片存在安全风险（色情、暴力、版权、政治敏感等），请尝试修改提示词或参考图，或换个模型尝试（不同模型审查尺度不同）！"
PROMPT_MODERATION_ERROR_MESSAGE = "提示词或参考图审核未通过"
GENERATION_TASK_FAILURE_MESSAGE = "生图失败，请反馈给我们处理"
INVALID_REFERENCE_IMAGE_MESSAGE = "参考图被模型拒绝，请更换正常格式的参考图后重试；或换个模型尝试（不同模型审查尺度不同）！"
INVALID_ASPECT_RATIO_MESSAGE = "当前宽高比不受支持，请更换其他宽高比后重试"

PROMPT_MODERATION_ERROR_PATTERN = re.compile(
    r"\b(?:safety|prompt|moderation)\b|提示词|审核",
    re.IGNORECASE,
)
IMAGE_SAFETY_ERROR_PATTERN = re.compile(r"unsafe|image_unsafe|content blocked", re.IGNORECASE)
INVALID_ASPECT_RATIO_PATTERN = re.compile(r"n?put\.aspect_ratio is invalid|aspect_ratio is invalid", re.IGNORECASE)
INVALID_REFERENCE_IMAGE_PATTERN = re.compile(
    r"invalid image file or mode|provider_request_invalid|bad request to openai|poll rejected: 400|image \d+",
    re.IGNORECASE,
)


def format_generation_public_error_message(error_message: str | None) -> str:
    detail = (error_message or "").strip()
    if not detail:
        return ""
    if PROMPT_MODERATION_ERROR_PATTERN.search(detail):
        return PROMPT_MODERATION_ERROR_MESSAGE
    if IMAGE_SAFETY_ERROR_PATTERN.search(detail):
        return IMAGE_SAFETY_ERROR_MESSAGE
    if INVALID_ASPECT_RATIO_PATTERN.search(detail):
        return INVALID_ASPECT_RATIO_MESSAGE
    if INVALID_REFERENCE_IMAGE_PATTERN.search(detail):
        return INVALID_REFERENCE_IMAGE_MESSAGE
    return GENERATION_TASK_FAILURE_MESSAGE


def get_optional_cos_config(db: Session) -> CosRuntimeConfig | None:
    try:
        return get_cos_config(db)
    except HTTPException:
        return None


def _normalize_url(value: str | None) -> str:
    return (value or "").strip()


def resolve_avatar_url(
    avatar_url: str | None,
    *,
    cos_config: CosRuntimeConfig | None = None,
) -> str:
    canonical_url = _normalize_url(avatar_url)
    if not canonical_url:
        return ""
    if canonical_url.startswith("data:"):
        return canonical_url

    parsed = urlparse(canonical_url)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        if _looks_like_cos_url(canonical_url, cos_config):
            return canonical_url
        path = parsed.path or ""
        if "/uploads/avatar/" in path or path.startswith("/avatar/") or "/avatar/" in path:
            if cos_config:
                return build_cos_public_url(cos_config, path.lstrip("/"))
        return canonical_url

    if not cos_config:
        return canonical_url
    return build_cos_public_url(cos_config, canonical_url.lstrip("/"))


def resolve_user_avatar_url(user, *, cos_config: CosRuntimeConfig | None = None) -> str:
    if not user:
        return ""
    return resolve_avatar_url(getattr(user, "avatar_url", None), cos_config=cos_config)


def normalize_external_image_url(
    image_url: str | None,
    *,
    cos_config: CosRuntimeConfig | None = None,
) -> str:
    canonical_url = _normalize_url(image_url)
    if not canonical_url:
        return ""

    parsed = urlparse(canonical_url)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return canonical_url
    if canonical_url.startswith("data:"):
        return canonical_url
    if canonical_url.startswith("/uploads/") or canonical_url.startswith("uploads/"):
        return canonical_url
    if cos_config:
        return build_cos_public_url(cos_config, canonical_url)
    return canonical_url


def _looks_like_cos_url(image_url: str, cos_config: CosRuntimeConfig | None) -> bool:
    parsed = urlparse(image_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    if parsed.netloc.endswith(".myqcloud.com"):
        return True
    if not cos_config:
        return False
    return parsed.netloc == urlparse(cos_config.public_base_url).netloc


COS_WEBP_FORMAT_RULE = "imageMogr2/format/webp"


def _append_ci_rule(image_url: str, rule: str) -> str:
    cleaned_rule = rule.strip().lstrip("?&")
    if not cleaned_rule or cleaned_rule in image_url:
        return image_url
    separator = "&" if "?" in image_url else "?"
    return f"{image_url}{separator}{cleaned_rule}"


def _normalize_style_name(rule: str) -> str:
    cleaned_rule = rule.strip()
    if not cleaned_rule:
        return ""
    if cleaned_rule.startswith("style/"):
        return cleaned_rule[len("style/"):].strip()
    if "/" in cleaned_rule:
        return ""
    return cleaned_rule


def _append_style_suffix(image_url: str, style_name: str) -> str:
    cleaned_style = style_name.strip()
    if not cleaned_style:
        return image_url

    parsed = urlparse(image_url)
    separator = (settings.COS_IMAGE_STYLE_SEPARATOR or "!").strip() or "!"
    if parsed.path.endswith(f"{separator}{cleaned_style}"):
        return image_url

    new_path = f"{parsed.path}{separator}{cleaned_style}"
    return urlunparse(parsed._replace(path=new_path))


def _build_cos_thumb_url(image_url: str, rule: str) -> str:
    style_name = _normalize_style_name(rule)
    if style_name:
        return _append_style_suffix(image_url, style_name)
    return _append_ci_rule(image_url, rule)


def build_webp_url(image_url: str | None) -> str:
    canonical_url = _normalize_url(image_url)
    if not canonical_url:
        return ""
    lowered = canonical_url.lower()
    if lowered.startswith("data:") or lowered.startswith("blob:"):
        return canonical_url
    return _append_ci_rule(canonical_url, COS_WEBP_FORMAT_RULE)


def build_thumb_url(
    image_url: str | None,
    *,
    preview_url: str | None = None,
    cos_config: CosRuntimeConfig | None = None,
) -> str:
    canonical_url = _normalize_url(image_url)
    fallback_preview = _normalize_url(preview_url)
    if not canonical_url:
        return fallback_preview
    if not _looks_like_cos_url(canonical_url, cos_config):
        return canonical_url
    return _build_cos_thumb_url(canonical_url, settings.COS_IMAGE_THUMBNAIL_RULE)


def serialize_asset_urls(
    image_url: str | None,
    *,
    cos_config: CosRuntimeConfig | None = None,
) -> dict[str, str]:
    canonical_url = normalize_external_image_url(image_url, cos_config=cos_config)
    return {
        "image_url": canonical_url,
        "thumb_url": build_thumb_url(canonical_url, cos_config=cos_config),
    }


def serialize_image(
    image: Image,
    *,
    cos_config: CosRuntimeConfig | None = None,
    public_error_message: bool = False,
) -> dict:
    image_url = _normalize_url(image.image_url)
    preview_url = _normalize_url(image.preview_url)
    exposed_preview_url = "" if image_url else preview_url
    return {
        "id": image.id,
        "image_url": image_url,
        "preview_url": exposed_preview_url,
        "thumb_url": build_thumb_url(image_url, preview_url=preview_url, cos_config=cos_config),
        "status": image.status,
        "error_message": (
            format_generation_public_error_message(image.error_message)
            if public_error_message
            else (image.error_message or "")
        ),
        "image_format": image.image_format or "",
        "image_size_bytes": int(image.image_size_bytes or 0),
        "is_deleted": bool(image.is_deleted),
    }


def _serialize_task_api_attempts(attempts: list[TaskApiAttempt] | None) -> list[dict]:
    if not attempts:
        return []
    serialized: list[dict] = []
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
            "created_at": attempt.created_at,
            "request_preview": None,
        })
    return serialized


def _parse_reference_images(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        refs = json.loads(raw)
        return refs if isinstance(refs, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def serialize_task(
    task: Task,
    *,
    cos_config: CosRuntimeConfig | None = None,
    credit_refunded: bool | None = None,
    failure_refund_remaining_count: int | None = None,
    include_provider_diagnostics: bool = False,
) -> dict:
    task_credit_cost = int(task.credit_cost or 0)
    resolved_credit_refunded = False
    if credit_refunded is not None:
        resolved_credit_refunded = bool(credit_refunded)
    elif task.status == "failed" and task_credit_cost > 0:
        db = Session.object_session(task)
        resolved_credit_refunded = bool(db and is_task_generation_failure_credit_refunded(db, task.id))
    source_asset = serialize_asset_urls(task.source_image or "", cos_config=cos_config)
    mask_asset = serialize_asset_urls(task.mask_image or "", cos_config=cos_config)
    reference_assets = [serialize_asset_urls(ref, cos_config=cos_config) for ref in _parse_reference_images(task.reference_images)]

    return {
        "id": task_external_id(task),
        "canvas_id": task.canvas_id,
        "mode": task.mode or "generate",
        "model": task.model or "",
        "source": (task.source or "web"),
        "prompt": task.prompt or "",
        "num_images": task.num_images,
        "size": task.size,
        "resolution": task.resolution or "",
        "custom_size": task.custom_size or "",
        "reference_images": [asset["image_url"] for asset in reference_assets],
        "reference_image_thumbs": [asset["thumb_url"] for asset in reference_assets],
        "source_image": source_asset["image_url"],
        "source_image_thumb": source_asset["thumb_url"],
        "mask_image": mask_asset["image_url"],
        "mask_image_thumb": mask_asset["thumb_url"],
        "credit_cost": task_credit_cost,
        "credit_refunded": resolved_credit_refunded,
        "failure_refund_remaining_count": failure_refund_remaining_count,
        "used_fallback_api": bool(task.used_fallback_api),
        "status": task.status,
        "error_message": (
            (task.error_message or "")
            if include_provider_diagnostics
            else format_generation_public_error_message(task.error_message)
        ),
        "provider_error_message": (task.provider_error_message or "") if include_provider_diagnostics else "",
        "created_at": task.created_at,
        "enqueued_at": task.enqueued_at,
        "request_started_at": task.request_started_at,
        "request_finished_at": task.request_finished_at,
        "images": [
            serialize_image(
                image,
                cos_config=cos_config,
                public_error_message=not include_provider_diagnostics,
            )
            for image in task.images
        ],
        "api_attempts": (
            _serialize_task_api_attempts(list(task.api_attempts or []))
            if include_provider_diagnostics
            else []
        ),
    }
