import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.external_api_config import (
    _validate_integer_list_json,
    _validate_json_text,
    _validate_resolution_credit_costs_json,
    _validate_scene_options_json,
    _validate_string_list_json,
)


StatusType = Literal["enabled", "disabled"]
RequestFormatType = Literal["json", "multipart"]
CallModeType = Literal["async"]
HttpMethodType = Literal["GET", "POST"]
VideoCreditBillingModeType = Literal["fixed", "per_second"]
VideoSceneAvailabilityModeType = Literal["text_to_video", "image_to_video", "both"]
VideoGenerationModeType = Literal["text_to_video", "image_to_video", "first_last_frame"]


def _validate_resolution_mapping_json(value: str, field_name: str) -> str:
    raw = (value or "").strip() or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} 必须是合法 JSON: {exc.msg}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"{field_name} 必须是 JSON 对象")

    normalized: dict[str, str] = {}
    for resolution, mapped_value in parsed.items():
        resolution_key = str(resolution or "").strip()
        normalized_value = str(mapped_value or "").strip()
        if not resolution_key or not normalized_value:
            raise ValueError(f"{field_name} 的键和值不能为空")
        normalized[resolution_key] = normalized_value
    return json.dumps(normalized, ensure_ascii=False, indent=2)


class VideoExternalApiConfigBase(BaseModel):
    name: str
    description: str = ""
    group_name: str = "默认"
    request_url: str
    request_format: RequestFormatType = "json"
    headers_json: str = "{}"
    payload_json: str = "{}"
    response_json: str = "{}"
    result_video_url_field: str = ""
    result_video_base64_field: str = ""
    result_cover_url_field: str = ""
    call_mode: CallModeType = "async"
    submit_success_statuses_json: str = "[200, 201, 202]"
    poll_url: str = ""
    poll_method: HttpMethodType = "GET"
    poll_headers_json: str = "{}"
    poll_payload_json: str = "{}"
    task_id_field: str = ""
    result_status_field: str = ""
    result_success_values_json: str = '["success", "succeeded", "completed"]'
    result_failed_values_json: str = '["failed", "error", "cancelled"]'
    result_error_field: str = ""
    poll_result_video_url_field: str = ""
    poll_result_video_base64_field: str = ""
    poll_result_cover_url_field: str = ""
    poll_interval_seconds: int = 5
    poll_timeout_seconds: int = 600
    status: StatusType = "enabled"

    @field_validator("name", "request_url")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("字段不能为空")
        return cleaned

    @field_validator("description", "group_name")
    @classmethod
    def validate_optional_text(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("headers_json", "poll_headers_json")
    @classmethod
    def validate_headers_json(cls, value: str) -> str:
        return _validate_json_text(value, "Header JSON", expect_object=True)

    @field_validator("payload_json", "response_json", "poll_payload_json")
    @classmethod
    def validate_payload_json(cls, value: str) -> str:
        return _validate_json_text(value, "请求 JSON", expect_object=False)

    @field_validator(
        "result_video_url_field",
        "result_video_base64_field",
        "result_cover_url_field",
        "poll_url",
        "task_id_field",
        "result_status_field",
        "result_error_field",
        "poll_result_video_url_field",
        "poll_result_video_base64_field",
        "poll_result_cover_url_field",
    )
    @classmethod
    def validate_path_fields(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("submit_success_statuses_json")
    @classmethod
    def validate_status_codes_json(cls, value: str) -> str:
        return _validate_integer_list_json(value, "提交成功状态码 JSON")

    @field_validator("result_success_values_json")
    @classmethod
    def validate_result_success_values_json(cls, value: str) -> str:
        return _validate_string_list_json(value, "成功状态值 JSON")

    @field_validator("result_failed_values_json")
    @classmethod
    def validate_result_failed_values_json(cls, value: str) -> str:
        return _validate_string_list_json(value, "失败状态值 JSON")

    @field_validator("poll_interval_seconds")
    @classmethod
    def validate_poll_interval_seconds(cls, value: int) -> int:
        if int(value) <= 0:
            raise ValueError("轮询间隔必须大于 0 秒")
        return int(value)

    @field_validator("poll_timeout_seconds")
    @classmethod
    def validate_poll_timeout_seconds(cls, value: int) -> int:
        if int(value) <= 0:
            raise ValueError("轮询超时必须大于 0 秒")
        return int(value)

    @model_validator(mode="after")
    def validate_async_fields(self):
        if not self.poll_url.strip():
            raise ValueError("异步接口必须填写轮询地址")
        if not self.task_id_field.strip():
            raise ValueError("异步接口必须填写第三方任务 ID 字段路径")
        if not self.result_status_field.strip():
            raise ValueError("异步接口必须填写结果状态字段路径")
        if not self.poll_result_video_url_field.strip():
            raise ValueError("异步接口必须填写轮询结果视频 URL 路径")
        return self


class VideoExternalApiConfigCreate(VideoExternalApiConfigBase):
    pass


class VideoExternalApiConfigUpdate(VideoExternalApiConfigBase):
    pass


class VideoExternalApiConfigStatusUpdate(BaseModel):
    status: StatusType


class VideoExternalApiConfigOut(VideoExternalApiConfigBase):
    id: int
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class VideoExternalApiConfigTestResult(BaseModel):
    success: bool
    request_url: str
    status_code: int | None = None
    response_preview: str


class VideoExternalApiSceneBindingBase(BaseModel):
    scene_key: str
    scene_label: str
    scene_description: str = ""
    sort_order: int = 100
    hide_aspect_ratio: bool = False
    hide_duration: bool = False
    hide_resolution: bool = False
    api_config_id: int | None = None
    backup_api_config_id: int | None = None
    display_name: str = ""
    subtitle: str = ""
    availability_mode: VideoSceneAvailabilityModeType = "both"
    availability_modes: list[VideoGenerationModeType] = Field(default_factory=lambda: ["text_to_video", "image_to_video"])
    max_reference_images: int = 1
    credit_billing_mode: VideoCreditBillingModeType = "fixed"
    credit_cost: int = 0
    per_second_credit_cost: int = 0
    aspect_ratio_options_json: str = "[]"
    duration_options_json: str = "[]"
    resolution_options_json: str = "[]"
    resolution_mapping_json: str = "{}"
    resolution_credit_costs_json: str = "{}"
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

    @field_validator("scene_description", "display_name", "subtitle")
    @classmethod
    def validate_scene_text(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("sort_order", "credit_cost", "per_second_credit_cost", "max_reference_images")
    @classmethod
    def validate_non_negative_numbers(cls, value: int) -> int:
        if int(value) < 0:
            raise ValueError("数值不能小于 0")
        return int(value)

    @field_validator("availability_modes")
    @classmethod
    def validate_availability_modes(cls, value: list[VideoGenerationModeType]) -> list[VideoGenerationModeType]:
        normalized: list[VideoGenerationModeType] = []
        for item in value or []:
            if item not in normalized:
                normalized.append(item)
        if not normalized:
            raise ValueError("可用范围至少选择一项")
        return normalized

    @field_validator("aspect_ratio_options_json")
    @classmethod
    def validate_aspect_ratio_options_json(cls, value: str) -> str:
        return _validate_scene_options_json(value, "宽高比选项 JSON")

    @field_validator("duration_options_json")
    @classmethod
    def validate_duration_options_json(cls, value: str) -> str:
        return _validate_scene_options_json(value, "秒数选项 JSON")

    @field_validator("resolution_options_json")
    @classmethod
    def validate_resolution_options_json(cls, value: str) -> str:
        return _validate_scene_options_json(value, "分辨率选项 JSON")

    @field_validator("resolution_mapping_json")
    @classmethod
    def validate_resolution_mapping_json(cls, value: str) -> str:
        return _validate_resolution_mapping_json(value, "分辨率映射 JSON")

    @field_validator("resolution_credit_costs_json")
    @classmethod
    def validate_resolution_credit_costs_json(cls, value: str) -> str:
        return _validate_resolution_credit_costs_json(value, "分辨率积分 JSON")


class VideoExternalApiSceneBindingCreate(VideoExternalApiSceneBindingBase):
    pass


class VideoExternalApiSceneBindingUpdate(BaseModel):
    api_config_id: int | None = None
    backup_api_config_id: int | None = None
    display_name: str = ""
    subtitle: str = ""
    credit_billing_mode: VideoCreditBillingModeType = "fixed"
    credit_cost: int = 0
    per_second_credit_cost: int = 0
    status: StatusType = "enabled"

    @field_validator("credit_cost", "per_second_credit_cost")
    @classmethod
    def validate_update_non_negative_numbers(cls, value: int) -> int:
        if int(value) < 0:
            raise ValueError("数值不能小于 0")
        return int(value)


class VideoExternalApiSceneBindingMetaUpdate(BaseModel):
    scene_key: str = ""
    scene_label: str
    scene_description: str = ""
    sort_order: int = 100
    hide_aspect_ratio: bool = False
    hide_duration: bool = False
    hide_resolution: bool = False
    availability_mode: VideoSceneAvailabilityModeType = "both"
    availability_modes: list[VideoGenerationModeType] = Field(default_factory=lambda: ["text_to_video", "image_to_video"])
    max_reference_images: int = 1
    credit_billing_mode: VideoCreditBillingModeType = "fixed"
    credit_cost: int = 0
    per_second_credit_cost: int = 0
    aspect_ratio_options_json: str = "[]"
    duration_options_json: str = "[]"
    resolution_options_json: str = "[]"
    resolution_mapping_json: str = "{}"
    resolution_credit_costs_json: str = "{}"

    @field_validator("scene_key", "scene_label", "scene_description")
    @classmethod
    def validate_meta_text(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("sort_order", "credit_cost", "per_second_credit_cost", "max_reference_images")
    @classmethod
    def validate_meta_non_negative_numbers(cls, value: int) -> int:
        if int(value) < 0:
            raise ValueError("数值不能小于 0")
        return int(value)

    @field_validator("availability_modes")
    @classmethod
    def validate_meta_availability_modes(cls, value: list[VideoGenerationModeType]) -> list[VideoGenerationModeType]:
        normalized: list[VideoGenerationModeType] = []
        for item in value or []:
            if item not in normalized:
                normalized.append(item)
        if not normalized:
            raise ValueError("可用范围至少选择一项")
        return normalized

    @field_validator("aspect_ratio_options_json")
    @classmethod
    def validate_meta_aspect_ratio_options_json(cls, value: str) -> str:
        return _validate_scene_options_json(value, "宽高比选项 JSON")

    @field_validator("duration_options_json")
    @classmethod
    def validate_meta_duration_options_json(cls, value: str) -> str:
        return _validate_scene_options_json(value, "秒数选项 JSON")

    @field_validator("resolution_options_json")
    @classmethod
    def validate_meta_resolution_options_json(cls, value: str) -> str:
        return _validate_scene_options_json(value, "分辨率选项 JSON")

    @field_validator("resolution_mapping_json")
    @classmethod
    def validate_meta_resolution_mapping_json(cls, value: str) -> str:
        return _validate_resolution_mapping_json(value, "分辨率映射 JSON")

    @field_validator("resolution_credit_costs_json")
    @classmethod
    def validate_meta_resolution_credit_costs_json(cls, value: str) -> str:
        return _validate_resolution_credit_costs_json(value, "分辨率积分 JSON")


class VideoExternalApiSceneBindingStatusUpdate(BaseModel):
    status: StatusType


class VideoExternalApiSceneBindingOut(BaseModel):
    scene_key: str
    scene_label: str
    scene_description: str
    display_name: str
    subtitle: str
    sort_order: int
    hide_aspect_ratio: bool
    hide_duration: bool
    hide_resolution: bool
    availability_mode: VideoSceneAvailabilityModeType
    availability_modes: list[VideoGenerationModeType]
    max_reference_images: int
    status: StatusType
    is_builtin: bool = False
    api_config_id: int | None = None
    api_config_name: str = ""
    api_group_name: str = ""
    api_status: StatusType | None = None
    backup_api_config_id: int | None = None
    backup_api_config_name: str = ""
    backup_api_group_name: str = ""
    backup_api_status: StatusType | None = None
    credit_billing_mode: VideoCreditBillingModeType
    credit_cost: int
    per_second_credit_cost: int
    aspect_ratio_options_json: str
    duration_options_json: str
    resolution_options_json: str
    resolution_mapping_json: str
    resolution_credit_costs_json: str


class VideoGenerationModelOptionOut(BaseModel):
    model_key: str
    model_label: str
    model_description: str
    display_name: str
    subtitle: str
    sort_order: int
    hide_aspect_ratio: bool
    hide_duration: bool
    hide_resolution: bool
    availability_mode: VideoSceneAvailabilityModeType
    availability_modes: list[VideoGenerationModeType]
    max_reference_images: int
    credit_billing_mode: VideoCreditBillingModeType
    credit_cost: int
    per_second_credit_cost: int
    aspect_ratio_options: list[dict[str, str]]
    resolution_credit_costs: dict[str, int]
    duration_options: list[dict[str, str]]
    resolution_options: list[dict[str, str]]


class VideoTaskSceneConfigOut(BaseModel):
    scene_key: str
    scene_label: str
    scene_description: str
    display_name: str
    subtitle: str
    sort_order: int
    hide_aspect_ratio: bool
    hide_duration: bool
    hide_resolution: bool
    availability_mode: VideoSceneAvailabilityModeType
    availability_modes: list[VideoGenerationModeType]
    max_reference_images: int
    credit_billing_mode: VideoCreditBillingModeType
    credit_cost: int
    per_second_credit_cost: int
    aspect_ratio_options: list[dict[str, str]]
    resolution_credit_costs: dict[str, int]
    duration_options: list[dict[str, str]]
    resolution_options: list[dict[str, str]]
