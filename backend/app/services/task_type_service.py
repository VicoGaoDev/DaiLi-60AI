from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.external_api_scene_binding import ExternalApiSceneBinding
from app.models.task import Task
from app.services.external_api_config_service import SCENE_INPAINT, SCENE_SMART_CUTOUT
from app.services.prompt_optimize_service import PROMPT_OPTIMIZE_MODE
from app.services.prompt_reverse_service import PROMPT_REVERSE_MODE

TASK_TYPE_TEXT_GENERATE = "text_generate"
TASK_TYPE_IMAGE_EDIT = "image_edit"
TASK_TYPE_INPAINT = "inpaint"
TASK_TYPE_SMART_CUTOUT = "smart_cutout"
TASK_TYPE_PROMPT_REVERSE = PROMPT_REVERSE_MODE
TASK_TYPE_PROMPT_OPTIMIZE = PROMPT_OPTIMIZE_MODE


def list_task_type_values() -> tuple[str, str, str, str, str, str]:
    return (
        TASK_TYPE_TEXT_GENERATE,
        TASK_TYPE_IMAGE_EDIT,
        TASK_TYPE_INPAINT,
        TASK_TYPE_SMART_CUTOUT,
        TASK_TYPE_PROMPT_REVERSE,
        TASK_TYPE_PROMPT_OPTIMIZE,
    )


def _query_scene_type_pairs(
    db: Session,
    *,
    enabled_only: bool = False,
    scene_keys: set[str] | None = None,
) -> list[tuple[str, str]]:
    query = db.query(
        ExternalApiSceneBinding.scene_key,
        ExternalApiSceneBinding.scene_type,
    ).filter(ExternalApiSceneBinding.is_deleted.is_(False))
    if enabled_only:
        query = query.filter(ExternalApiSceneBinding.status == "enabled")
    if scene_keys is not None:
        normalized_keys = {key.strip() for key in scene_keys if key and key.strip()}
        if not normalized_keys:
            return []
        query = query.filter(ExternalApiSceneBinding.scene_key.in_(normalized_keys))
    return [(scene_key or "", scene_type or "") for scene_key, scene_type in query.all()]


def get_task_scene_type_map(db: Session, *, enabled_only: bool = False) -> dict[str, str]:
    return {
        scene_key.strip(): scene_type.strip()
        for scene_key, scene_type in _query_scene_type_pairs(db, enabled_only=enabled_only)
        if scene_key.strip()
    }


def get_task_scene_type_subset(
    db: Session,
    scene_keys: set[str],
    *,
    enabled_only: bool = False,
) -> dict[str, str]:
    return {
        scene_key.strip(): scene_type.strip()
        for scene_key, scene_type in _query_scene_type_pairs(
            db,
            enabled_only=enabled_only,
            scene_keys=scene_keys,
        )
        if scene_key.strip()
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
    if normalized_mode == PROMPT_OPTIMIZE_MODE:
        return TASK_TYPE_PROMPT_OPTIMIZE
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
