from __future__ import annotations

import json

import httpx
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.video_external_api_config import VideoExternalApiConfig
from app.models.video_external_api_scene_binding import VideoExternalApiSceneBinding
from app.models.video_task_api_attempt import VideoTaskApiAttempt
from app.schemas.video_external_api_config import (
    VideoExternalApiConfigCreate,
    VideoExternalApiConfigOut,
    VideoExternalApiConfigTestResult,
    VideoExternalApiConfigUpdate,
    VideoExternalApiSceneBindingCreate,
    VideoExternalApiSceneBindingMetaUpdate,
    VideoExternalApiSceneBindingOut,
    VideoExternalApiSceneBindingUpdate,
    VideoGenerationModelOptionOut,
    VideoTaskSceneConfigOut,
)
from app.services.external_api_config_service import (
    build_external_request_kwargs,
    build_secret_variables,
    parse_http_statuses_json,
    render_config,
)


DEFAULT_VIDEO_DURATION_OPTIONS = [
    {"label": "5 秒", "value": "5"},
    {"label": "10 秒", "value": "10"},
]
DEFAULT_VIDEO_ASPECT_RATIO_OPTIONS = [
    {"label": "16:9", "value": "16:9"},
    {"label": "9:16", "value": "9:16"},
    {"label": "1:1", "value": "1:1"},
]
DEFAULT_VIDEO_RESOLUTION_OPTIONS = [
    {"label": "540P", "value": "540p"},
    {"label": "720P", "value": "720p"},
    {"label": "1080P", "value": "1080p"},
]
DEFAULT_VIDEO_RESOLUTION_MAPPING: dict[str, str] = {}
DEFAULT_VIDEO_RESOLUTION_CREDIT_COSTS: dict[str, int] = {}
MAX_TEST_RESPONSE_PREVIEW_LENGTH = 2000
FIXED_VIDEO_CREDIT_BILLING_MODE = "fixed"
PER_SECOND_VIDEO_CREDIT_BILLING_MODE = "per_second"
VIDEO_SCENE_AVAILABILITY_TEXT = "text_to_video"
VIDEO_SCENE_AVAILABILITY_IMAGE = "image_to_video"
VIDEO_SCENE_AVAILABILITY_BOTH = "both"
VIDEO_SCENE_AVAILABILITY_FIRST_LAST = "first_last_frame"
VIDEO_SCENE_GENERATION_MODES = (
    VIDEO_SCENE_AVAILABILITY_TEXT,
    VIDEO_SCENE_AVAILABILITY_IMAGE,
    VIDEO_SCENE_AVAILABILITY_FIRST_LAST,
)


def _enforce_async_call_mode(config: VideoExternalApiConfig) -> VideoExternalApiConfig:
    if (config.call_mode or "").strip().lower() != "async":
        config.call_mode = "async"
    return config


def _normalize_scene_options(raw: str | None, fallback: list[dict[str, str]]) -> list[dict[str, str]]:
    candidate = (raw or "").strip()
    if not candidate:
        return [item.copy() for item in fallback]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return [item.copy() for item in fallback]
    if not isinstance(parsed, list):
        return [item.copy() for item in fallback]

    normalized: list[dict[str, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "") or "").strip()
        value = str(item.get("value", "") or "").strip()
        if not label or not value:
            continue
        normalized.append({"label": label, "value": value})
    return normalized or [item.copy() for item in fallback]


def _normalize_resolution_mapping(raw: str | None) -> dict[str, str]:
    candidate = (raw or "").strip() or "{}"
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return DEFAULT_VIDEO_RESOLUTION_MAPPING.copy()
    if not isinstance(parsed, dict):
        return DEFAULT_VIDEO_RESOLUTION_MAPPING.copy()
    normalized: dict[str, str] = {}
    for key, value in parsed.items():
        normalized_key = str(key or "").strip()
        normalized_value = str(value or "").strip()
        if normalized_key and normalized_value:
            normalized[normalized_key] = normalized_value
    return normalized


def _normalize_resolution_credit_costs(raw: str | None) -> dict[str, int]:
    candidate = (raw or "").strip() or "{}"
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return DEFAULT_VIDEO_RESOLUTION_CREDIT_COSTS.copy()
    if not isinstance(parsed, dict):
        return DEFAULT_VIDEO_RESOLUTION_CREDIT_COSTS.copy()
    normalized: dict[str, int] = {}
    for key, value in parsed.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        try:
            normalized[normalized_key] = max(int(value), 0)
        except (TypeError, ValueError):
            continue
    return normalized


def _normalize_credit_billing_mode(raw: str | None) -> str:
    normalized = (raw or "").strip().lower()
    if normalized == PER_SECOND_VIDEO_CREDIT_BILLING_MODE:
        return PER_SECOND_VIDEO_CREDIT_BILLING_MODE
    return FIXED_VIDEO_CREDIT_BILLING_MODE


def normalize_video_scene_availability_mode(raw: str | None) -> str:
    normalized = (raw or "").strip().lower()
    if normalized == VIDEO_SCENE_AVAILABILITY_TEXT:
        return VIDEO_SCENE_AVAILABILITY_TEXT
    if normalized == VIDEO_SCENE_AVAILABILITY_IMAGE:
        return VIDEO_SCENE_AVAILABILITY_IMAGE
    return VIDEO_SCENE_AVAILABILITY_BOTH


def normalize_video_generation_mode(raw: str | None, *, has_reference_images: bool = False) -> str:
    normalized = (raw or "").strip().lower()
    if normalized in VIDEO_SCENE_GENERATION_MODES:
        return normalized
    return VIDEO_SCENE_AVAILABILITY_IMAGE if has_reference_images else VIDEO_SCENE_AVAILABILITY_TEXT


def normalize_video_scene_availability_modes(raw: str | None, legacy_mode: str | None = None) -> list[str]:
    candidate = (raw or "").strip()
    parsed: object = None
    if candidate:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = None
    normalized: list[str] = []
    if isinstance(parsed, list):
        for item in parsed:
            mode = str(item or "").strip().lower()
            if mode in VIDEO_SCENE_GENERATION_MODES and mode not in normalized:
                normalized.append(mode)
    if normalized:
        return normalized

    legacy = normalize_video_scene_availability_mode(legacy_mode)
    if legacy == VIDEO_SCENE_AVAILABILITY_TEXT:
        return [VIDEO_SCENE_AVAILABILITY_TEXT]
    if legacy == VIDEO_SCENE_AVAILABILITY_IMAGE:
        return [VIDEO_SCENE_AVAILABILITY_IMAGE]
    return [VIDEO_SCENE_AVAILABILITY_TEXT, VIDEO_SCENE_AVAILABILITY_IMAGE]


def video_scene_availability_modes_json(modes: list[str] | tuple[str, ...] | None) -> str:
    normalized: list[str] = []
    for item in modes or []:
        mode = str(item or "").strip().lower()
        if mode in VIDEO_SCENE_GENERATION_MODES and mode not in normalized:
            normalized.append(mode)
    if not normalized:
        normalized = [VIDEO_SCENE_AVAILABILITY_TEXT, VIDEO_SCENE_AVAILABILITY_IMAGE]
    return json.dumps(normalized, ensure_ascii=False)


def legacy_availability_mode_from_modes(modes: list[str] | tuple[str, ...] | None) -> str:
    normalized = normalize_video_scene_availability_modes(video_scene_availability_modes_json(list(modes or [])))
    has_text = VIDEO_SCENE_AVAILABILITY_TEXT in normalized
    has_image = VIDEO_SCENE_AVAILABILITY_IMAGE in normalized
    if has_text and has_image:
        return VIDEO_SCENE_AVAILABILITY_BOTH
    if has_text:
        return VIDEO_SCENE_AVAILABILITY_TEXT
    return VIDEO_SCENE_AVAILABILITY_IMAGE


def is_video_scene_available_for_task_mode(
    availability_mode: str | None,
    *,
    has_reference_images: bool = False,
    generation_mode: str | None = None,
    availability_modes_json: str | None = None,
) -> bool:
    task_mode = normalize_video_generation_mode(generation_mode, has_reference_images=has_reference_images)
    return task_mode in normalize_video_scene_availability_modes(availability_modes_json, availability_mode)


def _serialize_scene_binding(
    binding: VideoExternalApiSceneBinding,
    primary_config: VideoExternalApiConfig | None,
    backup_config: VideoExternalApiConfig | None,
) -> VideoExternalApiSceneBindingOut:
    availability_modes = normalize_video_scene_availability_modes(
        binding.availability_modes_json,
        binding.availability_mode,
    )
    return VideoExternalApiSceneBindingOut(
        scene_key=binding.scene_key,
        scene_label=binding.scene_label,
        scene_description=binding.scene_description or "",
        display_name=binding.display_name or "",
        subtitle=binding.subtitle or "",
        sort_order=int(binding.sort_order or 0),
        hide_aspect_ratio=bool(binding.hide_aspect_ratio),
        hide_duration=bool(binding.hide_duration),
        hide_resolution=bool(binding.hide_resolution),
        availability_mode=normalize_video_scene_availability_mode(binding.availability_mode),
        availability_modes=availability_modes,
        max_reference_images=max(0, int(binding.max_reference_images or 0)),
        status=(binding.status or "enabled"),
        is_builtin=False,
        api_config_id=binding.api_config_id,
        api_config_name=primary_config.name if primary_config else "",
        api_group_name=primary_config.group_name if primary_config else "",
        api_status=(primary_config.status if primary_config else None),
        backup_api_config_id=binding.backup_api_config_id,
        backup_api_config_name=backup_config.name if backup_config else "",
        backup_api_group_name=backup_config.group_name if backup_config else "",
        backup_api_status=(backup_config.status if backup_config else None),
        credit_billing_mode=_normalize_credit_billing_mode(binding.credit_billing_mode),
        credit_cost=int(binding.credit_cost or 0),
        per_second_credit_cost=int(binding.per_second_credit_cost or 0),
        aspect_ratio_options_json=(binding.aspect_ratio_options_json or "[]"),
        duration_options_json=(binding.duration_options_json or "[]"),
        resolution_options_json=(binding.resolution_options_json or "[]"),
        resolution_mapping_json=(binding.resolution_mapping_json or "{}"),
        resolution_credit_costs_json=(binding.resolution_credit_costs_json or "{}"),
    )


def _require_config(db: Session, config_id: int) -> VideoExternalApiConfig:
    config = db.query(VideoExternalApiConfig).filter(VideoExternalApiConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="视频接口配置不存在")
    return config


def _require_scene_binding(db: Session, scene_key: str) -> VideoExternalApiSceneBinding:
    binding = (
        db.query(VideoExternalApiSceneBinding)
        .filter(
            VideoExternalApiSceneBinding.scene_key == (scene_key or "").strip().lower(),
            VideoExternalApiSceneBinding.is_deleted.is_(False),
        )
        .first()
    )
    if not binding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="视频场景不存在")
    return binding


def _validate_scene_binding_configs(
    db: Session,
    *,
    api_config_id: int | None,
    backup_api_config_id: int | None,
) -> tuple[VideoExternalApiConfig, VideoExternalApiConfig | None]:
    if not api_config_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="必须绑定主视频接口")
    primary_config = _require_config(db, api_config_id)
    backup_config = None
    if backup_api_config_id is not None:
        if backup_api_config_id == api_config_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="备用接口不能和主接口相同")
        backup_config = _require_config(db, backup_api_config_id)
    return primary_config, backup_config


def list_video_configs(db: Session) -> list[VideoExternalApiConfigOut]:
    return [
        VideoExternalApiConfigOut.model_validate(_enforce_async_call_mode(item))
        for item in db.query(VideoExternalApiConfig)
        .order_by(VideoExternalApiConfig.group_name.asc(), VideoExternalApiConfig.name.asc())
        .all()
    ]


def create_video_config(db: Session, body: VideoExternalApiConfigCreate) -> VideoExternalApiConfigOut:
    exists = db.query(VideoExternalApiConfig.id).filter(VideoExternalApiConfig.name == body.name).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="视频接口配置名称已存在")
    config = VideoExternalApiConfig(**body.model_dump())
    config.call_mode = "async"
    db.add(config)
    db.commit()
    db.refresh(config)
    return VideoExternalApiConfigOut.model_validate(_enforce_async_call_mode(config))


def update_video_config(db: Session, config_id: int, body: VideoExternalApiConfigUpdate) -> VideoExternalApiConfigOut:
    config = _require_config(db, config_id)
    duplicated = (
        db.query(VideoExternalApiConfig.id)
        .filter(VideoExternalApiConfig.name == body.name, VideoExternalApiConfig.id != config_id)
        .first()
    )
    if duplicated:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="视频接口配置名称已存在")
    for key, value in body.model_dump().items():
        setattr(config, key, value)
    config.call_mode = "async"
    db.add(config)
    db.commit()
    db.refresh(config)
    return VideoExternalApiConfigOut.model_validate(_enforce_async_call_mode(config))


def set_video_config_status(db: Session, config_id: int, status_value: str) -> VideoExternalApiConfigOut:
    config = _require_config(db, config_id)
    config.status = (status_value or "enabled").strip().lower()
    db.add(config)
    db.commit()
    db.refresh(config)
    return VideoExternalApiConfigOut.model_validate(_enforce_async_call_mode(config))


def delete_video_config(db: Session, config_id: int) -> None:
    config = _require_config(db, config_id)
    referenced = (
        db.query(VideoTaskApiAttempt.id)
        .filter(VideoTaskApiAttempt.api_config_id == config.id)
        .first()
    )
    if referenced:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该接口已被历史任务引用，无法删除。如需停用，请改为停用该接口。",
        )
    (
        db.query(VideoExternalApiSceneBinding)
        .filter(VideoExternalApiSceneBinding.api_config_id == config.id)
        .update({"api_config_id": None}, synchronize_session=False)
    )
    (
        db.query(VideoExternalApiSceneBinding)
        .filter(VideoExternalApiSceneBinding.backup_api_config_id == config.id)
        .update({"backup_api_config_id": None}, synchronize_session=False)
    )
    try:
        db.delete(config)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该接口已被历史任务引用，无法删除。如需停用，请改为停用该接口。",
        )


def list_video_scene_bindings(db: Session) -> list[VideoExternalApiSceneBindingOut]:
    configs = {item.id: item for item in db.query(VideoExternalApiConfig).all()}
    bindings = (
        db.query(VideoExternalApiSceneBinding)
        .filter(VideoExternalApiSceneBinding.is_deleted.is_(False))
        .order_by(VideoExternalApiSceneBinding.sort_order.asc(), VideoExternalApiSceneBinding.scene_key.asc())
        .all()
    )
    return [
        _serialize_scene_binding(
            binding,
            configs.get(binding.api_config_id),
            configs.get(binding.backup_api_config_id),
        )
        for binding in bindings
    ]


def create_video_scene_binding(db: Session, body: VideoExternalApiSceneBindingCreate) -> VideoExternalApiSceneBindingOut:
    exists = (
        db.query(VideoExternalApiSceneBinding.id)
        .filter(VideoExternalApiSceneBinding.scene_key == body.scene_key)
        .first()
    )
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="视频场景标识已存在")
    primary_config, backup_config = _validate_scene_binding_configs(
        db,
        api_config_id=body.api_config_id,
        backup_api_config_id=body.backup_api_config_id,
    )
    binding = VideoExternalApiSceneBinding(**body.model_dump(exclude={"availability_modes"}))
    binding.availability_modes_json = video_scene_availability_modes_json(body.availability_modes)
    binding.availability_mode = legacy_availability_mode_from_modes(body.availability_modes)
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return _serialize_scene_binding(binding, primary_config, backup_config)


def update_video_scene_binding(
    db: Session,
    scene_key: str,
    body: VideoExternalApiSceneBindingUpdate,
) -> VideoExternalApiSceneBindingOut:
    binding = _require_scene_binding(db, scene_key)
    primary_config, backup_config = _validate_scene_binding_configs(
        db,
        api_config_id=body.api_config_id,
        backup_api_config_id=body.backup_api_config_id,
    )
    binding.api_config_id = body.api_config_id
    binding.backup_api_config_id = body.backup_api_config_id
    binding.display_name = body.display_name
    binding.subtitle = body.subtitle
    binding.credit_billing_mode = _normalize_credit_billing_mode(body.credit_billing_mode)
    binding.credit_cost = body.credit_cost
    binding.per_second_credit_cost = body.per_second_credit_cost
    binding.status = body.status
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return _serialize_scene_binding(binding, primary_config, backup_config)


def update_video_scene_binding_meta(
    db: Session,
    scene_key: str,
    body: VideoExternalApiSceneBindingMetaUpdate,
) -> VideoExternalApiSceneBindingOut:
    binding = _require_scene_binding(db, scene_key)
    binding.scene_label = body.scene_label
    binding.scene_description = body.scene_description
    binding.sort_order = body.sort_order
    binding.hide_aspect_ratio = body.hide_aspect_ratio
    binding.hide_duration = body.hide_duration
    binding.hide_resolution = body.hide_resolution
    binding.availability_modes_json = video_scene_availability_modes_json(body.availability_modes)
    binding.availability_mode = legacy_availability_mode_from_modes(body.availability_modes)
    binding.max_reference_images = max(0, int(body.max_reference_images or 0))
    binding.credit_billing_mode = _normalize_credit_billing_mode(body.credit_billing_mode)
    binding.credit_cost = body.credit_cost
    binding.per_second_credit_cost = body.per_second_credit_cost
    binding.aspect_ratio_options_json = body.aspect_ratio_options_json
    binding.duration_options_json = body.duration_options_json
    binding.resolution_options_json = body.resolution_options_json
    binding.resolution_mapping_json = body.resolution_mapping_json
    binding.resolution_credit_costs_json = body.resolution_credit_costs_json
    db.add(binding)
    db.commit()
    db.refresh(binding)
    primary_config = _require_config(db, binding.api_config_id) if binding.api_config_id else None
    backup_config = _require_config(db, binding.backup_api_config_id) if binding.backup_api_config_id else None
    return _serialize_scene_binding(binding, primary_config, backup_config)


def set_video_scene_binding_status(
    db: Session,
    scene_key: str,
    status_value: str,
) -> VideoExternalApiSceneBindingOut:
    binding = _require_scene_binding(db, scene_key)
    binding.status = (status_value or "enabled").strip().lower()
    db.add(binding)
    db.commit()
    db.refresh(binding)
    primary_config = _require_config(db, binding.api_config_id) if binding.api_config_id else None
    backup_config = _require_config(db, binding.backup_api_config_id) if binding.backup_api_config_id else None
    return _serialize_scene_binding(binding, primary_config, backup_config)


def delete_video_scene_binding(db: Session, scene_key: str) -> None:
    binding = _require_scene_binding(db, scene_key)
    binding.is_deleted = True
    db.add(binding)
    db.commit()


def list_public_video_task_scene_configs(db: Session) -> list[VideoTaskSceneConfigOut]:
    bindings = (
        db.query(VideoExternalApiSceneBinding)
        .filter(
            VideoExternalApiSceneBinding.is_deleted.is_(False),
            VideoExternalApiSceneBinding.status == "enabled",
        )
        .order_by(VideoExternalApiSceneBinding.sort_order.asc(), VideoExternalApiSceneBinding.scene_key.asc())
        .all()
    )
    return [
        VideoTaskSceneConfigOut(
            scene_key=item.scene_key,
            scene_label=item.scene_label,
            scene_description=item.scene_description or "",
            display_name=item.display_name or item.scene_label,
            subtitle=item.subtitle or "",
            sort_order=int(item.sort_order or 0),
            hide_aspect_ratio=bool(item.hide_aspect_ratio),
            hide_duration=bool(item.hide_duration),
            hide_resolution=bool(item.hide_resolution),
            availability_mode=normalize_video_scene_availability_mode(item.availability_mode),
            availability_modes=normalize_video_scene_availability_modes(item.availability_modes_json, item.availability_mode),
            max_reference_images=max(0, int(item.max_reference_images or 0)),
            credit_billing_mode=_normalize_credit_billing_mode(item.credit_billing_mode),
            credit_cost=int(item.credit_cost or 0),
            per_second_credit_cost=int(item.per_second_credit_cost or 0),
            aspect_ratio_options=_normalize_scene_options(item.aspect_ratio_options_json, DEFAULT_VIDEO_ASPECT_RATIO_OPTIONS),
            resolution_credit_costs=_normalize_resolution_credit_costs(item.resolution_credit_costs_json),
            duration_options=_normalize_scene_options(item.duration_options_json, DEFAULT_VIDEO_DURATION_OPTIONS),
            resolution_options=_normalize_scene_options(item.resolution_options_json, DEFAULT_VIDEO_RESOLUTION_OPTIONS),
        )
        for item in bindings
    ]


def list_video_generation_models(db: Session) -> list[VideoGenerationModelOptionOut]:
    return [
        VideoGenerationModelOptionOut(
            model_key=item.scene_key,
            model_label=item.scene_label,
            model_description=item.scene_description or "",
            display_name=item.display_name,
            subtitle=item.subtitle or "",
            sort_order=item.sort_order,
            hide_aspect_ratio=bool(item.hide_aspect_ratio),
            hide_duration=bool(item.hide_duration),
            hide_resolution=bool(item.hide_resolution),
            availability_mode=normalize_video_scene_availability_mode(item.availability_mode),
            availability_modes=item.availability_modes,
            max_reference_images=max(0, int(item.max_reference_images or 0)),
            credit_billing_mode=_normalize_credit_billing_mode(item.credit_billing_mode),
            credit_cost=int(item.credit_cost or 0),
            per_second_credit_cost=int(item.per_second_credit_cost or 0),
            aspect_ratio_options=_normalize_scene_options(item.aspect_ratio_options_json, DEFAULT_VIDEO_ASPECT_RATIO_OPTIONS),
            resolution_credit_costs=_normalize_resolution_credit_costs(item.resolution_credit_costs_json),
            duration_options=_normalize_scene_options(item.duration_options_json, DEFAULT_VIDEO_DURATION_OPTIONS),
            resolution_options=_normalize_scene_options(item.resolution_options_json, DEFAULT_VIDEO_RESOLUTION_OPTIONS),
        )
        for item in list_public_video_task_scene_configs(db)
    ]


def resolve_video_scene_generation_configs(
    db: Session,
    scene_key: str,
) -> tuple[VideoExternalApiConfig, VideoExternalApiConfig | None]:
    binding = _require_scene_binding(db, scene_key)
    if (binding.status or "").strip().lower() != "enabled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="视频场景已禁用")
    primary_config = _require_config(db, binding.api_config_id) if binding.api_config_id else None
    if not primary_config or (primary_config.status or "").strip().lower() != "enabled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="视频主接口未配置或已禁用")
    backup_config = None
    if binding.backup_api_config_id:
        backup_candidate = _require_config(db, binding.backup_api_config_id)
        if (backup_candidate.status or "").strip().lower() == "enabled":
            backup_config = backup_candidate
    return primary_config, backup_config


def require_video_scene_config(db: Session, scene_key: str) -> VideoExternalApiConfig:
    primary_config, _backup_config = resolve_video_scene_generation_configs(db, scene_key)
    return primary_config


def get_video_scene_credit_cost(db: Session, scene_key: str, *, resolution: str = "", duration_seconds: int = 0) -> int:
    binding = _require_scene_binding(db, scene_key)
    billing_mode = _normalize_credit_billing_mode(binding.credit_billing_mode)
    if billing_mode == PER_SECOND_VIDEO_CREDIT_BILLING_MODE:
        normalized_duration = max(int(duration_seconds or 0), 0)
        return normalized_duration * max(int(binding.per_second_credit_cost or 0), 0)
    resolution_key = (resolution or "").strip()
    resolution_costs = _normalize_resolution_credit_costs(binding.resolution_credit_costs_json)
    if resolution_key and resolution_key in resolution_costs:
        return int(resolution_costs[resolution_key])
    return int(binding.credit_cost or 0)


def get_video_scene_max_reference_images(db: Session, scene_key: str) -> int:
    binding = _require_scene_binding(db, scene_key)
    return max(0, int(binding.max_reference_images or 0))


def resolve_mapped_video_resolution(db: Session, scene_key: str, resolution: str) -> str:
    binding = _require_scene_binding(db, scene_key)
    resolution_key = (resolution or "").strip()
    mapping = _normalize_resolution_mapping(binding.resolution_mapping_json)
    return mapping.get(resolution_key, resolution_key)


def test_video_external_api_config(
    db: Session,
    body: VideoExternalApiConfigCreate,
) -> VideoExternalApiConfigTestResult:
    config = VideoExternalApiConfig(**body.model_dump())
    config.call_mode = "async"
    variables = {
        **build_secret_variables(db),
        "prompt": "连接测试",
        "duration_seconds": 5,
        "resolution": "720p",
        "mapped_resolution": "720p",
        "task_id": "test-task-id",
        "provider_task_id": "test-task-id",
    }
    rendered = render_config(config, variables)
    request_kwargs = build_external_request_kwargs(rendered)
    method = "POST"
    with httpx.Client(timeout=15, trust_env=False) as client:
        response = client.request(method, rendered.request_url, **request_kwargs)
    preview = (response.text or "")[:MAX_TEST_RESPONSE_PREVIEW_LENGTH]
    success_statuses = parse_http_statuses_json(config.submit_success_statuses_json) or [200, 201, 202]
    return VideoExternalApiConfigTestResult(
        success=response.status_code in success_statuses or 200 <= response.status_code < 300,
        request_url=rendered.request_url,
        status_code=response.status_code,
        response_preview=preview or "(空响应)",
    )
