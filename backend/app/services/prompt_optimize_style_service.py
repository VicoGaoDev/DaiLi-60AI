from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.prompt_optimize_style import PromptOptimizeStyle
from app.models.prompt_optimize_task import PromptOptimizeTask

DEFAULT_PROMPT_OPTIMIZE_STYLE_NAME = "通用优化"
DEFAULT_PROMPT_OPTIMIZE_STYLE_DESCRIPTION = "默认风格，适合通用中文生图提示词补全"
DEFAULT_PROMPT_OPTIMIZE_STYLE_PROMPT = (
    "在保留用户原始意图前提下，补全构图、镜头、光线、色彩、材质、氛围和画面细节，"
    "输出适合直接生图的中文提示词。"
)


def _normalize_name(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="风格名称不能为空")
    if len(normalized) > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="风格名称不能超过 100 个字符")
    return normalized


def _normalize_description(value: str | None) -> str:
    normalized = (value or "").strip()
    if len(normalized) > 255:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="风格描述不能超过 255 个字符")
    return normalized


def _normalize_style_prompt(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="风格提示词不能为空")
    if len(normalized) > 10000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="风格提示词不能超过 10000 个字符")
    return normalized


def _normalize_status(value: str | None) -> str:
    normalized = (value or "enabled").strip().lower() or "enabled"
    if normalized not in {"enabled", "disabled"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="风格状态不支持")
    return normalized


def _serialize_style(item: PromptOptimizeStyle, usage_count: int = 0) -> dict:
    return {
        "id": int(item.id),
        "name": (item.name or "").strip(),
        "description": (item.description or "").strip(),
        "style_prompt": (item.style_prompt or "").strip(),
        "sort_order": int(item.sort_order or 0),
        "status": _normalize_status(item.status),
        "is_default": bool(item.is_default),
        "is_deleted": bool(item.is_deleted),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "usage_count": int(usage_count or 0),
    }


def _serialize_public_style(item: PromptOptimizeStyle) -> dict:
    return {
        "id": int(item.id),
        "name": (item.name or "").strip(),
        "description": (item.description or "").strip(),
        "style_prompt": (item.style_prompt or "").strip(),
        "is_default": bool(item.is_default),
        "sort_order": int(item.sort_order or 0),
    }


def _get_style_or_404(db: Session, style_id: int) -> PromptOptimizeStyle:
    item = db.query(PromptOptimizeStyle).filter(PromptOptimizeStyle.id == style_id).first()
    if not item or bool(item.is_deleted):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提示词优化风格不存在")
    return item


def get_active_style_or_404(db: Session, style_id: int) -> PromptOptimizeStyle:
    item = _get_style_or_404(db, style_id)
    if _normalize_status(item.status) != "enabled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="所选提示词优化风格已停用")
    return item


def _ensure_name_unique(db: Session, name: str, exclude_id: int | None = None) -> None:
    query = db.query(PromptOptimizeStyle).filter(
        PromptOptimizeStyle.name == name,
        PromptOptimizeStyle.is_deleted.is_(False),
    )
    if exclude_id is not None:
        query = query.filter(PromptOptimizeStyle.id != exclude_id)
    if query.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="风格名称已存在")


def _set_default_style(db: Session, style_id: int) -> PromptOptimizeStyle:
    item = _get_style_or_404(db, style_id)
    if _normalize_status(item.status) != "enabled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能将启用中的风格设为默认风格")
    (
        db.query(PromptOptimizeStyle)
        .filter(PromptOptimizeStyle.is_deleted.is_(False))
        .update({"is_default": False}, synchronize_session=False)
    )
    item.is_default = True
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def ensure_default_prompt_optimize_style(db: Session) -> None:
    existing = (
        db.query(PromptOptimizeStyle)
        .filter(PromptOptimizeStyle.is_deleted.is_(False))
        .order_by(PromptOptimizeStyle.is_default.desc(), PromptOptimizeStyle.sort_order.asc(), PromptOptimizeStyle.id.asc())
        .all()
    )
    if not existing:
        item = PromptOptimizeStyle(
            name=DEFAULT_PROMPT_OPTIMIZE_STYLE_NAME,
            description=DEFAULT_PROMPT_OPTIMIZE_STYLE_DESCRIPTION,
            style_prompt=DEFAULT_PROMPT_OPTIMIZE_STYLE_PROMPT,
            sort_order=10,
            status="enabled",
            is_default=True,
            is_deleted=False,
        )
        db.add(item)
        db.commit()
        return
    default_exists = any(bool(item.is_default) and _normalize_status(item.status) == "enabled" for item in existing)
    if default_exists:
        return
    for item in existing:
        if _normalize_status(item.status) == "enabled":
            item.is_default = True
            db.add(item)
            db.commit()
            return


def list_admin_prompt_optimize_styles(db: Session) -> list[dict]:
    ensure_default_prompt_optimize_style(db)
    usage_rows = (
        db.query(PromptOptimizeTask.style_id, func.count(PromptOptimizeTask.id))
        .filter(PromptOptimizeTask.style_id.is_not(None))
        .group_by(PromptOptimizeTask.style_id)
        .all()
    )
    usage_map = {int(style_id): int(count or 0) for style_id, count in usage_rows if style_id is not None}
    rows = (
        db.query(PromptOptimizeStyle)
        .filter(PromptOptimizeStyle.is_deleted.is_(False))
        .order_by(PromptOptimizeStyle.is_default.desc(), PromptOptimizeStyle.sort_order.asc(), PromptOptimizeStyle.id.asc())
        .all()
    )
    return [_serialize_style(style, usage_count=usage_map.get(int(style.id), 0)) for style in rows]


def list_public_prompt_optimize_styles(db: Session) -> list[dict]:
    ensure_default_prompt_optimize_style(db)
    rows = (
        db.query(PromptOptimizeStyle)
        .filter(
            PromptOptimizeStyle.is_deleted.is_(False),
            PromptOptimizeStyle.status == "enabled",
        )
        .order_by(PromptOptimizeStyle.is_default.desc(), PromptOptimizeStyle.sort_order.asc(), PromptOptimizeStyle.id.asc())
        .all()
    )
    return [_serialize_public_style(row) for row in rows]


def create_prompt_optimize_style(
    db: Session,
    *,
    name: str,
    description: str,
    style_prompt: str,
    sort_order: int,
    status_value: str,
    is_default: bool,
) -> dict:
    normalized_name = _normalize_name(name)
    _ensure_name_unique(db, normalized_name)
    item = PromptOptimizeStyle(
        name=normalized_name,
        description=_normalize_description(description),
        style_prompt=_normalize_style_prompt(style_prompt),
        sort_order=int(sort_order or 0),
        status=_normalize_status(status_value),
        is_default=bool(is_default),
        is_deleted=False,
    )
    if item.is_default and item.status != "enabled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="停用风格不能设为默认风格")
    db.add(item)
    db.commit()
    db.refresh(item)
    if item.is_default:
        item = _set_default_style(db, item.id)
    else:
        ensure_default_prompt_optimize_style(db)
        db.refresh(item)
    return _serialize_style(item)


def update_prompt_optimize_style(
    db: Session,
    *,
    style_id: int,
    name: str,
    description: str,
    style_prompt: str,
    sort_order: int,
    status_value: str,
    is_default: bool,
) -> dict:
    item = _get_style_or_404(db, style_id)
    normalized_name = _normalize_name(name)
    _ensure_name_unique(db, normalized_name, exclude_id=item.id)
    normalized_status = _normalize_status(status_value)
    if is_default and normalized_status != "enabled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="停用风格不能设为默认风格")
    item.name = normalized_name
    item.description = _normalize_description(description)
    item.style_prompt = _normalize_style_prompt(style_prompt)
    item.sort_order = int(sort_order or 0)
    item.status = normalized_status
    item.is_default = bool(is_default)
    db.add(item)
    db.commit()
    db.refresh(item)
    if item.is_default:
        item = _set_default_style(db, item.id)
    else:
        ensure_default_prompt_optimize_style(db)
        db.refresh(item)
    return _serialize_style(item)


def update_prompt_optimize_style_status(db: Session, *, style_id: int, status_value: str) -> dict:
    item = _get_style_or_404(db, style_id)
    normalized_status = _normalize_status(status_value)
    if item.is_default and normalized_status != "enabled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="默认风格不能直接停用，请先设置其他默认风格")
    item.status = normalized_status
    db.add(item)
    db.commit()
    ensure_default_prompt_optimize_style(db)
    db.refresh(item)
    return _serialize_style(item)


def set_prompt_optimize_style_default(db: Session, *, style_id: int) -> dict:
    item = _set_default_style(db, style_id)
    return _serialize_style(item)


def delete_prompt_optimize_style(db: Session, *, style_id: int) -> None:
    item = _get_style_or_404(db, style_id)
    item.is_deleted = True
    item.is_default = False
    item.status = "disabled"
    db.add(item)
    db.commit()
    ensure_default_prompt_optimize_style(db)
