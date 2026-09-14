from datetime import datetime
from pydantic import BaseModel, Field


class TemplateTagOut(BaseModel):
    id: int
    name: str
    template_count: int = 0

    model_config = {"from_attributes": True}


class TemplateTagPayload(BaseModel):
    name: str


class TemplateBase(BaseModel):
    prompt: str
    model: str = "banana_pro"
    reference_images: list[str] = []
    size: str = "1:1"
    resolution: str = "2K"
    custom_size: str = ""
    num_images: int = Field(default=1, ge=1, le=6)
    result_image: str = ""
    sort_order: int = 0
    tag_names: list[str] = []


class TemplateCreate(TemplateBase):
    pass


class TemplateUpdate(TemplateBase):
    pass


class TemplateListItemOut(BaseModel):
    id: int
    prompt: str
    model: str = ""
    result_image: str
    result_image_thumb: str = ""
    sort_order: int = 0
    size: str
    resolution: str
    custom_size: str = ""
    num_images: int
    tags: list[TemplateTagOut]
    created_at: datetime | None = None


class TemplateListResponse(BaseModel):
    total: int
    items: list[TemplateListItemOut]


class TemplateDetailOut(BaseModel):
    id: int
    prompt: str
    model: str = ""
    reference_images: list[str] = []
    reference_image_thumbs: list[str] = []
    sort_order: int = 0
    size: str
    resolution: str
    custom_size: str = ""
    num_images: int
    result_image: str
    result_image_thumb: str = ""
    tags: list[TemplateTagOut]
    created_at: datetime | None = None
