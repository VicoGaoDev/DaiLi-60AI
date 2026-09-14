from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.external_api_config import _validate_integer_list_json, _validate_json_text


StatusType = Literal["enabled", "disabled"]
RequestFormatType = Literal["json"]
CallModeType = Literal["sync"]
MAX_CHAT_STARTER_PROMPTS = 6


class ChatStarterPromptItem(BaseModel):
    tag: str = ""
    text: str = ""
    image_url: str = ""

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if len(cleaned) > 20:
            raise ValueError("内置问题标签最多 20 字")
        return cleaned

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("内置问题内容不能为空")
        if len(cleaned) > 500:
            raise ValueError("内置问题内容最多 500 字")
        return cleaned

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            return ""
        if len(cleaned) > 2000:
            raise ValueError("内置问题图片地址过长")
        lowered = cleaned.lower()
        if not (lowered.startswith("http://") or lowered.startswith("https://")):
            raise ValueError("内置问题图片地址必须是 http/https URL")
        return cleaned


def _normalize_starter_prompts(value: list[ChatStarterPromptItem] | None) -> list[ChatStarterPromptItem]:
    items = list(value or [])
    if len(items) > MAX_CHAT_STARTER_PROMPTS:
        raise ValueError(f"内置问题最多 {MAX_CHAT_STARTER_PROMPTS} 条")
    return items


class ChatExternalApiConfigBase(BaseModel):
    name: str
    description: str = ""
    group_name: str = "默认"
    request_url: str
    request_format: RequestFormatType = "json"
    headers_json: str = "{}"
    payload_json: str = "{}"
    response_json: str = "{}"
    result_text_field: str = ""
    result_error_field: str = ""
    call_mode: CallModeType = "sync"
    submit_success_statuses_json: str = "[200, 201, 202]"
    status: StatusType = "enabled"

    @field_validator("name", "request_url")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("字段不能为空")
        return cleaned

    @field_validator("description", "group_name", "result_text_field", "result_error_field")
    @classmethod
    def validate_optional_text(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("headers_json")
    @classmethod
    def validate_headers_json(cls, value: str) -> str:
        return _validate_json_text(value, "Header JSON", expect_object=True)

    @field_validator("payload_json", "response_json")
    @classmethod
    def validate_payload_json(cls, value: str) -> str:
        return _validate_json_text(value, "请求 JSON", expect_object=False)

    @field_validator("submit_success_statuses_json")
    @classmethod
    def validate_status_codes_json(cls, value: str) -> str:
        return _validate_integer_list_json(value, "提交成功状态码 JSON")

    @model_validator(mode="after")
    def validate_result_text_field(self):
        if not self.result_text_field.strip():
            raise ValueError("必须填写回复文本字段路径，例如 choices.0.message.content")
        return self


class ChatExternalApiConfigCreate(ChatExternalApiConfigBase):
    pass


class ChatExternalApiConfigUpdate(ChatExternalApiConfigBase):
    pass


class ChatExternalApiConfigStatusUpdate(BaseModel):
    status: StatusType


class ChatExternalApiConfigOut(ChatExternalApiConfigBase):
    id: int
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ChatExternalApiConfigTestResult(BaseModel):
    success: bool
    request_url: str
    status_code: int | None = None
    response_preview: str
    extracted_text: str = ""


class ChatExternalApiSceneBindingBase(BaseModel):
    scene_key: str
    scene_label: str
    scene_description: str = ""
    sort_order: int = 100
    api_config_id: int | None = None
    backup_api_config_id: int | None = None
    display_name: str = ""
    subtitle: str = ""
    credit_cost: int = 0
    system_prompt: str = ""
    context_message_limit: int = 10
    opening_greeting: str = ""
    starter_prompts: list[ChatStarterPromptItem] = Field(default_factory=list)
    status: StatusType = "enabled"

    @field_validator("scene_key")
    @classmethod
    def validate_scene_key(cls, value: str) -> str:
        cleaned = (value or "").strip().lower().replace(" ", "_")
        if not cleaned:
            raise ValueError("场景标识不能为空")
        return cleaned

    @field_validator("scene_label")
    @classmethod
    def validate_scene_label(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("场景名称不能为空")
        return cleaned

    @field_validator("scene_description", "display_name", "subtitle", "system_prompt", "opening_greeting")
    @classmethod
    def validate_scene_text(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("sort_order", "credit_cost")
    @classmethod
    def validate_non_negative_numbers(cls, value: int) -> int:
        if int(value) < 0:
            raise ValueError("数值不能小于 0")
        return int(value)

    @field_validator("context_message_limit")
    @classmethod
    def validate_context_message_limit(cls, value: int) -> int:
        normalized = int(value)
        if normalized < 2:
            raise ValueError("上下文条数至少为 2")
        if normalized > 200:
            raise ValueError("上下文条数不能超过 200")
        return normalized

    @field_validator("starter_prompts")
    @classmethod
    def validate_starter_prompts(cls, value: list[ChatStarterPromptItem] | None) -> list[ChatStarterPromptItem]:
        return _normalize_starter_prompts(value)


class ChatExternalApiSceneBindingCreate(ChatExternalApiSceneBindingBase):
    pass


class ChatExternalApiSceneBindingUpdate(BaseModel):
    api_config_id: int | None = None
    backup_api_config_id: int | None = None
    display_name: str = ""
    subtitle: str = ""
    credit_cost: int = 0
    status: StatusType = "enabled"

    @field_validator("display_name", "subtitle")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("credit_cost")
    @classmethod
    def validate_credit_cost(cls, value: int) -> int:
        if int(value) < 0:
            raise ValueError("积分不能小于 0")
        return int(value)


class ChatExternalApiSceneBindingMetaUpdate(BaseModel):
    scene_key: str | None = None
    scene_label: str
    scene_description: str = ""
    sort_order: int = 100
    credit_cost: int = 0
    system_prompt: str = ""
    context_message_limit: int = 10
    opening_greeting: str = ""
    starter_prompts: list[ChatStarterPromptItem] = Field(default_factory=list)

    @field_validator("scene_key")
    @classmethod
    def validate_scene_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = (value or "").strip().lower().replace(" ", "_")
        if not cleaned:
            raise ValueError("场景标识不能为空")
        return cleaned

    @field_validator("scene_label")
    @classmethod
    def validate_scene_label(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("场景名称不能为空")
        return cleaned

    @field_validator("scene_description", "system_prompt", "opening_greeting")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("sort_order", "credit_cost")
    @classmethod
    def validate_non_negative(cls, value: int) -> int:
        if int(value) < 0:
            raise ValueError("数值不能小于 0")
        return int(value)

    @field_validator("context_message_limit")
    @classmethod
    def validate_context_message_limit(cls, value: int) -> int:
        normalized = int(value)
        if normalized < 2:
            raise ValueError("上下文条数至少为 2")
        if normalized > 200:
            raise ValueError("上下文条数不能超过 200")
        return normalized

    @field_validator("starter_prompts")
    @classmethod
    def validate_starter_prompts(cls, value: list[ChatStarterPromptItem] | None) -> list[ChatStarterPromptItem]:
        return _normalize_starter_prompts(value)


class ChatExternalApiSceneBindingStatusUpdate(BaseModel):
    status: StatusType


class ChatExternalApiSceneBindingOut(BaseModel):
    scene_key: str
    scene_label: str
    scene_description: str = ""
    display_name: str = ""
    subtitle: str = ""
    sort_order: int = 0
    status: StatusType = "enabled"
    api_config_id: int | None = None
    api_config_name: str = ""
    api_group_name: str = ""
    api_status: StatusType | None = None
    backup_api_config_id: int | None = None
    backup_api_config_name: str = ""
    backup_api_group_name: str = ""
    backup_api_status: StatusType | None = None
    credit_cost: int = 0
    system_prompt: str = ""
    context_message_limit: int = 10
    opening_greeting: str = ""
    starter_prompts: list[ChatStarterPromptItem] = Field(default_factory=list)


class ChatGenerationModelOptionOut(BaseModel):
    model_key: str
    model_label: str
    model_description: str = ""
    display_name: str = ""
    subtitle: str = ""
    sort_order: int = 0
    credit_cost: int = 0
    opening_greeting: str = ""
    starter_prompts: list[ChatStarterPromptItem] = Field(default_factory=list)
    stream: bool = False
