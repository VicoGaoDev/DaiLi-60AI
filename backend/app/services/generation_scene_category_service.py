import json
import logging
from typing import TypedDict

from fastapi import HTTPException, status
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.models.external_api_scene_binding import ExternalApiSceneBinding
from app.models.generation_scene_category import GenerationSceneCategory

logger = logging.getLogger(__name__)

ALLOWED_SCENE_TYPES = {"generate", "image_edit"}
SCENE_TYPE_LABELS = {
    "generate": "文生图",
    "image_edit": "图编辑",
}


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


def _normalize_name(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分类名称不能为空")
    if len(normalized) > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分类名称不能超过 100 个字符")
    return normalized


def _normalize_description(value: str | None) -> str:
    normalized = (value or "").strip()
    if len(normalized) > 255:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分类描述不能超过 255 个字符")
    return normalized


def _normalize_status(value: str | None) -> str:
    normalized = (value or "enabled").strip().lower() or "enabled"
    if normalized not in {"enabled", "disabled"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分类状态不支持")
    return normalized


def _normalize_scene_type(value: str | None) -> str:
    normalized = (value or "generate").strip() or "generate"
    if normalized not in ALLOWED_SCENE_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分类类型仅支持文生图或图编辑")
    return normalized


def _serialize_category(item: GenerationSceneCategory) -> dict:
    return {
        "id": int(item.id),
        "name": (item.name or "").strip(),
        "description": (item.description or "").strip(),
        "scene_type": _normalize_scene_type(getattr(item, "scene_type", None)),
        "scene_keys": parse_scene_keys(item.scene_keys_json),
        "sort_order": int(item.sort_order or 0),
        "status": _normalize_status(item.status),
        "is_deleted": bool(item.is_deleted),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _get_category_or_404(db: Session, category_id: int) -> GenerationSceneCategory:
    item = db.query(GenerationSceneCategory).filter(GenerationSceneCategory.id == category_id).first()
    if not item or bool(item.is_deleted):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="生图场景分类不存在")
    return item


def _ensure_name_unique(db: Session, name: str, scene_type: str, exclude_id: int | None = None) -> None:
    query = db.query(GenerationSceneCategory).filter(
        GenerationSceneCategory.name == name,
        GenerationSceneCategory.scene_type == scene_type,
        GenerationSceneCategory.is_deleted.is_(False),
    )
    if exclude_id is not None:
        query = query.filter(GenerationSceneCategory.id != exclude_id)
    if query.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该类型下分类名称已存在")


def _validate_scene_keys(
    db: Session,
    scene_keys: list[str],
    *,
    scene_type: str,
    exclude_id: int | None = None,
) -> list[str]:
    cleaned = parse_scene_keys(json.dumps(scene_keys))
    if not cleaned:
        return []

    bindings = (
        db.query(ExternalApiSceneBinding)
        .filter(
            ExternalApiSceneBinding.scene_key.in_(cleaned),
            ExternalApiSceneBinding.is_deleted.is_(False),
        )
        .all()
    )
    binding_map = {item.scene_key: item for item in bindings}
    missing = [key for key in cleaned if key not in binding_map]
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"场景不存在：{', '.join(missing)}")

    type_label = SCENE_TYPE_LABELS.get(scene_type, scene_type)
    mismatched = [
        key for key in cleaned
        if (binding_map[key].scene_type or "") != scene_type
    ]
    if mismatched:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{type_label}分类只能选择{type_label}场景：{', '.join(mismatched)}",
        )

    others = (
        db.query(GenerationSceneCategory)
        .filter(GenerationSceneCategory.is_deleted.is_(False))
        .all()
    )
    occupied: dict[str, str] = {}
    for category in others:
        if exclude_id is not None and int(category.id) == exclude_id:
            continue
        for key in parse_scene_keys(category.scene_keys_json):
            occupied[key] = (category.name or "").strip() or f"分类 {category.id}"
    conflicts = [key for key in cleaned if key in occupied]
    if conflicts:
        details = "、".join(f"{key}（已属于 {occupied[key]}）" for key in conflicts)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"一个场景最多属于一个分类：{details}")
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


def list_admin_generation_scene_categories(db: Session) -> list[dict]:
    rows = (
        db.query(GenerationSceneCategory)
        .filter(GenerationSceneCategory.is_deleted.is_(False))
        .order_by(GenerationSceneCategory.sort_order.asc(), GenerationSceneCategory.id.asc())
        .all()
    )
    return [_serialize_category(item) for item in rows]


def create_generation_scene_category(
    db: Session,
    *,
    name: str,
    description: str,
    scene_type: str,
    scene_keys: list[str],
    sort_order: int,
    status_value: str,
) -> dict:
    normalized_name = _normalize_name(name)
    normalized_scene_type = _normalize_scene_type(scene_type)
    _ensure_name_unique(db, normalized_name, normalized_scene_type)
    item = GenerationSceneCategory(
        name=normalized_name,
        description=_normalize_description(description),
        scene_type=normalized_scene_type,
        scene_keys_json=json.dumps(
            _validate_scene_keys(db, scene_keys, scene_type=normalized_scene_type),
            ensure_ascii=False,
        ),
        sort_order=int(sort_order or 0),
        status=_normalize_status(status_value),
        is_deleted=False,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize_category(item)


def update_generation_scene_category(
    db: Session,
    *,
    category_id: int,
    name: str,
    description: str,
    scene_type: str,
    scene_keys: list[str],
    sort_order: int,
    status_value: str,
) -> dict:
    item = _get_category_or_404(db, category_id)
    normalized_name = _normalize_name(name)
    normalized_scene_type = _normalize_scene_type(scene_type)
    _ensure_name_unique(db, normalized_name, normalized_scene_type, exclude_id=item.id)
    item.name = normalized_name
    item.description = _normalize_description(description)
    item.scene_type = normalized_scene_type
    item.scene_keys_json = json.dumps(
        _validate_scene_keys(db, scene_keys, scene_type=normalized_scene_type, exclude_id=item.id),
        ensure_ascii=False,
    )
    item.sort_order = int(sort_order or 0)
    item.status = _normalize_status(status_value)
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize_category(item)


def update_generation_scene_category_status(db: Session, *, category_id: int, status_value: str) -> dict:
    item = _get_category_or_404(db, category_id)
    item.status = _normalize_status(status_value)
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize_category(item)


def delete_generation_scene_category(db: Session, *, category_id: int) -> None:
    item = _get_category_or_404(db, category_id)
    item.is_deleted = True
    item.status = "disabled"
    db.add(item)
    db.commit()
