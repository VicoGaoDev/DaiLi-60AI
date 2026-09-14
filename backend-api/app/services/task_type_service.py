from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.external_api_scene_binding import ExternalApiSceneBinding
from app.models.task import Task
from app.services.external_api_config_service import SCENE_INPAINT, SCENE_SMART_CUTOUT
from app.services.prompt_reverse_service import PROMPT_REVERSE_MODE

TASK_TYPE_TEXT_GENERATE = "text_generate"
TASK_TYPE_IMAGE_EDIT = "image_edit"
TASK_TYPE_INPAINT = "inpaint"
TASK_TYPE_SMART_CUTOUT = "smart_cutout"
TASK_TYPE_PROMPT_REVERSE = PROMPT_REVERSE_MODE


def list_task_type_values() -> tuple[str, str, str, str, str]:
    return (
        TASK_TYPE_TEXT_GENERATE,
        TASK_TYPE_IMAGE_EDIT,
        TASK_TYPE_INPAINT,
        TASK_TYPE_SMART_CUTOUT,
        TASK_TYPE_PROMPT_REVERSE,
    )


def get_task_scene_type_map(db: Session, *, enabled_only: bool = False) -> dict[str, str]:
    query = db.query(ExternalApiSceneBinding).filter(ExternalApiSceneBinding.is_deleted.is_(False))
    if enabled_only:
        query = query.filter(ExternalApiSceneBinding.status == "enabled")
    rows = query.all()
    return {
        (row.scene_key or "").strip(): (row.scene_type or "").strip()
        for row in rows
        if (row.scene_key or "").strip()
    }


def resolve_task_type(
    *,
    mode: str | None,
    model: str | None,
    scene_type_map: dict[str, str] | None = None,
) -> str:
    normalized_mode = (mode or "").strip()
    normalized_model = (model or "").strip()
    if normalized_mode == PROMPT_REVERSE_MODE:
        return TASK_TYPE_PROMPT_REVERSE
    if normalized_mode == "inpaint" or normalized_model == SCENE_INPAINT:
        return TASK_TYPE_INPAINT
    if normalized_mode == "smart_cutout" or normalized_model == SCENE_SMART_CUTOUT:
        return TASK_TYPE_SMART_CUTOUT
    scene_type = (scene_type_map or {}).get(normalized_model, "").strip()
    if scene_type == "image_edit":
        return TASK_TYPE_IMAGE_EDIT
    return TASK_TYPE_TEXT_GENERATE


def resolve_task_type_for_task(task: Task, *, scene_type_map: dict[str, str] | None = None) -> str:
    return resolve_task_type(mode=task.mode, model=task.model, scene_type_map=scene_type_map)
