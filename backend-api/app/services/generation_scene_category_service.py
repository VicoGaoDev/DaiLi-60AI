import json
import logging
from typing import TypedDict

from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.models.generation_scene_category import GenerationSceneCategory

logger = logging.getLogger(__name__)


class SceneCategoryInfo(TypedDict):
    id: int
    name: str
    sort_order: int


def parse_scene_keys(raw: str | None) -> list[str]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in data:
        key = str(item or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append(key)
    return cleaned


def build_scene_category_map(db: Session) -> dict[str, SceneCategoryInfo]:
    try:
        rows = (
            db.query(GenerationSceneCategory)
            .filter(
                GenerationSceneCategory.is_deleted.is_(False),
                GenerationSceneCategory.status == "enabled",
            )
            .order_by(GenerationSceneCategory.sort_order.asc(), GenerationSceneCategory.id.asc())
            .all()
        )
    except (ProgrammingError, OperationalError):
        db.rollback()
        logger.warning("generation_scene_categories is unavailable, skip model grouping")
        return {}
    mapping: dict[str, SceneCategoryInfo] = {}
    for item in rows:
        info: SceneCategoryInfo = {
            "id": int(item.id),
            "name": (item.name or "").strip(),
            "sort_order": int(item.sort_order or 0),
        }
        for key in parse_scene_keys(item.scene_keys_json):
            mapping.setdefault(key, info)
    return mapping
