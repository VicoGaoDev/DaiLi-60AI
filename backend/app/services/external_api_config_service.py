import base64
import json
import re
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.api_key import ApiKey
from app.models.external_api_config import ExternalApiConfig
from app.models.external_api_scene_binding import ExternalApiSceneBinding
from app.models.task_api_attempt import TaskApiAttempt
from app.schemas.external_api_config import (
    ExternalApiConfigCreate,
    ExternalApiConfigOut,
    ExternalApiConfigTestResult,
    ExternalApiSceneBindingCreate,
    ExternalApiSceneBindingMetaUpdate,
    ExternalApiConfigUpdate,
    ExternalApiSceneBindingOut,
    ExternalApiSceneBindingStatusUpdate,
    ExternalApiSceneBindingUpdate,
    GenerationModelOptionOut,
    RenderedExternalApiConfig,
    RenderedPollExternalApiConfig,
    TaskSceneConfigOut,
)
from app.services.cos_service import load_image_bytes
from app.services.generation_scene_category_service import build_scene_category_map

SCENE_BANANA = "banana"
SCENE_BANANA2 = "banana2"
SCENE_BANANA_PRO = "banana_pro"
SCENE_BANANA_PRO_PLUS = "banana_pro_plus"
SCENE_BANANA_EDIT = "banana_edit"
SCENE_BANANA2_EDIT = "banana2_edit"
SCENE_BANANA_PRO_EDIT = "banana_pro_edit"
SCENE_BANANA_PRO_PLUS_EDIT = "banana_pro_plus_edit"
SCENE_PROMPT_REVERSE = "prompt_reverse"
SCENE_PROMPT_OPTIMIZE = "prompt_optimize"
SCENE_INPAINT = "inpaint"
SCENE_SMART_CUTOUT = "smart_cutout"
SCENE_TYPE_GENERATE = "generate"
SCENE_TYPE_IMAGE_EDIT = "image_edit"
SCENE_TYPE_PROMPT_REVERSE = "prompt_reverse"
SCENE_TYPE_PROMPT_OPTIMIZE = "prompt_optimize"
SCENE_TYPE_INPAINT = "inpaint"
SCENE_TYPE_SMART_CUTOUT = "smart_cutout"
DEFAULT_GENERATION_SCENE = SCENE_BANANA_PRO
PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
_MISSING_PLACEHOLDER = object()
SMART_CUTOUT_PLACEHOLDER_PROMPT = "智能抠图"
SMART_CUTOUT_FULL_IMAGE_PROMPT = "将这张图的主体抠出，去除背景，输出干净的主体图。"
SMART_CUTOUT_MASK_PROMPT = "请基于第1张原图和第2张蒙版进行抠图：白色区域是需要抠出的主体，黑色区域作为背景去掉。"


def _is_known_broken_smart_cutout_prompt(value: str) -> bool:
    return (value or "").strip() == "{标记区域抠图"


def normalize_smart_cutout_user_prompt(prompt: str) -> str:
    text = (prompt or "").strip()
    if not text or text == SMART_CUTOUT_PLACEHOLDER_PROMPT or _is_known_broken_smart_cutout_prompt(text):
        return ""
    return text


def resolve_smart_cutout_prompt(prompt: str, reference_count: int) -> str:
    custom_prompt = normalize_smart_cutout_user_prompt(prompt)
    if custom_prompt:
        return custom_prompt
    if int(reference_count or 0) >= 2:
        return SMART_CUTOUT_MASK_PROMPT
    return SMART_CUTOUT_FULL_IMAGE_PROMPT


def _fix_rendered_payload_prompt(payload: Any, variables: dict[str, Any]) -> Any:
    if str(variables.get("mode") or "").strip() != SCENE_TYPE_SMART_CUTOUT:
        return payload
    if not isinstance(payload, dict):
        return payload
    current = payload.get("prompt")
    if not isinstance(current, str) or not _is_known_broken_smart_cutout_prompt(current):
        return payload
    fallback = str(variables.get("prompt") or "").strip()
    if _is_known_broken_smart_cutout_prompt(fallback):
        fallback = ""
    next_payload = dict(payload)
    next_payload["prompt"] = fallback or resolve_smart_cutout_prompt("", int(variables.get("reference_image_count") or 0))
    return next_payload
MULTIPART_EDIT_FILE_FIELD_ALIASES = {
    "image": "image",
    "image[]": "image[]",
    "images": "image",
    "images[]": "image[]",
    "mask": "mask",
}
MULTIPART_EDIT_FILE_FIELDS = set(MULTIPART_EDIT_FILE_FIELD_ALIASES)
IMAGE_MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
DEFAULT_SCENE_DEFINITIONS = [
    {"scene_key": SCENE_BANANA, "scene_type": SCENE_TYPE_GENERATE, "scene_label": "Banana", "scene_description": "推荐模型", "sort_order": 10, "hide_aspect_ratio": False, "hide_resolution": True, "hide_custom_size": True},
    {"scene_key": SCENE_BANANA2, "scene_type": SCENE_TYPE_GENERATE, "scene_label": "Banana 2", "scene_description": "尝鲜版", "sort_order": 20, "hide_aspect_ratio": False, "hide_resolution": False, "hide_custom_size": True},
    {"scene_key": SCENE_BANANA_PRO, "scene_type": SCENE_TYPE_GENERATE, "scene_label": "Banana Pro", "scene_description": "增强版", "sort_order": 30, "hide_aspect_ratio": False, "hide_resolution": False, "hide_custom_size": True},
    {"scene_key": SCENE_BANANA_PRO_PLUS, "scene_type": SCENE_TYPE_GENERATE, "scene_label": "Banana Pro+", "scene_description": "增强稳定版", "sort_order": 40, "hide_aspect_ratio": False, "hide_resolution": False, "hide_custom_size": True},
    {"scene_key": SCENE_BANANA_EDIT, "scene_type": SCENE_TYPE_IMAGE_EDIT, "scene_label": "Banana", "scene_description": "推荐模型", "sort_order": 110, "hide_aspect_ratio": False, "hide_resolution": True, "hide_custom_size": True},
    {"scene_key": SCENE_BANANA2_EDIT, "scene_type": SCENE_TYPE_IMAGE_EDIT, "scene_label": "Banana 2", "scene_description": "尝鲜版", "sort_order": 120, "hide_aspect_ratio": False, "hide_resolution": False, "hide_custom_size": True},
    {"scene_key": SCENE_BANANA_PRO_EDIT, "scene_type": SCENE_TYPE_IMAGE_EDIT, "scene_label": "Banana Pro", "scene_description": "增强版", "sort_order": 130, "hide_aspect_ratio": False, "hide_resolution": False, "hide_custom_size": True},
    {"scene_key": SCENE_BANANA_PRO_PLUS_EDIT, "scene_type": SCENE_TYPE_IMAGE_EDIT, "scene_label": "Banana Pro+", "scene_description": "增强稳定版", "sort_order": 140, "hide_aspect_ratio": False, "hide_resolution": False, "hide_custom_size": True},
    {"scene_key": SCENE_PROMPT_REVERSE, "scene_type": SCENE_TYPE_PROMPT_REVERSE, "scene_label": "提示词反推", "scene_description": "图片反推提示词", "sort_order": 50, "hide_aspect_ratio": True, "hide_resolution": True, "hide_custom_size": True},
    {"scene_key": SCENE_PROMPT_OPTIMIZE, "scene_type": SCENE_TYPE_PROMPT_OPTIMIZE, "scene_label": "提示词优化", "scene_description": "优化当前提示词", "sort_order": 55, "hide_aspect_ratio": True, "hide_resolution": True, "hide_custom_size": True},
    {"scene_key": SCENE_INPAINT, "scene_type": SCENE_TYPE_INPAINT, "scene_label": "局部重绘", "scene_description": "图编辑/局部重绘", "sort_order": 60, "hide_aspect_ratio": True, "hide_resolution": True, "hide_custom_size": True},
    {"scene_key": SCENE_SMART_CUTOUT, "scene_type": SCENE_TYPE_SMART_CUTOUT, "scene_label": "智能抠图", "scene_description": "涂抹区域后自动抠图", "sort_order": 65, "hide_aspect_ratio": False, "hide_resolution": False, "hide_custom_size": False},
]
SCENE_DEFAULT_CREDIT_COSTS = {
    SCENE_BANANA: 4,
    SCENE_BANANA2: 4,
    SCENE_BANANA_PRO: 4,
    SCENE_BANANA_PRO_PLUS: 4,
    SCENE_BANANA_EDIT: 4,
    SCENE_BANANA2_EDIT: 4,
    SCENE_BANANA_PRO_EDIT: 4,
    SCENE_BANANA_PRO_PLUS_EDIT: 4,
    SCENE_PROMPT_REVERSE: 1,
    SCENE_PROMPT_OPTIMIZE: 1,
    SCENE_INPAINT: 4,
    SCENE_SMART_CUTOUT: 4,
}
IMAGE_EDIT_SCENE_SOURCE_MAP = {
    SCENE_BANANA_EDIT: SCENE_BANANA,
    SCENE_BANANA2_EDIT: SCENE_BANANA2,
    SCENE_BANANA_PRO_EDIT: SCENE_BANANA_PRO,
    SCENE_BANANA_PRO_PLUS_EDIT: SCENE_BANANA_PRO_PLUS,
}
DEFAULT_SCENE_MAP = {item["scene_key"]: item for item in DEFAULT_SCENE_DEFINITIONS}
NON_EDITABLE_SCENE_KEYS = {SCENE_PROMPT_REVERSE, SCENE_PROMPT_OPTIMIZE, SCENE_INPAINT}
DEFAULT_SMART_CUTOUT_MAX_REFERENCE_IMAGES = 2
DEFAULT_ASPECT_RATIO_OPTIONS = [
    {"label": "■  1:1", "value": "1:1"},
    {"label": "▮  2:3", "value": "2:3"},
    {"label": "▬  3:2", "value": "3:2"},
    {"label": "▮  3:4", "value": "3:4"},
    {"label": "▬  4:3", "value": "4:3"},
    {"label": "▮  9:16", "value": "9:16"},
    {"label": "▬  16:9", "value": "16:9"},
]
DEFAULT_IMAGE_SIZE_OPTIONS = [
    {"label": "1K", "value": "1K"},
    {"label": "2K", "value": "2K"},
    {"label": "4K", "value": "4K"},
]
DEFAULT_CUSTOM_SIZE_OPTIONS = [
    {"label": "1024 x 1024", "value": "1024x1024"},
    {"label": "1152 x 896", "value": "1152x896"},
    {"label": "896 x 1152", "value": "896x1152"},
    {"label": "1280 x 720", "value": "1280x720"},
]
DEFAULT_RESOLUTION_MAPPING: dict[str, dict[str, str]] = {}
DEFAULT_RESOLUTION_CREDIT_COSTS: dict[str, int] = {}
DEFAULT_IMAGE_EDIT_MAX_REFERENCE_IMAGES = 6


def is_builtin_scene(scene_key: str) -> bool:
    return scene_key in NON_EDITABLE_SCENE_KEYS


def _get_default_scene_options(scene_type: str) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    if scene_type in {SCENE_TYPE_GENERATE, SCENE_TYPE_IMAGE_EDIT, SCENE_TYPE_SMART_CUTOUT}:
        return DEFAULT_ASPECT_RATIO_OPTIONS, DEFAULT_IMAGE_SIZE_OPTIONS, DEFAULT_CUSTOM_SIZE_OPTIONS
    return [], [], []


def get_default_max_reference_images(scene_type: str) -> int:
    if scene_type == SCENE_TYPE_IMAGE_EDIT:
        return DEFAULT_IMAGE_EDIT_MAX_REFERENCE_IMAGES
    if scene_type == SCENE_TYPE_SMART_CUTOUT:
        return DEFAULT_SMART_CUTOUT_MAX_REFERENCE_IMAGES
    return 0


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


def _dump_scene_options(items: list[dict[str, str]]) -> str:
    return json.dumps(items, ensure_ascii=False, indent=2)


def _normalize_resolution_mapping(raw: str | None) -> dict[str, dict[str, str]]:
    candidate = (raw or "").strip()
    if not candidate:
        return DEFAULT_RESOLUTION_MAPPING.copy()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return DEFAULT_RESOLUTION_MAPPING.copy()

    if not isinstance(parsed, dict):
        return DEFAULT_RESOLUTION_MAPPING.copy()

    normalized: dict[str, dict[str, str]] = {}
    for aspect_ratio, resolution_map in parsed.items():
        aspect_key = str(aspect_ratio or "").strip()
        if not aspect_key or not isinstance(resolution_map, dict):
            continue
        normalized_resolution_map: dict[str, str] = {}
        for image_size, mapped_resolution in resolution_map.items():
            image_size_key = str(image_size or "").strip()
            mapped_value = str(mapped_resolution or "").strip()
            if image_size_key and mapped_value:
                normalized_resolution_map[image_size_key] = mapped_value
        normalized[aspect_key] = normalized_resolution_map
    return normalized


def _dump_resolution_mapping(items: dict[str, dict[str, str]]) -> str:
    return json.dumps(items, ensure_ascii=False, indent=2)


def _get_resolution_mapping_json(raw: str | None) -> str:
    return _dump_resolution_mapping(_normalize_resolution_mapping(raw))


def _normalize_resolution_credit_costs(raw: str | None) -> dict[str, int]:
    candidate = (raw or "").strip()
    if not candidate:
        return DEFAULT_RESOLUTION_CREDIT_COSTS.copy()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return DEFAULT_RESOLUTION_CREDIT_COSTS.copy()

    if not isinstance(parsed, dict):
        return DEFAULT_RESOLUTION_CREDIT_COSTS.copy()

    normalized: dict[str, int] = {}
    for resolution, credit_cost in parsed.items():
        resolution_key = str(resolution or "").strip()
        if not resolution_key or isinstance(credit_cost, bool):
            continue
        try:
            normalized_cost = int(credit_cost)
        except (TypeError, ValueError):
            continue
        if normalized_cost >= 0:
            normalized[resolution_key] = normalized_cost
    return normalized


def _dump_resolution_credit_costs(items: dict[str, int]) -> str:
    return json.dumps(items, ensure_ascii=False, indent=2)


def _get_resolution_credit_costs_json(raw: str | None) -> str:
    return _dump_resolution_credit_costs(_normalize_resolution_credit_costs(raw))


def resolve_mapped_resolution(
    db: Session,
    scene_key: str,
    aspect_ratio: str,
    image_size: str,
) -> str:
    _ensure_scene_bindings(db)
    binding = (
        db.query(ExternalApiSceneBinding)
        .filter(
            ExternalApiSceneBinding.scene_key == scene_key,
            ExternalApiSceneBinding.is_deleted.is_(False),
        )
        .first()
    )
    if not binding:
        return ""
    mapping = _normalize_resolution_mapping(binding.resolution_mapping_json)
    aspect_key = (aspect_ratio or "").strip()
    image_size_key = (image_size or "").strip()
    return (mapping.get(aspect_key, {}).get(image_size_key) or "").strip()


def _get_scene_option_json(
    scene_type: str,
    aspect_ratio_options_json: str | None,
    image_size_options_json: str | None,
    custom_size_options_json: str | None,
) -> tuple[str, str, str]:
    default_aspect_ratio_options, default_image_size_options, default_custom_size_options = _get_default_scene_options(scene_type)
    return (
        _dump_scene_options(_normalize_scene_options(aspect_ratio_options_json, default_aspect_ratio_options)),
        _dump_scene_options(_normalize_scene_options(image_size_options_json, default_image_size_options)),
        _dump_scene_options(_normalize_scene_options(custom_size_options_json, default_custom_size_options)),
    )


def _load_json(raw: str, field_name: str) -> Any:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} 不是合法 JSON: {exc.msg}",
        ) from exc


def _dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _default_generation_headers(api_key: str) -> str:
    return _dump_json({
        "Content-Type": "application/json",
        "Authorization": api_key,
    })


def _default_generation_payload() -> str:
    return _dump_json({
        "contents": [
            {
                "role": "user",
                "parts": "{{contents_parts}}",
            }
        ],
        "generationConfig": "{{generation_config}}",
    })


def _default_generation_response() -> str:
    return _dump_json({
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": "<base64>",
                            }
                        }
                    ]
                }
            }
        ]
    })


def _default_prompt_reverse_headers(api_key: str) -> str:
    return _dump_json({
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })


def _default_prompt_reverse_payload() -> str:
    return _dump_json({
        "model": "qwen-vl-plus",
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"image": "{{image_data_url}}"},
                        {"text": "{{prompt_reverse_text}}"},
                    ],
                }
            ],
        },
        "parameters": {
            "temperature": 0.1,
            "max_tokens": 1024,
        },
    })


def _default_prompt_optimize_payload() -> str:
    return _dump_json({
        "model": "qwen-vl-plus",
        "input": {
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {"text": "{{prompt_optimize_text}}\n{{prompt_optimize_style_prompt}}"},
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"text": "原始提示词：{{prompt}}"},
                        {"image": "{{reference_image_1_data_url}}"},
                        {"image": "{{reference_image_2_data_url}}"},
                        {"image": "{{reference_image_3_data_url}}"},
                    ],
                },
            ],
        },
        "parameters": {
            "temperature": 0.3,
            "max_tokens": 1024,
        },
    })


def _normalize_headers(data: Any) -> dict[str, str]:
    if not isinstance(data, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Header JSON 必须是对象")
    return {str(key): "" if value is None else str(value) for key, value in data.items()}


def _render_string(template: str, variables: dict[str, Any]) -> Any:
    exact_match = PLACEHOLDER_RE.fullmatch(template)
    if exact_match:
        return variables.get(exact_match.group(1), _MISSING_PLACEHOLDER)

    names = PLACEHOLDER_RE.findall(template)
    if names and any(name not in variables for name in names):
        return _MISSING_PLACEHOLDER

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        value = variables.get(name, "")
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        if value is None:
            return ""
        return str(value)

    return PLACEHOLDER_RE.sub(replace, template)


def _render_json_template(
    template: Any,
    variables: dict[str, Any],
    *,
    prune_partial_objects: bool = False,
) -> Any:
    if isinstance(template, dict):
        rendered: dict[str, Any] = {}
        missing_count = 0
        for key, value in template.items():
            next_value = _render_json_template(
                value,
                variables,
                prune_partial_objects=prune_partial_objects,
            )
            if next_value is _MISSING_PLACEHOLDER:
                missing_count += 1
                continue
            if (
                prune_partial_objects
                and isinstance(value, list)
                and value
                and isinstance(next_value, list)
                and not next_value
            ):
                missing_count += 1
                continue
            rendered[key] = next_value
        if missing_count and (prune_partial_objects or not rendered):
            return _MISSING_PLACEHOLDER
        if not rendered and template:
            return _MISSING_PLACEHOLDER
        return rendered
    if isinstance(template, list):
        rendered_items: list[Any] = []
        for item in template:
            next_item = _render_json_template(
                item,
                variables,
                prune_partial_objects=isinstance(item, dict),
            )
            if next_item is _MISSING_PLACEHOLDER:
                continue
            rendered_items.append(next_item)
        return rendered_items
    if isinstance(template, str):
        return _render_string(template, variables)
    return template


def _serialize_config(config: ExternalApiConfig) -> ExternalApiConfigOut:
    return ExternalApiConfigOut(
        id=int(config.id),
        name=(config.name or "").strip(),
        description=(config.description or "").strip(),
        group_name=(config.group_name or "").strip() or "默认",
        request_url=(config.request_url or "").strip(),
        request_format=((config.request_format or "json").strip().lower() or "json"),
        headers_json=(config.headers_json or "{}"),
        payload_json=(config.payload_json or "{}"),
        response_json=(config.response_json or "{}"),
        result_base64_field=(config.result_base64_field or "").strip(),
        call_mode=((config.call_mode or "sync").strip().lower() or "sync"),
        submit_success_statuses_json=(config.submit_success_statuses_json or "[200, 201, 202]"),
        poll_url=(config.poll_url or "").strip(),
        poll_method=((config.poll_method or "GET").strip().upper() or "GET"),
        poll_headers_json=(config.poll_headers_json or "{}"),
        poll_payload_json=(config.poll_payload_json or "{}"),
        task_id_field=(config.task_id_field or "").strip(),
        result_status_field=(config.result_status_field or "").strip(),
        result_success_values_json=(config.result_success_values_json or '["success", "succeeded", "completed"]'),
        result_failed_values_json=(config.result_failed_values_json or '["failed", "error", "cancelled"]'),
        result_error_field=(config.result_error_field or "").strip(),
        poll_result_base64_field=(config.poll_result_base64_field or "").strip(),
        poll_result_url_field=(config.poll_result_url_field or "").strip(),
        poll_interval_seconds=max(int(config.poll_interval_seconds or 5), 1),
        poll_timeout_seconds=max(int(config.poll_timeout_seconds or 600), 1),
        status=((config.status or "enabled").strip().lower() or "enabled"),
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def get_default_credit_cost(scene_key: str, scene_type: str | None = None) -> int:
    if scene_key in SCENE_DEFAULT_CREDIT_COSTS:
        return SCENE_DEFAULT_CREDIT_COSTS[scene_key]
    if scene_type == SCENE_TYPE_PROMPT_REVERSE:
        return SCENE_DEFAULT_CREDIT_COSTS[SCENE_PROMPT_REVERSE]
    if scene_type == SCENE_TYPE_PROMPT_OPTIMIZE:
        return SCENE_DEFAULT_CREDIT_COSTS[SCENE_PROMPT_OPTIMIZE]
    if scene_type == SCENE_TYPE_INPAINT:
        return SCENE_DEFAULT_CREDIT_COSTS[SCENE_INPAINT]
    if scene_type == SCENE_TYPE_SMART_CUTOUT:
        return SCENE_DEFAULT_CREDIT_COSTS[SCENE_SMART_CUTOUT]
    return SCENE_DEFAULT_CREDIT_COSTS[SCENE_BANANA_PRO]


def _resolve_scene_copy(binding: ExternalApiSceneBinding) -> tuple[str, str]:
    display_name = (binding.display_name or "").strip()
    subtitle = (binding.subtitle or "").strip()
    return (
        display_name or (binding.scene_label or "").strip(),
        subtitle or (binding.scene_description or "").strip(),
    )


def _serialize_scene_binding(
    binding: ExternalApiSceneBinding,
    config: ExternalApiConfig | None,
    backup_config: ExternalApiConfig | None = None,
) -> ExternalApiSceneBindingOut:
    scene_label, scene_description = _resolve_scene_copy(binding)
    aspect_ratio_options_json, image_size_options_json, custom_size_options_json = _get_scene_option_json(
        binding.scene_type,
        binding.aspect_ratio_options_json,
        binding.image_size_options_json,
        binding.custom_size_options_json,
    )
    return ExternalApiSceneBindingOut(
        scene_key=binding.scene_key,
        scene_type=binding.scene_type,
        scene_label=scene_label,
        scene_description=scene_description,
        display_name=(binding.display_name or "").strip(),
        subtitle=(binding.subtitle or "").strip(),
        sort_order=binding.sort_order,
        hide_aspect_ratio=bool(binding.hide_aspect_ratio),
        hide_resolution=binding.hide_resolution,
        hide_custom_size=bool(binding.hide_custom_size),
        custom_size_min=max(1, int(binding.custom_size_min or 256)),
        custom_size_max=max(1, int(binding.custom_size_max or 4096)),
        custom_size_step=max(1, int(binding.custom_size_step or 8)),
        status=(binding.status or "enabled").strip().lower(),
        is_builtin=is_builtin_scene(binding.scene_key),
        api_config_id=config.id if config else None,
        api_config_name=config.name if config else "",
        api_group_name=config.group_name if config else "",
        api_status=config.status if config else None,
        backup_api_config_id=backup_config.id if backup_config else None,
        backup_api_config_name=backup_config.name if backup_config else "",
        backup_api_group_name=backup_config.group_name if backup_config else "",
        backup_api_status=backup_config.status if backup_config else None,
        credit_cost=binding.credit_cost,
        max_reference_images=max(0, int(binding.max_reference_images or 0)),
        aspect_ratio_options_json=aspect_ratio_options_json,
        image_size_options_json=image_size_options_json,
        custom_size_options_json=custom_size_options_json,
        resolution_mapping_json=_get_resolution_mapping_json(binding.resolution_mapping_json),
        resolution_credit_costs_json=_get_resolution_credit_costs_json(binding.resolution_credit_costs_json),
    )


def list_configs(db: Session) -> list[ExternalApiConfigOut]:
    rows = (
        db.query(ExternalApiConfig)
        .order_by(ExternalApiConfig.group_name.asc(), ExternalApiConfig.created_at.desc(), ExternalApiConfig.id.desc())
        .all()
    )
    return [_serialize_config(row) for row in rows]


def list_generation_models(db: Session) -> list[GenerationModelOptionOut]:
    _ensure_scene_bindings(db)
    scene_bindings = (
        db.query(ExternalApiSceneBinding)
        .filter(
            ExternalApiSceneBinding.is_deleted.is_(False),
            ExternalApiSceneBinding.scene_type == SCENE_TYPE_GENERATE,
            ExternalApiSceneBinding.status == "enabled",
        )
        .order_by(ExternalApiSceneBinding.sort_order.asc(), ExternalApiSceneBinding.id.asc())
        .all()
    )
    category_map = build_scene_category_map(db)
    items: list[GenerationModelOptionOut] = []
    for binding in scene_bindings:
        model_label, model_description = _resolve_scene_copy(binding)
        category = category_map.get(binding.scene_key)
        items.append(GenerationModelOptionOut(
            model_key=binding.scene_key,
            model_label=model_label,
            model_description=model_description,
            display_name=(binding.display_name or "").strip(),
            subtitle=(binding.subtitle or "").strip(),
            sort_order=binding.sort_order,
            hide_aspect_ratio=bool(binding.hide_aspect_ratio),
            hide_resolution=binding.hide_resolution,
            hide_custom_size=bool(binding.hide_custom_size),
            custom_size_min=max(1, int(binding.custom_size_min or 256)),
            custom_size_max=max(1, int(binding.custom_size_max or 4096)),
            custom_size_step=max(1, int(binding.custom_size_step or 8)),
            credit_cost=binding.credit_cost,
            resolution_credit_costs=_normalize_resolution_credit_costs(binding.resolution_credit_costs_json),
            max_reference_images=max(0, int(binding.max_reference_images or 0)),
            aspect_ratio_options=json.loads(binding.aspect_ratio_options_json or "[]"),
            image_size_options=json.loads(binding.image_size_options_json or "[]"),
            custom_size_options=json.loads(binding.custom_size_options_json or "[]"),
            category_id=category["id"] if category else None,
            category_name=category["name"] if category else None,
            category_sort_order=category["sort_order"] if category else None,
        ))
    return items


def get_default_generation_model_key(db: Session) -> str:
    models = list_generation_models(db)
    return models[0].model_key if models else DEFAULT_GENERATION_SCENE


def get_config_or_404(db: Session, config_id: int) -> ExternalApiConfig:
    config = db.query(ExternalApiConfig).filter(ExternalApiConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="接口配置不存在")
    return config


def _ensure_name_unique(db: Session, name: str, exclude_id: int | None = None) -> None:
    query = db.query(ExternalApiConfig).filter(ExternalApiConfig.name == name)
    if exclude_id is not None:
        query = query.filter(ExternalApiConfig.id != exclude_id)
    if query.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="配置名称已存在")


def create_config(db: Session, body: ExternalApiConfigCreate) -> ExternalApiConfigOut:
    _ensure_name_unique(db, body.name)
    config = ExternalApiConfig(**body.model_dump())
    db.add(config)
    db.commit()
    db.refresh(config)
    return _serialize_config(config)


def update_config(db: Session, config_id: int, body: ExternalApiConfigUpdate) -> ExternalApiConfigOut:
    config = get_config_or_404(db, config_id)
    _ensure_name_unique(db, body.name, exclude_id=config_id)
    for key, value in body.model_dump().items():
        setattr(config, key, value)
    db.commit()
    db.refresh(config)
    return _serialize_config(config)


def set_config_status(db: Session, config_id: int, status_value: str) -> ExternalApiConfigOut:
    config = get_config_or_404(db, config_id)
    config.status = status_value
    db.commit()
    db.refresh(config)
    return _serialize_config(config)


def delete_config(db: Session, config_id: int) -> None:
    config = get_config_or_404(db, config_id)
    referenced = (
        db.query(TaskApiAttempt.id)
        .filter(TaskApiAttempt.api_config_id == config.id)
        .first()
    )
    if referenced:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该接口已被历史任务引用，无法删除。如需停用，请改为停用该接口。",
        )
    (
        db.query(ExternalApiSceneBinding)
        .filter(ExternalApiSceneBinding.api_config_id == config.id)
        .update({"api_config_id": None}, synchronize_session=False)
    )
    (
        db.query(ExternalApiSceneBinding)
        .filter(ExternalApiSceneBinding.backup_api_config_id == config.id)
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


def list_scene_bindings(db: Session) -> list[ExternalApiSceneBindingOut]:
    _ensure_scene_bindings(db)
    bindings = (
        db.query(ExternalApiSceneBinding)
        .filter(ExternalApiSceneBinding.is_deleted.is_(False))
        .order_by(ExternalApiSceneBinding.sort_order.asc(), ExternalApiSceneBinding.id.asc())
        .all()
    )
    configs = {row.id: row for row in db.query(ExternalApiConfig).all()}
    return [
        _serialize_scene_binding(
            binding,
            configs.get(binding.api_config_id) if binding.api_config_id else None,
            configs.get(binding.backup_api_config_id) if binding.backup_api_config_id else None,
        )
        for binding in bindings
    ]


def _validate_enabled_binding_config(
    db: Session,
    config_id: int | None,
    *,
    field_label: str,
) -> ExternalApiConfig | None:
    if config_id is None:
        return None
    config = get_config_or_404(db, config_id)
    if config.status != "enabled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"只能绑定启用状态的{field_label}")
    return config


def _validate_scene_binding_configs(
    db: Session,
    *,
    api_config_id: int | None,
    backup_api_config_id: int | None,
) -> tuple[ExternalApiConfig | None, ExternalApiConfig | None]:
    if api_config_id is not None and backup_api_config_id is not None and api_config_id == backup_api_config_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="主接口和备用接口不能绑定同一个接口")
    primary_config = _validate_enabled_binding_config(db, api_config_id, field_label="主接口")
    backup_config = _validate_enabled_binding_config(db, backup_api_config_id, field_label="备用接口")
    return primary_config, backup_config


def list_public_task_scene_configs(db: Session) -> list[TaskSceneConfigOut]:
    category_map = build_scene_category_map(db)
    items: list[TaskSceneConfigOut] = []
    for item in list_scene_bindings(db):
        if item.status != "enabled":
            continue
        category = category_map.get(item.scene_key)
        items.append(TaskSceneConfigOut(
            scene_key=item.scene_key,
            scene_type=item.scene_type,
            scene_label=item.scene_label,
            scene_description=item.scene_description,
            display_name=item.display_name,
            subtitle=item.subtitle,
            sort_order=item.sort_order,
            hide_aspect_ratio=item.hide_aspect_ratio,
            hide_resolution=item.hide_resolution,
            hide_custom_size=item.hide_custom_size,
            custom_size_min=item.custom_size_min,
            custom_size_max=item.custom_size_max,
            custom_size_step=item.custom_size_step,
            credit_cost=item.credit_cost,
            resolution_credit_costs=_normalize_resolution_credit_costs(item.resolution_credit_costs_json),
            max_reference_images=item.max_reference_images,
            aspect_ratio_options=json.loads(item.aspect_ratio_options_json or "[]"),
            image_size_options=json.loads(item.image_size_options_json or "[]"),
            custom_size_options=json.loads(item.custom_size_options_json or "[]"),
            category_id=category["id"] if category else None,
            category_name=category["name"] if category else None,
            category_sort_order=category["sort_order"] if category else None,
        ))
    return items


def create_scene_binding(
    db: Session,
    body: ExternalApiSceneBindingCreate,
) -> ExternalApiSceneBindingOut:
    _ensure_scene_bindings(db)
    if db.query(ExternalApiSceneBinding).filter(ExternalApiSceneBinding.scene_key == body.scene_key).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="场景标识已存在")
    if body.scene_type not in {SCENE_TYPE_GENERATE, SCENE_TYPE_IMAGE_EDIT}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="目前仅支持新增文生图或图编辑场景")
    if not body.scene_label.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="场景名称不能为空")

    primary_config, backup_config = _validate_scene_binding_configs(
        db,
        api_config_id=body.api_config_id,
        backup_api_config_id=body.backup_api_config_id,
    )

    binding = ExternalApiSceneBinding(
        scene_key=body.scene_key,
        scene_type=body.scene_type,
        scene_label=body.scene_label,
        scene_description=body.scene_description,
        sort_order=body.sort_order,
        hide_aspect_ratio=body.hide_aspect_ratio,
        hide_resolution=body.hide_resolution,
        hide_custom_size=body.hide_custom_size,
        custom_size_min=body.custom_size_min,
        custom_size_max=body.custom_size_max,
        custom_size_step=body.custom_size_step,
        status=body.status,
        api_config_id=body.api_config_id,
        backup_api_config_id=body.backup_api_config_id,
        display_name=body.display_name,
        subtitle=body.subtitle,
        credit_cost=body.credit_cost,
        max_reference_images=body.max_reference_images,
        aspect_ratio_options_json=body.aspect_ratio_options_json,
        image_size_options_json=body.image_size_options_json,
        custom_size_options_json=body.custom_size_options_json,
        resolution_mapping_json=body.resolution_mapping_json,
        resolution_credit_costs_json=body.resolution_credit_costs_json,
    )
    db.add(binding)
    db.commit()
    return _serialize_scene_binding(binding, primary_config, backup_config)


def _require_custom_scene_binding(db: Session, scene_key: str) -> ExternalApiSceneBinding:
    _ensure_scene_bindings(db)
    binding = (
        db.query(ExternalApiSceneBinding)
        .filter(
            ExternalApiSceneBinding.scene_key == scene_key,
            ExternalApiSceneBinding.is_deleted.is_(False),
        )
        .first()
    )
    if not binding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调用场景不存在")
    if is_builtin_scene(scene_key):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="内置场景不支持此操作")
    return binding


def set_scene_binding(
    db: Session,
    scene_key: str,
    body: ExternalApiSceneBindingUpdate,
) -> ExternalApiSceneBindingOut:
    _ensure_scene_bindings(db)
    binding = (
        db.query(ExternalApiSceneBinding)
        .filter(
            ExternalApiSceneBinding.scene_key == scene_key,
            ExternalApiSceneBinding.is_deleted.is_(False),
        )
        .first()
    )
    if not binding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调用场景不存在")

    primary_config, backup_config = _validate_scene_binding_configs(
        db,
        api_config_id=body.api_config_id,
        backup_api_config_id=body.backup_api_config_id,
    )

    binding.api_config_id = body.api_config_id
    binding.backup_api_config_id = body.backup_api_config_id
    binding.display_name = body.display_name
    binding.subtitle = body.subtitle
    binding.credit_cost = body.credit_cost
    binding.resolution_credit_costs_json = body.resolution_credit_costs_json
    db.commit()
    return _serialize_scene_binding(binding, primary_config, backup_config)


def update_scene_binding_meta(
    db: Session,
    scene_key: str,
    body: ExternalApiSceneBindingMetaUpdate,
) -> ExternalApiSceneBindingOut:
    binding = _require_custom_scene_binding(db, scene_key)
    next_scene_key = body.scene_key or scene_key
    if next_scene_key != scene_key:
        existing = (
            db.query(ExternalApiSceneBinding)
            .filter(ExternalApiSceneBinding.scene_key == next_scene_key)
            .first()
        )
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="场景标识已存在")
    if not body.scene_label.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="场景名称不能为空")
    binding.scene_key = next_scene_key
    binding.scene_label = body.scene_label
    binding.scene_description = body.scene_description
    binding.sort_order = body.sort_order
    binding.hide_aspect_ratio = body.hide_aspect_ratio
    binding.hide_resolution = body.hide_resolution
    binding.hide_custom_size = body.hide_custom_size
    binding.custom_size_min = body.custom_size_min
    binding.custom_size_max = body.custom_size_max
    binding.custom_size_step = body.custom_size_step
    binding.max_reference_images = body.max_reference_images
    binding.aspect_ratio_options_json = body.aspect_ratio_options_json
    binding.image_size_options_json = body.image_size_options_json
    binding.custom_size_options_json = body.custom_size_options_json
    binding.resolution_mapping_json = body.resolution_mapping_json
    binding.resolution_credit_costs_json = body.resolution_credit_costs_json
    db.commit()
    config = get_config_or_404(db, binding.api_config_id) if binding.api_config_id else None
    backup_config = get_config_or_404(db, binding.backup_api_config_id) if binding.backup_api_config_id else None
    return _serialize_scene_binding(binding, config, backup_config)


def set_scene_binding_status(
    db: Session,
    scene_key: str,
    body: ExternalApiSceneBindingStatusUpdate,
) -> ExternalApiSceneBindingOut:
    binding = _require_custom_scene_binding(db, scene_key)
    binding.status = body.status
    db.commit()
    config = get_config_or_404(db, binding.api_config_id) if binding.api_config_id else None
    backup_config = get_config_or_404(db, binding.backup_api_config_id) if binding.backup_api_config_id else None
    return _serialize_scene_binding(binding, config, backup_config)


def delete_scene_binding(db: Session, scene_key: str) -> None:
    binding = _require_custom_scene_binding(db, scene_key)
    if scene_key in DEFAULT_SCENE_MAP:
        binding.is_deleted = True
        binding.status = "disabled"
        binding.api_config_id = None
        binding.backup_api_config_id = None
        db.commit()
        return
    db.delete(binding)
    db.commit()


def get_scene_credit_cost(db: Session, scene_key: str, resolution: str = "") -> int:
    _ensure_scene_bindings(db)
    binding = (
        db.query(ExternalApiSceneBinding)
        .filter(
            ExternalApiSceneBinding.scene_key == scene_key,
            ExternalApiSceneBinding.is_deleted.is_(False),
        )
        .first()
    )
    if not binding:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的调用场景")
    if binding.status != "enabled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"场景 {scene_key} 已被停用")
    resolution_key = (resolution or "").strip()
    resolution_costs = _normalize_resolution_credit_costs(binding.resolution_credit_costs_json)
    if resolution_key and resolution_key in resolution_costs:
        return resolution_costs[resolution_key]
    return binding.credit_cost


def require_scene_config(db: Session, scene_key: str) -> ExternalApiConfig:
    config, _backup_config = resolve_scene_generation_configs(db, scene_key)
    return config


def resolve_scene_generation_configs(
    db: Session,
    scene_key: str,
) -> tuple[ExternalApiConfig, ExternalApiConfig | None]:
    _ensure_scene_bindings(db)
    binding = (
        db.query(ExternalApiSceneBinding)
        .filter(
            ExternalApiSceneBinding.scene_key == scene_key,
            ExternalApiSceneBinding.is_deleted.is_(False),
        )
        .first()
    )
    if not binding:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的调用场景")
    if binding.status != "enabled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"场景 {scene_key} 已被停用，请联系超级管理员调整",
        )
    if not binding or not binding.api_config_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"场景 {scene_key} 尚未绑定接口，请联系超级管理员在后台设置后再使用",
        )
    config = get_config_or_404(db, binding.api_config_id)
    if config.status != "enabled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"场景 {scene_key} 当前绑定的接口已停用，请联系超级管理员调整绑定",
        )
    backup_config: ExternalApiConfig | None = None
    if binding.backup_api_config_id and binding.backup_api_config_id != binding.api_config_id:
        try:
            candidate = get_config_or_404(db, binding.backup_api_config_id)
        except HTTPException:
            candidate = None
        if candidate and candidate.status == "enabled":
            backup_config = candidate
    return config, backup_config


def render_config(config: ExternalApiConfig, variables: dict[str, Any]) -> RenderedExternalApiConfig:
    headers_template = _load_json(config.headers_json, "Header JSON")
    payload_template = _load_json(config.payload_json, "请求 JSON")

    rendered_headers = _render_json_template(headers_template, variables)
    rendered_payload = _fix_rendered_payload_prompt(
        _render_json_template(payload_template, variables),
        variables,
    )

    return RenderedExternalApiConfig(
        request_url=config.request_url.strip(),
        request_format=(config.request_format or "json").strip().lower() or "json",
        headers=_normalize_headers(rendered_headers),
        payload=rendered_payload,
    )


def render_poll_config(config: ExternalApiConfig, variables: dict[str, Any]) -> RenderedPollExternalApiConfig:
    headers_template = _load_json(config.poll_headers_json or "{}", "轮询 Header JSON")
    payload_template = _load_json(config.poll_payload_json or "{}", "轮询请求 JSON")

    rendered_request_url = _render_string((config.poll_url or "").strip(), variables)
    rendered_headers = _render_json_template(headers_template, variables)
    rendered_payload = _render_json_template(payload_template, variables)

    return RenderedPollExternalApiConfig(
        request_url=str(rendered_request_url or "").strip(),
        method=((config.poll_method or "GET").strip().upper() or "GET"),
        headers=_normalize_headers(rendered_headers),
        payload=rendered_payload,
    )


def parse_http_statuses_json(raw: str | None) -> list[int]:
    candidate = (raw or "").strip() or "[]"
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    normalized: list[int] = []
    for item in parsed:
        if isinstance(item, bool):
            continue
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if 100 <= value <= 599:
            normalized.append(value)
    return normalized


def parse_string_list_json(raw: str | None) -> list[str]:
    candidate = (raw or "").strip() or "[]"
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    normalized: list[str] = []
    for item in parsed:
        cleaned = str(item or "").strip()
        if cleaned:
            normalized.append(cleaned)
    return normalized


def split_response_path(field_path: str) -> list[str]:
    normalized = re.sub(r"\[(\d+)\]", r".\1", (field_path or "").strip()).strip(".")
    return [segment for segment in normalized.split(".") if segment]


def read_value_by_path(payload: object, field_path: str) -> tuple[object | None, object | None]:
    current = payload
    parent: object | None = None
    for segment in split_response_path(field_path):
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


def _detect_image_mime(data: bytes, fallback: str = "image/png") -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in {b"GIF87a", b"GIF89a"}:
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return fallback


def _decode_data_url(value: str) -> tuple[bytes, str] | None:
    if not isinstance(value, str) or not value.startswith("data:"):
        return None
    header, separator, payload = value.partition(",")
    if not separator or not payload:
        return None
    mime_type = (header[5:].split(";", 1)[0] or "image/png").strip() or "image/png"
    try:
        if ";base64" in header:
            return base64.b64decode(payload), mime_type
        return payload.encode("utf-8"), mime_type
    except Exception:
        return None


def _decode_base64_image_value(value: str) -> tuple[bytes, str] | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    if cleaned.startswith("data:"):
        return _decode_data_url(cleaned)
    try:
        raw = base64.b64decode(cleaned, validate=False)
    except Exception:
        return None
    if not raw:
        return None
    return raw, _detect_image_mime(raw)


def _decode_multipart_file_value(value: Any) -> tuple[bytes, str] | None:
    if isinstance(value, dict):
        base64_value = value.get("b64_json")
        if isinstance(base64_value, str) and base64_value.strip():
            decoded = _decode_base64_image_value(base64_value)
            if not decoded:
                return None
            raw, detected_mime = decoded
            mime_type = str(value.get("mime_type") or value.get("mimeType") or "").strip() or detected_mime
            return raw, mime_type

        data_url_value = value.get("data_url")
        if isinstance(data_url_value, str):
            decoded = _decode_data_url(data_url_value)
            if decoded:
                return decoded

        file_url_value = value.get("file_url") or value.get("fileUri") or value.get("url")
        if isinstance(file_url_value, str) and file_url_value.strip():
            decoded = load_image_bytes(file_url_value.strip())
            if not decoded:
                return None
            raw, detected_mime = decoded
            mime_type = str(value.get("mime_type") or value.get("mimeType") or "").strip() or detected_mime
            return raw, mime_type

        inline_data = value.get("inlineData")
        if isinstance(inline_data, dict):
            inline_base64 = inline_data.get("data")
            if isinstance(inline_base64, str) and inline_base64.strip():
                try:
                    raw = base64.b64decode(inline_base64)
                except Exception:
                    return None
                mime_type = str(inline_data.get("mimeType") or "").strip() or _detect_image_mime(raw)
                return raw, mime_type

    if isinstance(value, str):
        return _decode_data_url(value)
    return None


def _build_multipart_files(field_name: str, value: Any) -> list[tuple[str, tuple[str, bytes, str]]]:
    raw_items = value if isinstance(value, list) else [value]
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    for index, item in enumerate(raw_items, start=1):
        decoded = _decode_multipart_file_value(item)
        if not decoded:
            continue
        raw, mime_type = decoded
        ext = IMAGE_MIME_EXTENSIONS.get(mime_type, ".png")
        filename = ""
        if isinstance(item, dict):
            filename = str(item.get("file_name") or item.get("filename") or item.get("name") or "").strip()
        if not filename:
            filename = f"{field_name}_{index}{ext}"
        files.append((field_name, (filename, raw, mime_type)))
    return files


def _stringify_form_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def should_use_multipart_request(rendered: RenderedExternalApiConfig) -> bool:
    return rendered.request_format == "multipart"


def build_external_request_kwargs(rendered: RenderedExternalApiConfig) -> dict[str, Any]:
    if not should_use_multipart_request(rendered):
        return {
            "headers": rendered.headers,
            "json": rendered.payload,
        }

    if not isinstance(rendered.payload, dict):
        raise ValueError("multipart 请求要求 payload_json 渲染结果为 JSON 对象")

    payload = rendered.payload
    headers = {
        key: value
        for key, value in rendered.headers.items()
        if key.lower() != "content-type"
    }
    data: dict[str, str] = {}
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    for key, value in payload.items():
        if value is None:
            continue
        if key in MULTIPART_EDIT_FILE_FIELDS:
            files.extend(_build_multipart_files(MULTIPART_EDIT_FILE_FIELD_ALIASES[key], value))
            continue
        data[key] = _stringify_form_value(value)
    return {
        "headers": headers,
        "data": data,
        "files": files,
    }


def build_external_poll_request_kwargs(rendered: RenderedPollExternalApiConfig) -> dict[str, Any]:
    method = (rendered.method or "GET").strip().upper()
    if method == "GET":
        if isinstance(rendered.payload, dict):
            return {
                "headers": rendered.headers,
                "params": rendered.payload,
            }
        return {
            "headers": rendered.headers,
        }
    return {
        "headers": rendered.headers,
        "json": rendered.payload,
    }


def build_secret_variables(db: Session) -> dict[str, str]:
    record = db.query(ApiKey).first()
    generation_key = (record.key or "").strip() if record else ""
    prompt_reverse_key = (record.tongyi_key or "").strip() if record else ""
    return {
        "api_key": generation_key,
        "bearer_token": prompt_reverse_key or generation_key,
    }


def _build_test_variables(db: Session) -> dict[str, Any]:
    one_pixel_png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+XGJ0AAAAASUVORK5CYII="
    sample_inline_image = {"inlineData": {"mimeType": "image/png", "data": one_pixel_png}}
    return {
        "prompt": "连接测试",
        "aspect_ratio": "1:1",
        "image_size": "2K",
        "custom_size": "1024x1024",
        "mapped_resolution": "2048x2048",
        "resolved_resolution": "1024x1024",
        "contents_parts": [
            sample_inline_image,
            sample_inline_image,
            {"text": "连接测试"},
        ],
        "generation_config": {"responseModalities": ["TEXT"]},
        "mode": "generate",
        "reference_image_1": sample_inline_image,
        "reference_image_2": sample_inline_image,
        "reference_image_3": sample_inline_image,
        "reference_image_1_url": "https://example.com/reference-image-1.png",
        "reference_image_2_url": "https://example.com/reference-image-2.png",
        "reference_image_3_url": "https://example.com/reference-image-3.png",
        "reference_image_1_base64": one_pixel_png,
        "reference_image_2_base64": one_pixel_png,
        "reference_image_3_base64": one_pixel_png,
        "reference_image_1_mime_type": "image/png",
        "reference_image_2_mime_type": "image/png",
        "reference_image_3_mime_type": "image/png",
        "reference_image_1_data_url": f"data:image/png;base64,{one_pixel_png}",
        "reference_image_2_data_url": f"data:image/png;base64,{one_pixel_png}",
        "reference_image_3_data_url": f"data:image/png;base64,{one_pixel_png}",
        "reference_images": [
            "https://example.com/reference-image-1.png",
            "https://example.com/reference-image-2.png",
            "https://example.com/reference-image-3.png",
        ],
        "reference_image_count": 3,
        "source_image_url": "https://example.com/source-image.png",
        "image_data_url": f"data:image/png;base64,{one_pixel_png}",
        "prompt_reverse_text": "请返回测试提示词",
        "prompt_optimize_text": "请优化测试提示词",
        "prompt_optimize_style_prompt": "偏电影感与光影层次，补足画面细节、材质与镜头语言",
        "style_prompt": "偏电影感与光影层次，补足画面细节、材质与镜头语言",
        **build_secret_variables(db),
    }


def test_external_api_config(db: Session, body: ExternalApiConfigCreate) -> ExternalApiConfigTestResult:
    config = ExternalApiConfig(**body.model_dump())
    variables = _build_test_variables(db)
    rendered = render_config(config, variables)

    try:
        with httpx.Client(timeout=20, trust_env=False) as client:
            response = client.post(
                rendered.request_url,
                **build_external_request_kwargs(rendered),
            )
        preview = response.text[:1200]
        is_async = (config.call_mode or "sync").strip().lower() == "async"
        success_statuses = parse_http_statuses_json(config.submit_success_statuses_json) or [200, 201, 202]
        if is_async:
            try:
                payload = response.json()
            except Exception:
                payload = None
            task_id_value, _parent = read_value_by_path(payload, config.task_id_field or "") if payload else (None, None)
            has_task_id = isinstance(task_id_value, (str, int)) and str(task_id_value).strip() != ""
            return ExternalApiConfigTestResult(
                success=response.status_code in success_statuses and has_task_id,
                request_url=rendered.request_url,
                status_code=response.status_code,
                response_preview=preview or "(空响应)",
            )
        return ExternalApiConfigTestResult(
            success=200 <= response.status_code < 300,
            request_url=rendered.request_url,
            status_code=response.status_code,
            response_preview=preview or "(空响应)",
        )
    except httpx.TimeoutException:
        return ExternalApiConfigTestResult(
            success=False,
            request_url=rendered.request_url,
            response_preview="请求超时，请检查接口地址、网络或服务端响应时间",
        )
    except Exception as exc:
        return ExternalApiConfigTestResult(
            success=False,
            request_url=rendered.request_url,
            response_preview=f"请求发送失败：{exc}",
        )


def _pick_generation_config_for_scene(db: Session, scene_key: str) -> ExternalApiConfig | None:
    candidates = db.query(ExternalApiConfig).filter(ExternalApiConfig.status == "enabled").order_by(ExternalApiConfig.id.asc()).all()
    for item in candidates:
        if item.model_key == scene_key and item.is_active_generation:
            return item
    for item in candidates:
        if item.model_key == scene_key:
            return item
    for item in candidates:
        if item.is_active_generation:
            return item
    return candidates[0] if candidates else None


def _pick_prompt_reverse_config(db: Session) -> ExternalApiConfig | None:
    candidates = db.query(ExternalApiConfig).filter(ExternalApiConfig.status == "enabled").order_by(ExternalApiConfig.id.asc()).all()
    for item in candidates:
        if item.is_active_prompt_reverse:
            return item
    return candidates[-1] if candidates else None


def _pick_prompt_optimize_config(db: Session) -> ExternalApiConfig | None:
    candidates = db.query(ExternalApiConfig).filter(ExternalApiConfig.status == "enabled").order_by(ExternalApiConfig.id.asc()).all()
    for item in candidates:
        if "{{prompt_optimize_text}}" in (item.payload_json or ""):
            return item
    return None


def _pick_inpaint_config(db: Session) -> ExternalApiConfig | None:
    candidates = db.query(ExternalApiConfig).filter(ExternalApiConfig.status == "enabled").order_by(ExternalApiConfig.id.asc()).all()
    for item in candidates:
        if item.is_active_inpaint:
            return item
    preferred = _pick_generation_config_for_scene(db, SCENE_BANANA_PRO)
    return preferred or (candidates[0] if candidates else None)


def _pick_smart_cutout_config(db: Session) -> ExternalApiConfig | None:
    candidates = db.query(ExternalApiConfig).filter(ExternalApiConfig.status == "enabled").order_by(ExternalApiConfig.id.asc()).all()
    for item in candidates:
        if getattr(item, "is_active_smart_cutout", False):
            return item
    preferred = _pick_generation_config_for_scene(db, SCENE_BANANA_PRO)
    return preferred or (candidates[0] if candidates else None)


def _pick_default_config_for_definition(db: Session, definition: dict[str, Any]) -> ExternalApiConfig | None:
    if definition["scene_type"] == SCENE_TYPE_GENERATE:
        return _pick_generation_config_for_scene(db, definition["scene_key"])
    if definition["scene_type"] == SCENE_TYPE_IMAGE_EDIT:
        source_scene_key = IMAGE_EDIT_SCENE_SOURCE_MAP.get(definition["scene_key"], SCENE_BANANA_PRO)
        return _pick_generation_config_for_scene(db, source_scene_key)
    if definition["scene_type"] == SCENE_TYPE_PROMPT_REVERSE:
        return _pick_prompt_reverse_config(db)
    if definition["scene_type"] == SCENE_TYPE_PROMPT_OPTIMIZE:
        return _pick_prompt_optimize_config(db)
    if definition["scene_type"] == SCENE_TYPE_INPAINT:
        return _pick_inpaint_config(db)
    if definition["scene_type"] == SCENE_TYPE_SMART_CUTOUT:
        return _pick_smart_cutout_config(db)
    return None


def _ensure_scene_bindings(db: Session) -> None:
    bindings = db.query(ExternalApiSceneBinding).all()
    updated = False
    binding_map = {str(binding.scene_key or "").strip(): binding for binding in bindings if (binding.scene_key or "").strip()}
    for definition in DEFAULT_SCENE_DEFINITIONS:
        if definition["scene_key"] in binding_map:
            continue
        aspect_ratio_options_json, image_size_options_json, custom_size_options_json = _get_scene_option_json(
            definition["scene_type"],
            None,
            None,
            None,
        )
        default_config = _pick_default_config_for_definition(db, definition)
        binding = ExternalApiSceneBinding(
            scene_key=definition["scene_key"],
            scene_type=definition["scene_type"],
            scene_label=definition["scene_label"],
            scene_description=definition["scene_description"],
            sort_order=definition["sort_order"],
            hide_aspect_ratio=definition["hide_aspect_ratio"],
            hide_resolution=definition["hide_resolution"],
            hide_custom_size=definition["hide_custom_size"],
            status="enabled",
            api_config_id=default_config.id if default_config else None,
            backup_api_config_id=None,
            display_name="",
            subtitle="",
            credit_cost=get_default_credit_cost(definition["scene_key"], definition["scene_type"]),
            max_reference_images=get_default_max_reference_images(definition["scene_type"]),
            aspect_ratio_options_json=aspect_ratio_options_json,
            image_size_options_json=image_size_options_json,
            custom_size_options_json=custom_size_options_json,
            resolution_mapping_json=_get_resolution_mapping_json(None),
            resolution_credit_costs_json=_get_resolution_credit_costs_json(None),
        )
        db.add(binding)
        bindings.append(binding)
        binding_map[definition["scene_key"]] = binding
        updated = True
    for binding in bindings:
        default_definition = DEFAULT_SCENE_MAP.get(binding.scene_key)
        default_cost = get_default_credit_cost(binding.scene_key, binding.scene_type)
        aspect_ratio_options_json, image_size_options_json, custom_size_options_json = _get_scene_option_json(
            binding.scene_type or SCENE_TYPE_GENERATE,
            binding.aspect_ratio_options_json,
            binding.image_size_options_json,
            binding.custom_size_options_json,
        )
        if binding.credit_cost is None:
            binding.credit_cost = default_cost
            updated = True
        if (binding.status or "").strip().lower() not in {"enabled", "disabled"}:
            binding.status = "enabled"
            updated = True
        if (binding.aspect_ratio_options_json or "") != aspect_ratio_options_json:
            binding.aspect_ratio_options_json = aspect_ratio_options_json
            updated = True
        if (binding.image_size_options_json or "") != image_size_options_json:
            binding.image_size_options_json = image_size_options_json
            updated = True
        if (binding.custom_size_options_json or "") != custom_size_options_json:
            binding.custom_size_options_json = custom_size_options_json
            updated = True
        resolution_mapping_json = _get_resolution_mapping_json(binding.resolution_mapping_json)
        if (binding.resolution_mapping_json or "") != resolution_mapping_json:
            binding.resolution_mapping_json = resolution_mapping_json
            updated = True
        resolution_credit_costs_json = _get_resolution_credit_costs_json(binding.resolution_credit_costs_json)
        if (binding.resolution_credit_costs_json or "") != resolution_credit_costs_json:
            binding.resolution_credit_costs_json = resolution_credit_costs_json
            updated = True
        if default_definition:
            if not (binding.scene_type or "").strip():
                binding.scene_type = default_definition["scene_type"]
                updated = True
            if is_builtin_scene(binding.scene_key):
                if binding.scene_type != default_definition["scene_type"]:
                    binding.scene_type = default_definition["scene_type"]
                    updated = True
                if (binding.scene_label or "").strip() != default_definition["scene_label"]:
                    binding.scene_label = default_definition["scene_label"]
                    updated = True
                if (binding.scene_description or "").strip() != default_definition["scene_description"]:
                    binding.scene_description = default_definition["scene_description"]
                    updated = True
                if int(binding.sort_order or 0) != int(default_definition["sort_order"]):
                    binding.sort_order = default_definition["sort_order"]
                    updated = True
                if bool(binding.hide_aspect_ratio) != bool(default_definition["hide_aspect_ratio"]):
                    binding.hide_aspect_ratio = default_definition["hide_aspect_ratio"]
                    updated = True
                if bool(binding.hide_resolution) != bool(default_definition["hide_resolution"]):
                    binding.hide_resolution = default_definition["hide_resolution"]
                    updated = True
                if bool(binding.hide_custom_size) != bool(default_definition["hide_custom_size"]):
                    binding.hide_custom_size = default_definition["hide_custom_size"]
                    updated = True
            else:
                if not (binding.scene_label or "").strip():
                    binding.scene_label = default_definition["scene_label"]
                    updated = True
                if not (binding.scene_description or "").strip():
                    binding.scene_description = default_definition["scene_description"]
                    updated = True
                if int(binding.sort_order or 0) <= 0:
                    binding.sort_order = default_definition["sort_order"]
                    updated = True
                if binding.hide_aspect_ratio is None:
                    binding.hide_aspect_ratio = default_definition["hide_aspect_ratio"]
                    updated = True
                if binding.hide_resolution is None:
                    binding.hide_resolution = default_definition["hide_resolution"]
                    updated = True
                if binding.hide_custom_size is None:
                    binding.hide_custom_size = default_definition["hide_custom_size"]
                    updated = True
        else:
            if not (binding.scene_type or "").strip():
                binding.scene_type = SCENE_TYPE_GENERATE
                updated = True
            if not (binding.scene_label or "").strip():
                binding.scene_label = binding.scene_key
                updated = True
            if binding.hide_aspect_ratio is None:
                binding.hide_aspect_ratio = False
                updated = True
            if binding.hide_resolution is None:
                binding.hide_resolution = False
                updated = True
            if binding.hide_custom_size is None:
                binding.hide_custom_size = True
                updated = True
            if binding.max_reference_images is None:
                binding.max_reference_images = get_default_max_reference_images(binding.scene_type)
                updated = True
    if updated:
        db.commit()


def seed_legacy_configs(db: Session, ai_api_url: str, prompt_reverse_url: str) -> None:
    api_key = db.query(ApiKey).first()
    generation_key = (api_key.key or "").strip() if api_key else ""
    prompt_reverse_key = (api_key.tongyi_key or "").strip() if api_key else ""

    if not db.query(ExternalApiConfig).first():
        created = False
        if generation_key:
            db.add(ExternalApiConfig(
                name="默认生图接口",
                description="从旧版 API Key 配置自动迁移而来",
                group_name="默认",
                request_url=ai_api_url,
                headers_json=_default_generation_headers(generation_key),
                payload_json=_default_generation_payload(),
                response_json=_default_generation_response(),
                result_base64_field="candidates.0.content.parts.0.inlineData.data",
                status="enabled",
            ))
            created = True
        if prompt_reverse_key:
            db.add(ExternalApiConfig(
                name="默认反推接口",
                description="从旧版通义配置自动迁移而来",
                group_name="默认",
                request_url=prompt_reverse_url,
                headers_json=_default_prompt_reverse_headers(prompt_reverse_key),
                payload_json=_default_prompt_reverse_payload(),
                status="enabled",
            ))
            db.add(ExternalApiConfig(
                name="默认提示词优化接口",
                description="从旧版通义配置自动迁移而来",
                group_name="默认",
                request_url=prompt_reverse_url,
                headers_json=_default_prompt_reverse_headers(prompt_reverse_key),
                payload_json=_default_prompt_optimize_payload(),
                status="enabled",
            ))
            created = True
        if created:
            db.commit()

    _ensure_scene_bindings(db)
