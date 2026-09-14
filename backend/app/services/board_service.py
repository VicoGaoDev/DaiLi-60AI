from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.image import Image
from app.models.task import Task
from app.models.user_board import UserBoard

DEFAULT_BOARD_NAME = "默认看板"
DEFAULT_BOARD_PREVIEW_LIMIT = 3
MAX_BOARD_NAME_LENGTH = 100


def _normalize_board_name(name: str | None, *, fallback: str = "新看板") -> str:
    normalized = (name or "").strip() or fallback
    if len(normalized) > MAX_BOARD_NAME_LENGTH:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"看板名称不能超过 {MAX_BOARD_NAME_LENGTH} 个字符")
    return normalized


def get_user_board_or_404(db: Session, user_id: int, board_id: int) -> UserBoard:
    board = (
        db.query(UserBoard)
        .filter(UserBoard.id == board_id, UserBoard.user_id == user_id)
        .first()
    )
    if not board:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="看板不存在")
    return board


def validate_user_board_id(db: Session, user_id: int, board_id: int | None) -> int | None:
    if board_id is None:
        return None
    get_user_board_or_404(db, user_id, board_id)
    return board_id


def _build_preview_map(db: Session, user_id: int, board_ids: list[int | None]) -> dict[int | None, list[str]]:
    from app.services.image_delivery_service import get_optional_cos_config, serialize_image

    cos_config = get_optional_cos_config(db)
    wanted_keys = set(board_ids)
    preview_map: dict[int | None, list[str]] = {key: [] for key in wanted_keys}
    # Fetch a bounded recent window and group in Python to keep the board list query simple.
    recent_images = (
        db.query(Image)
        .join(Task, Image.task_id == Task.id)
        .options(joinedload(Image.task))
        .filter(
            Task.user_id == user_id,
            Task.is_deleted.is_(False),
            Task.canvas_id.is_(None),
            Image.is_deleted.is_(False),
            Image.status == "success",
            or_(Image.image_url != "", Image.preview_url != ""),
        )
        .order_by(Task.created_at.desc(), Image.id.desc())
        .limit(max(60, len(wanted_keys) * DEFAULT_BOARD_PREVIEW_LIMIT * 4))
        .all()
    )
    for image in recent_images:
        board_key = image.task.board_id if image.task else None
        if board_key not in wanted_keys:
            continue
        previews = preview_map.setdefault(board_key, [])
        if len(previews) >= DEFAULT_BOARD_PREVIEW_LIMIT:
            continue
        image_payload = serialize_image(image, cos_config=cos_config)
        preview_url = image_payload.get("thumb_url") or image_payload.get("preview_url") or image_payload.get("image_url") or ""
        if preview_url:
            previews.append(preview_url)
    return preview_map


def list_user_boards(
    db: Session,
    user_id: int,
    *,
    include_stats: bool = True,
    include_previews: bool = True,
) -> dict:
    boards = (
        db.query(UserBoard)
        .filter(UserBoard.user_id == user_id)
        .order_by(UserBoard.updated_at.desc(), UserBoard.id.desc())
        .all()
    )
    stat_map: dict[int | None, tuple[int, datetime | None]] = {}
    if include_stats:
        stat_rows = (
            db.query(
                Task.board_id,
                func.count(Image.id).label("asset_count"),
                func.max(Task.created_at).label("latest_task_at"),
            )
            .join(Image, Image.task_id == Task.id)
            .filter(
                Task.user_id == user_id,
                Task.is_deleted.is_(False),
                Task.canvas_id.is_(None),
                Image.is_deleted.is_(False),
            )
            .group_by(Task.board_id)
            .all()
        )
        stat_map = {
            row.board_id: (int(row.asset_count or 0), row.latest_task_at)
            for row in stat_rows
        }
    board_keys: list[int | None] = [None, *[board.id for board in boards]]
    preview_map = _build_preview_map(db, user_id, board_keys) if include_previews else {}

    default_count, default_updated_at = stat_map.get(None, (0, None))
    items = [{
        "id": None,
        "name": DEFAULT_BOARD_NAME,
        "is_default": True,
        "asset_count": default_count,
        "updated_at": default_updated_at,
        "preview_urls": preview_map.get(None, []),
    }]

    for board in boards:
        asset_count, latest_task_at = stat_map.get(board.id, (0, None))
        items.append({
            "id": board.id,
            "name": board.name or "未命名看板",
            "is_default": False,
            "asset_count": asset_count,
            "updated_at": latest_task_at or board.updated_at,
            "preview_urls": preview_map.get(board.id, []),
        })
    return {"items": items}


def create_user_board(db: Session, user_id: int, name: str | None = None) -> dict:
    board = UserBoard(user_id=user_id, name=_normalize_board_name(name))
    db.add(board)
    db.commit()
    db.refresh(board)
    return {
        "id": board.id,
        "name": board.name,
        "is_default": False,
        "asset_count": 0,
        "updated_at": board.updated_at,
        "preview_urls": [],
    }


def update_user_board(db: Session, user_id: int, board_id: int, name: str) -> dict:
    board = get_user_board_or_404(db, user_id, board_id)
    board.name = _normalize_board_name(name, fallback=board.name or "未命名看板")
    db.commit()
    db.refresh(board)
    return {
        "id": board.id,
        "name": board.name,
        "is_default": False,
        "asset_count": 0,
        "updated_at": board.updated_at,
        "preview_urls": [],
    }


def delete_user_board(db: Session, user_id: int, board_id: int) -> None:
    board = get_user_board_or_404(db, user_id, board_id)
    (
        db.query(Task)
        .filter(Task.user_id == user_id, Task.board_id == board.id)
        .update({Task.board_id: None}, synchronize_session=False)
    )
    db.delete(board)
    db.commit()
