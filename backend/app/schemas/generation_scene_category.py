from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


StatusType = Literal["enabled", "disabled"]
SceneType = Literal["generate", "image_edit"]


class GenerationSceneCategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=255)
    scene_type: SceneType = "generate"
    scene_keys: list[str] = Field(default_factory=list)
    sort_order: int = Field(default=100, ge=0, le=999999)
    status: StatusType = "enabled"

    @field_validator("name", "description")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("scene_type")
    @classmethod
    def validate_scene_type(cls, value: str) -> str:
        normalized = (value or "generate").strip() or "generate"
        if normalized not in {"generate", "image_edit"}:
            raise ValueError("分类类型仅支持文生图或图编辑")
        return normalized

    @field_validator("scene_keys")
    @classmethod
    def validate_scene_keys(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value or []:
            key = str(item or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            cleaned.append(key)
        return cleaned


class GenerationSceneCategoryCreate(GenerationSceneCategoryBase):
    pass


class GenerationSceneCategoryUpdate(GenerationSceneCategoryBase):
    pass


class GenerationSceneCategoryStatusUpdate(BaseModel):
    status: StatusType


class GenerationSceneCategoryOut(BaseModel):
    id: int
    name: str
    description: str = ""
    scene_type: SceneType = "generate"
    scene_keys: list[str] = []
    sort_order: int
    status: StatusType
    is_deleted: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
