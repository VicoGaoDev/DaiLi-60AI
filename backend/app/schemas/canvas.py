from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.task import TaskOut
from app.schemas.video_task import VideoTaskOut


class CanvasCreate(BaseModel):
    name: str = Field(default="", max_length=100)


class CanvasUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    viewport_x: float | None = None
    viewport_y: float | None = None
    zoom: float | None = Field(default=None, ge=0.1, le=3)


class CanvasViewportUpdate(BaseModel):
    viewport_x: float = 0
    viewport_y: float = 0
    zoom: float = Field(default=0.5, ge=0.1, le=3)


class CanvasNodeUpdate(BaseModel):
    x: float | None = None
    y: float | None = None
    width: float | None = Field(default=None, ge=160, le=1200)
    height: float | None = Field(default=None, ge=160, le=1600)
    z_index: int | None = Field(default=None, ge=1)
    content: str | None = Field(default=None, max_length=5000)


class CanvasGroupNodeUpdate(BaseModel):
    id: int
    x: float | None = None
    y: float | None = None
    z_index: int | None = Field(default=None, ge=1)


class CanvasNodeBatchUpdateItem(CanvasNodeUpdate):
    id: int


class CanvasNodeBatchUpdate(BaseModel):
    nodes: list[CanvasNodeBatchUpdateItem] = Field(default_factory=list, max_length=500)


class CanvasFreeNodeCreate(BaseModel):
    node_type: Literal["text", "image"]
    content: str = Field(default="", max_length=5000)
    image_url: str = Field(default="", max_length=1000)
    x: float = 0
    y: float = 0
    width: float = Field(default=320, ge=120, le=1200)
    height: float = Field(default=220, ge=120, le=1600)


class CanvasTaskCreate(BaseModel):
    model: str = ""
    source: Literal["web", "app", "api"] = "web"
    prompt: str
    num_images: int = Field(default=1, ge=1, le=8)
    size: str = "3:4"
    resolution: str = "4K"
    custom_size: str = ""
    mode: Literal["generate", "inpaint"] = "generate"
    reference_images: list[str] | None = None
    source_node_ids: list[int] = Field(default_factory=list, max_length=50)
    source_image: str = ""
    mask_image: str = ""
    x: float = 0
    y: float = 0
    width: float = Field(default=320, ge=160, le=1200)
    height: float = Field(default=420, ge=160, le=1600)


class CanvasVideoTaskCreate(BaseModel):
    model: str = ""
    source: Literal["web", "app", "api"] = "web"
    prompt: str
    duration_seconds: int = Field(default=5, ge=1, le=60)
    aspect_ratio: str = ""
    resolution: str = ""
    reference_images: list[str] = Field(default_factory=list)
    source_node_ids: list[int] = Field(default_factory=list, max_length=50)
    x: float = 0
    y: float = 0
    width: float = Field(default=320, ge=160, le=1200)
    height: float = Field(default=420, ge=160, le=1600)


class CanvasGroupCreate(BaseModel):
    name: str = Field(default="未命名分组", min_length=1, max_length=100)
    color: str = Field(default="#ffab27", max_length=32)
    node_ids: list[int] = Field(default_factory=list, min_length=1, max_length=100)
    nodes: list[CanvasGroupNodeUpdate] = Field(default_factory=list, max_length=100)
    x: float = 0
    y: float = 0
    width: float = Field(default=320, ge=1, le=100000)
    height: float = Field(default=220, ge=1, le=100000)
    z_index: int = Field(default=1, ge=1)


class CanvasGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = Field(default=None, max_length=32)
    x: float | None = None
    y: float | None = None
    width: float | None = Field(default=None, ge=1, le=100000)
    height: float | None = Field(default=None, ge=1, le=100000)
    z_index: int | None = Field(default=None, ge=1)


class CanvasGroupAssignNodesRequest(BaseModel):
    nodes: list[CanvasGroupNodeUpdate] = Field(default_factory=list, min_length=1, max_length=100)


class CanvasSummary(BaseModel):
    id: int
    project_id: str
    name: str
    node_count: int = 0
    preview_urls: list[str] = []
    viewport_x: float = 0
    viewport_y: float = 0
    zoom: float = 0.5
    is_readonly: bool = False
    is_deleted: bool = False
    owner_user_id: str = ""
    owner_username: str = ""
    owner_avatar_url: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CanvasListResponse(BaseModel):
    items: list[CanvasSummary]
    total: int = 0
    page: int = 1
    page_size: int = 0
    has_more: bool = False


class CanvasNodeOut(BaseModel):
    id: int
    canvas_id: int
    group_id: int | None = None
    task_id: str
    video_task_id: str = ""
    node_type: str = "task"
    content: str = ""
    image_url: str = ""
    asset_is_deleted: bool = False
    x: float
    y: float
    width: float
    height: float
    z_index: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    task: TaskOut | None = None
    video_task: VideoTaskOut | None = None


class CanvasEdgeOut(BaseModel):
    id: int
    canvas_id: int
    source_node_id: int
    target_node_id: int
    edge_type: str = "reference"
    source_anchor: str = "auto"
    target_anchor: str = "auto"
    is_collapsed: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CanvasEdgeUpdate(BaseModel):
    is_collapsed: bool | None = None


class CanvasGroupOut(BaseModel):
    id: int
    canvas_id: int
    name: str
    color: str
    x: float
    y: float
    width: float
    height: float
    z_index: int
    node_ids: list[int] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CanvasDetail(CanvasSummary):
    nodes: list[CanvasNodeOut] = []
    edges: list[CanvasEdgeOut] = []
    groups: list[CanvasGroupOut] = []


class CanvasNodeBatchUpdateResponse(BaseModel):
    nodes: list[CanvasNodeOut] = []


class CanvasGroupCreateResponse(BaseModel):
    group: CanvasGroupOut
    nodes: list[CanvasNodeOut] = []


class CanvasGroupAssignNodesResponse(BaseModel):
    group: CanvasGroupOut
    groups: list[CanvasGroupOut] = []
    nodes: list[CanvasNodeOut] = []
    deleted_group_ids: list[int] = []


class CanvasGroupRemoveNodesResponse(BaseModel):
    groups: list[CanvasGroupOut] = []
    nodes: list[CanvasNodeOut] = []
    deleted_group_ids: list[int] = []


class CanvasTaskCreateResponse(BaseModel):
    task_id: str | None = None
    task_ids: list[str] = []
    nodes: list[CanvasNodeOut] = []
