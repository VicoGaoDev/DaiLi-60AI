from __future__ import annotations

import json

import httpx
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.chat_external_api_config import ChatExternalApiConfig
from app.models.chat_external_api_scene_binding import ChatExternalApiSceneBinding
from app.schemas.chat_external_api_config import (
    ChatExternalApiConfigCreate,
    ChatExternalApiConfigOut,
    ChatExternalApiConfigTestResult,
    ChatExternalApiConfigUpdate,
    ChatExternalApiSceneBindingCreate,
    ChatExternalApiSceneBindingMetaUpdate,
    ChatExternalApiSceneBindingOut,
    ChatExternalApiSceneBindingUpdate,
    ChatGenerationModelOptionOut,
    ChatStarterPromptItem,
    MAX_CHAT_STARTER_PROMPTS,
)
from app.services.external_api_config_service import (
    build_external_request_kwargs,
    build_secret_variables,
    parse_http_statuses_json,
    read_value_by_path,
    render_config,
)


MAX_TEST_RESPONSE_PREVIEW_LENGTH = 2000
DEFAULT_CHAT_PAYLOAD_JSON = json.dumps(
    {
        "model": "gpt-4o-mini",
        "messages": "{{messages}}",
    },
    ensure_ascii=False,
    indent=2,
)


def _enforce_sync_call_mode(config: ChatExternalApiConfig) -> ChatExternalApiConfig:
    if (config.call_mode or "").strip().lower() != "sync":
        config.call_mode = "sync"
    if (config.request_format or "").strip().lower() != "json":
        config.request_format = "json"
    return config


def _extract_text_value(payload: object, field_path: str) -> str:
    raw_value, _parent = read_value_by_path(payload, field_path or "")
    return str(raw_value or "").strip()


def payload_json_wants_stream(raw: str | None) -> bool:
    """仅当请求体 JSON 显式写了布尔 true 才走真流式。"""
    try:
        payload = json.loads(raw or "")
    except Exception:
        return False
    return isinstance(payload, dict) and payload.get("stream") is True


def _parse_starter_prompts(raw: str | None) -> list[ChatStarterPromptItem]:
    if not (raw or "").strip():
        return []
    try:
        payload = json.loads(raw)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    items: list[ChatStarterPromptItem] = []
    for entry in payload[:MAX_CHAT_STARTER_PROMPTS]:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        tag = str(entry.get("tag") or "").strip()[:20]
        image_url = str(entry.get("image_url") or "").strip()[:2000]
        if image_url and not image_url.lower().startswith(("http://", "https://")):
            image_url = ""
        items.append(ChatStarterPromptItem(tag=tag, text=text[:500], image_url=image_url))
    return items


def _dump_starter_prompts(items: list[ChatStarterPromptItem] | None) -> str:
    normalized = []
    for item in (items or []):
        text = (item.text or "").strip()[:500]
        if not text:
            continue
        payload = {
            "tag": (item.tag or "").strip()[:20],
            "text": text,
        }
        image_url = (item.image_url or "").strip()[:2000]
        if image_url:
            payload["image_url"] = image_url
        normalized.append(payload)
        if len(normalized) >= MAX_CHAT_STARTER_PROMPTS:
            break
    return json.dumps(normalized, ensure_ascii=False)


def _serialize_scene_binding(
    binding: ChatExternalApiSceneBinding,
    primary_config: ChatExternalApiConfig | None,
    backup_config: ChatExternalApiConfig | None,
) -> ChatExternalApiSceneBindingOut:
    return ChatExternalApiSceneBindingOut(
        scene_key=binding.scene_key,
        scene_label=binding.scene_label,
        scene_description=binding.scene_description or "",
        display_name=binding.display_name or "",
        subtitle=binding.subtitle or "",
        sort_order=int(binding.sort_order or 0),
        status=(binding.status or "enabled"),
        api_config_id=binding.api_config_id,
        api_config_name=primary_config.name if primary_config else "",
        api_group_name=primary_config.group_name if primary_config else "",
        api_status=(primary_config.status if primary_config else None),
        backup_api_config_id=binding.backup_api_config_id,
        backup_api_config_name=backup_config.name if backup_config else "",
        backup_api_group_name=backup_config.group_name if backup_config else "",
        backup_api_status=(backup_config.status if backup_config else None),
        credit_cost=int(binding.credit_cost or 0),
        system_prompt=binding.system_prompt or "",
        context_message_limit=max(2, int(binding.context_message_limit or 10)),
        opening_greeting=binding.opening_greeting or "",
        starter_prompts=_parse_starter_prompts(getattr(binding, "starter_prompts_json", None)),
    )


def _require_config(db: Session, config_id: int) -> ChatExternalApiConfig:
    config = db.query(ChatExternalApiConfig).filter(ChatExternalApiConfig.id == config_id).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话接口配置不存在")
    return config


def _require_scene_binding(db: Session, scene_key: str) -> ChatExternalApiSceneBinding:
    binding = (
        db.query(ChatExternalApiSceneBinding)
        .filter(
            ChatExternalApiSceneBinding.scene_key == (scene_key or "").strip().lower(),
            ChatExternalApiSceneBinding.is_deleted.is_(False),
        )
        .first()
    )
    if not binding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话场景不存在")
    return binding


def _validate_scene_binding_configs(
    db: Session,
    *,
    api_config_id: int | None,
    backup_api_config_id: int | None,
) -> tuple[ChatExternalApiConfig, ChatExternalApiConfig | None]:
    if not api_config_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="必须绑定主对话接口")
    primary_config = _require_config(db, api_config_id)
    backup_config = None
    if backup_api_config_id is not None:
        if backup_api_config_id == api_config_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="备用接口不能和主接口相同")
        backup_config = _require_config(db, backup_api_config_id)
    return primary_config, backup_config


def list_chat_configs(db: Session) -> list[ChatExternalApiConfigOut]:
    return [
        ChatExternalApiConfigOut.model_validate(_enforce_sync_call_mode(item))
        for item in db.query(ChatExternalApiConfig)
        .order_by(ChatExternalApiConfig.group_name.asc(), ChatExternalApiConfig.name.asc())
        .all()
    ]


def create_chat_config(db: Session, body: ChatExternalApiConfigCreate) -> ChatExternalApiConfigOut:
    exists = db.query(ChatExternalApiConfig.id).filter(ChatExternalApiConfig.name == body.name).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="对话接口配置名称已存在")
    config = ChatExternalApiConfig(**body.model_dump())
    _enforce_sync_call_mode(config)
    db.add(config)
    db.commit()
    db.refresh(config)
    return ChatExternalApiConfigOut.model_validate(config)


def update_chat_config(db: Session, config_id: int, body: ChatExternalApiConfigUpdate) -> ChatExternalApiConfigOut:
    config = _require_config(db, config_id)
    duplicated = (
        db.query(ChatExternalApiConfig.id)
        .filter(ChatExternalApiConfig.name == body.name, ChatExternalApiConfig.id != config_id)
        .first()
    )
    if duplicated:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="对话接口配置名称已存在")
    for key, value in body.model_dump().items():
        setattr(config, key, value)
    _enforce_sync_call_mode(config)
    db.add(config)
    db.commit()
    db.refresh(config)
    return ChatExternalApiConfigOut.model_validate(config)


def set_chat_config_status(db: Session, config_id: int, status_value: str) -> ChatExternalApiConfigOut:
    config = _require_config(db, config_id)
    config.status = (status_value or "enabled").strip().lower()
    db.add(config)
    db.commit()
    db.refresh(config)
    return ChatExternalApiConfigOut.model_validate(_enforce_sync_call_mode(config))


def delete_chat_config(db: Session, config_id: int) -> None:
    config = _require_config(db, config_id)
    (
        db.query(ChatExternalApiSceneBinding)
        .filter(ChatExternalApiSceneBinding.api_config_id == config.id)
        .update({"api_config_id": None}, synchronize_session=False)
    )
    (
        db.query(ChatExternalApiSceneBinding)
        .filter(ChatExternalApiSceneBinding.backup_api_config_id == config.id)
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


def list_chat_scene_bindings(db: Session) -> list[ChatExternalApiSceneBindingOut]:
    configs = {item.id: item for item in db.query(ChatExternalApiConfig).all()}
    bindings = (
        db.query(ChatExternalApiSceneBinding)
        .filter(ChatExternalApiSceneBinding.is_deleted.is_(False))
        .order_by(ChatExternalApiSceneBinding.sort_order.asc(), ChatExternalApiSceneBinding.scene_key.asc())
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


def create_chat_scene_binding(db: Session, body: ChatExternalApiSceneBindingCreate) -> ChatExternalApiSceneBindingOut:
    exists = (
        db.query(ChatExternalApiSceneBinding.id)
        .filter(ChatExternalApiSceneBinding.scene_key == body.scene_key)
        .first()
    )
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="对话场景标识已存在")
    primary_config, backup_config = _validate_scene_binding_configs(
        db,
        api_config_id=body.api_config_id,
        backup_api_config_id=body.backup_api_config_id,
    )
    payload = body.model_dump(exclude={"starter_prompts"})
    binding = ChatExternalApiSceneBinding(
        **payload,
        starter_prompts_json=_dump_starter_prompts(body.starter_prompts),
    )
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return _serialize_scene_binding(binding, primary_config, backup_config)


def update_chat_scene_binding(
    db: Session,
    scene_key: str,
    body: ChatExternalApiSceneBindingUpdate,
) -> ChatExternalApiSceneBindingOut:
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
    binding.credit_cost = body.credit_cost
    binding.status = body.status
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return _serialize_scene_binding(binding, primary_config, backup_config)


def update_chat_scene_binding_meta(
    db: Session,
    scene_key: str,
    body: ChatExternalApiSceneBindingMetaUpdate,
) -> ChatExternalApiSceneBindingOut:
    binding = _require_scene_binding(db, scene_key)
    next_scene_key = body.scene_key or scene_key
    if next_scene_key != scene_key:
        exists = (
            db.query(ChatExternalApiSceneBinding.id)
            .filter(
                ChatExternalApiSceneBinding.scene_key == next_scene_key,
                ChatExternalApiSceneBinding.id != binding.id,
            )
            .first()
        )
        if exists:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="对话场景标识已存在")
        binding.scene_key = next_scene_key
    binding.scene_label = body.scene_label
    binding.scene_description = body.scene_description
    binding.sort_order = body.sort_order
    binding.credit_cost = body.credit_cost
    binding.system_prompt = body.system_prompt
    binding.context_message_limit = body.context_message_limit
    binding.opening_greeting = body.opening_greeting
    binding.starter_prompts_json = _dump_starter_prompts(body.starter_prompts)
    db.add(binding)
    db.commit()
    db.refresh(binding)
    primary_config = _require_config(db, binding.api_config_id) if binding.api_config_id else None
    backup_config = _require_config(db, binding.backup_api_config_id) if binding.backup_api_config_id else None
    return _serialize_scene_binding(binding, primary_config, backup_config)


def set_chat_scene_binding_status(
    db: Session,
    scene_key: str,
    status_value: str,
) -> ChatExternalApiSceneBindingOut:
    binding = _require_scene_binding(db, scene_key)
    binding.status = (status_value or "enabled").strip().lower()
    db.add(binding)
    db.commit()
    db.refresh(binding)
    primary_config = _require_config(db, binding.api_config_id) if binding.api_config_id else None
    backup_config = _require_config(db, binding.backup_api_config_id) if binding.backup_api_config_id else None
    return _serialize_scene_binding(binding, primary_config, backup_config)


def delete_chat_scene_binding(db: Session, scene_key: str) -> None:
    binding = _require_scene_binding(db, scene_key)
    binding.is_deleted = True
    db.add(binding)
    db.commit()


def list_chat_generation_models(db: Session) -> list[ChatGenerationModelOptionOut]:
    configs = {item.id: item for item in db.query(ChatExternalApiConfig).all()}
    bindings = (
        db.query(ChatExternalApiSceneBinding)
        .filter(
            ChatExternalApiSceneBinding.is_deleted.is_(False),
            ChatExternalApiSceneBinding.status == "enabled",
        )
        .order_by(ChatExternalApiSceneBinding.sort_order.asc(), ChatExternalApiSceneBinding.scene_key.asc())
        .all()
    )
    return [
        ChatGenerationModelOptionOut(
            model_key=item.scene_key,
            model_label=item.scene_label,
            model_description=item.scene_description or "",
            # 前台选择的是场景：优先场景名称，其次展示名
            display_name=(item.scene_label or item.display_name or item.scene_key),
            subtitle=item.subtitle or "",
            sort_order=int(item.sort_order or 0),
            credit_cost=int(item.credit_cost or 0),
            opening_greeting=item.opening_greeting or "",
            starter_prompts=_parse_starter_prompts(getattr(item, "starter_prompts_json", None)),
            stream=payload_json_wants_stream(configs[item.api_config_id].payload_json),
        )
        for item in bindings
        if item.api_config_id
        and configs.get(item.api_config_id)
        and (configs[item.api_config_id].status or "").strip().lower() == "enabled"
    ]


def resolve_chat_scene_configs(
    db: Session,
    scene_key: str,
) -> tuple[ChatExternalApiConfig, ChatExternalApiConfig | None, ChatExternalApiSceneBinding]:
    binding = _require_scene_binding(db, scene_key)
    if (binding.status or "").strip().lower() != "enabled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="对话场景已禁用")
    primary_config = _require_config(db, binding.api_config_id) if binding.api_config_id else None
    if not primary_config or (primary_config.status or "").strip().lower() != "enabled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="对话主接口未配置或已禁用")
    backup_config = None
    if binding.backup_api_config_id:
        try:
            backup_candidate = _require_config(db, binding.backup_api_config_id)
        except HTTPException:
            backup_candidate = None
        if backup_candidate and (backup_candidate.status or "").strip().lower() == "enabled":
            backup_config = backup_candidate
    return primary_config, backup_config, binding


def require_chat_scene_config(db: Session, scene_key: str) -> ChatExternalApiConfig:
    primary_config, _backup_config, _binding = resolve_chat_scene_configs(db, scene_key)
    return primary_config


def get_chat_scene_credit_cost(db: Session, scene_key: str) -> int:
    binding = _require_scene_binding(db, scene_key)
    if (binding.status or "").strip().lower() != "enabled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="对话场景已禁用")
    return int(binding.credit_cost or 0)


def get_chat_scene_binding(db: Session, scene_key: str) -> ChatExternalApiSceneBinding:
    return _require_scene_binding(db, scene_key)


def test_chat_external_api_config(
    db: Session,
    body: ChatExternalApiConfigCreate,
) -> ChatExternalApiConfigTestResult:
    config = ChatExternalApiConfig(**body.model_dump())
    _enforce_sync_call_mode(config)
    messages = [{"role": "user", "content": "ping"}]
    variables = {
        **build_secret_variables(db),
        "messages": messages,
        "system_prompt": "你是一个连接测试助手。",
        "user_message": "ping",
    }
    rendered = render_config(config, variables)
    payload = rendered.payload
    if isinstance(payload, dict) and payload.get("stream") is True:
        rendered = rendered.model_copy(update={"payload": {**payload, "stream": False}})
    request_kwargs = build_external_request_kwargs(rendered)
    with httpx.Client(timeout=15, trust_env=False) as client:
        response = client.post(rendered.request_url, **request_kwargs)
    preview = (response.text or "")[:MAX_TEST_RESPONSE_PREVIEW_LENGTH]
    extracted_text = ""
    try:
        payload = response.json()
        extracted_text = _extract_text_value(payload, config.result_text_field)
        if not extracted_text and config.result_error_field:
            extracted_text = _extract_text_value(payload, config.result_error_field)
    except Exception:
        payload = None
    success_statuses = parse_http_statuses_json(config.submit_success_statuses_json) or [200, 201, 202]
    success = response.status_code in success_statuses and bool(extracted_text)
    return ChatExternalApiConfigTestResult(
        success=success,
        request_url=rendered.request_url,
        status_code=response.status_code,
        response_preview=preview or "(空响应)",
        extracted_text=extracted_text,
    )
