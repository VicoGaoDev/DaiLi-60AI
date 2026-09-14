import re

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.canvas_edge import CanvasEdge
from app.models.canvas_group import CanvasGroup
from app.models.canvas_node import CanvasNode
from app.models.image import Image
from app.models.task import Task
from app.models.user_asset import UserAsset
from app.models.user import User
from app.models.user_canvas import UserCanvas, generate_canvas_project_id
from app.models.video_result import VideoResult
from app.models.video_task import VideoTask
from app.services.business_id_service import task_external_id, user_external_id
from app.services.image_delivery_service import (
    build_thumb_url,
    get_optional_cos_config,
    normalize_external_image_url,
    resolve_user_avatar_url,
    serialize_task,
)
from app.services.task_service import create_tasks
from app.services.video_task_service import create_video_task as create_video_task_record, serialize_video_task
from app.utils.datetime_utils import now_local

DEFAULT_CANVAS_NAME_PREFIX = "新画布"
MAX_CANVAS_NAME_LENGTH = 100
DEFAULT_CANVAS_ZOOM = 0.5
DEFAULT_NODE_WIDTH = 320
DEFAULT_NODE_HEIGHT = 420
NODE_X_SPACING = 360
DEFAULT_CANVAS_PREVIEW_LIMIT = 3
CANVAS_GROUP_PADDING = 24
CANVAS_GROUP_TITLE_HEIGHT = 40
CANVAS_PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{16}$")
CANVAS_NODE_LOAD_OPTIONS = (
    selectinload(CanvasNode.task).selectinload(Task.images),
    selectinload(CanvasNode.video_task).selectinload(VideoTask.results),
)


def _default_canvas_name() -> str:
    return f"{DEFAULT_CANVAS_NAME_PREFIX}-{now_local().strftime('%y%m%d')}"


def _normalize_canvas_name(name: str | None, *, fallback: str | None = None) -> str:
    normalized = (name or "").strip() or fallback or _default_canvas_name()
    if len(normalized) > MAX_CANVAS_NAME_LENGTH:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"画布名称不能超过 {MAX_CANVAS_NAME_LENGTH} 个字符")
    return normalized


def _normalize_project_id(project_id: str) -> str:
    normalized = (project_id or "").strip()
    if not CANVAS_PROJECT_ID_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="画布不存在")
    return normalized


def _generate_unique_project_id(db: Session) -> str:
    for _ in range(10):
        project_id = generate_canvas_project_id()
        exists = db.query(UserCanvas.id).filter(UserCanvas.project_id == project_id).first()
        if not exists:
            return project_id
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="创建画布失败，请稍后重试")


def _serialize_canvas_summary(
    canvas: UserCanvas,
    node_count: int = 0,
    preview_urls: list[str] | None = None,
    *,
    is_readonly: bool = False,
    cos_config=None,
) -> dict:
    owner = canvas.user
    if cos_config is None:
        db = Session.object_session(canvas)
        cos_config = get_optional_cos_config(db) if db else None
    return {
        "id": canvas.id,
        "project_id": canvas.project_id,
        "name": canvas.name or "未命名画布",
        "node_count": int(node_count or 0),
        "preview_urls": preview_urls or [],
        "viewport_x": float(canvas.viewport_x or 0),
        "viewport_y": float(canvas.viewport_y or 0),
        "zoom": float(canvas.zoom if canvas.zoom is not None else DEFAULT_CANVAS_ZOOM),
        "is_readonly": bool(is_readonly),
        "is_deleted": bool(canvas.is_deleted),
        "owner_user_id": user_external_id(owner),
        "owner_username": owner.username if owner else "",
        "owner_avatar_url": resolve_user_avatar_url(owner, cos_config=cos_config),
        "created_at": canvas.created_at,
        "updated_at": canvas.updated_at,
    }


def _visible_canvas_node_filter(*, user_id: int | None = None):
    free_node_clause = and_(
        CanvasNode.task_id.is_(None),
        CanvasNode.video_task_id.is_(None),
    )
    image_task_clause = and_(
        CanvasNode.task_id.is_not(None),
        Task.is_deleted.is_(False),
    )
    video_task_clause = and_(
        CanvasNode.video_task_id.is_not(None),
        VideoTask.is_deleted.is_(False),
    )
    if user_id is not None:
        image_task_clause = and_(image_task_clause, Task.user_id == user_id)
        video_task_clause = and_(video_task_clause, VideoTask.user_id == user_id)
    return or_(free_node_clause, image_task_clause, video_task_clause)


def _resolve_preview_url(
    raw_image_url: str | None,
    *,
    raw_preview_url: str | None = None,
    cos_config=None,
) -> str:
    image_url = normalize_external_image_url(raw_image_url, cos_config=cos_config)
    preview_url = normalize_external_image_url(raw_preview_url, cos_config=cos_config)
    return build_thumb_url(image_url, preview_url=preview_url, cos_config=cos_config) or preview_url or image_url


def _serialize_node(node: CanvasNode, *, cos_config=None) -> dict:
    task = node.task
    video_task = node.video_task
    return {
        "id": node.id,
        "canvas_id": node.canvas_id,
        "group_id": node.group_id,
        "task_id": task_external_id(task) if task else "",
        "video_task_id": video_task.business_id if video_task else "",
        "node_type": node.node_type or ("task" if task else "text"),
        "content": node.content or "",
        "image_url": node.image_url or "",
        "x": float(node.x or 0),
        "y": float(node.y or 0),
        "width": float(node.width or DEFAULT_NODE_WIDTH),
        "height": float(node.height or DEFAULT_NODE_HEIGHT),
        "z_index": int(node.z_index or 1),
        "asset_is_deleted": False,
        "created_at": node.created_at,
        "updated_at": node.updated_at,
        "task": serialize_task(task, cos_config=cos_config) if task else None,
        "video_task": serialize_video_task(video_task, cos_config=cos_config) if video_task else None,
    }


def _is_user_asset_url(url: str | None) -> bool:
    return bool(url and "user_assets/" in url)


def _build_deleted_user_asset_url_set(
    db: Session,
    owner_user_id: int | None,
    image_urls: list[str] | None,
) -> set[str]:
    if owner_user_id is None or not image_urls:
        return set()
    normalized_urls = {
        (url or "").strip()
        for url in image_urls
        if _is_user_asset_url((url or "").strip())
    }
    if not normalized_urls:
        return set()
    rows = (
        db.query(UserAsset.url, UserAsset.is_deleted)
        .filter(
            UserAsset.user_id == owner_user_id,
            UserAsset.url.in_(list(normalized_urls)),
        )
        .all()
    )
    active_urls = {
        (url or "").strip()
        for url, is_deleted in rows
        if url and not is_deleted
    }
    return {url for url in normalized_urls if url not in active_urls}


def _serialize_nodes(
    db: Session,
    nodes: list[CanvasNode],
    *,
    owner_user_id: int | None,
    cos_config=None,
) -> list[dict]:
    deleted_asset_urls = _build_deleted_user_asset_url_set(
        db,
        owner_user_id,
        [node.image_url for node in nodes if (node.node_type or "") == "image"],
    )
    serialized_nodes: list[dict] = []
    for node in nodes:
        payload = _serialize_node(node, cos_config=cos_config)
        if (node.node_type or "") == "image":
            payload["asset_is_deleted"] = (node.image_url or "").strip() in deleted_asset_urls
        serialized_nodes.append(payload)
    return serialized_nodes


def _serialize_group(group: CanvasGroup, node_ids: list[int] | None = None) -> dict:
    return {
        "id": group.id,
        "canvas_id": group.canvas_id,
        "name": group.name or "未命名分组",
        "color": group.color or "#ffab27",
        "x": float(group.x or 0),
        "y": float(group.y or 0),
        "width": float(group.width or DEFAULT_NODE_WIDTH),
        "height": float(group.height or DEFAULT_NODE_HEIGHT),
        "z_index": int(group.z_index or 1),
        "node_ids": node_ids or [],
        "created_at": group.created_at,
        "updated_at": group.updated_at,
    }


def _delete_empty_groups(db: Session, canvas_id: int, group_ids: list[int] | None) -> set[int]:
    normalized_group_ids = list(dict.fromkeys(int(group_id) for group_id in (group_ids or []) if group_id))
    if not normalized_group_ids:
        return set()

    remaining_group_ids = {
        int(group_id)
        for (group_id,) in db.query(CanvasNode.group_id)
        .filter(
            CanvasNode.canvas_id == canvas_id,
            CanvasNode.group_id.in_(normalized_group_ids),
        )
        .distinct()
        .all()
        if group_id is not None
    }
    empty_group_ids = [group_id for group_id in normalized_group_ids if group_id not in remaining_group_ids]
    if empty_group_ids:
        db.query(CanvasGroup).filter(
            CanvasGroup.canvas_id == canvas_id,
            CanvasGroup.id.in_(empty_group_ids),
        ).delete(synchronize_session=False)
    return set(empty_group_ids)


def _get_group_frame_from_nodes(nodes: list[CanvasNode]) -> dict | None:
    if not nodes:
        return None
    min_x = min(float(node.x or 0) for node in nodes)
    min_y = min(float(node.y or 0) for node in nodes)
    max_x = max(float(node.x or 0) + float(node.width or DEFAULT_NODE_WIDTH) for node in nodes)
    max_y = max(float(node.y or 0) + float(node.height or DEFAULT_NODE_HEIGHT) for node in nodes)
    return {
        "x": round(min_x - CANVAS_GROUP_PADDING),
        "y": round(min_y - CANVAS_GROUP_PADDING - CANVAS_GROUP_TITLE_HEIGHT),
        "width": round(max_x - min_x + CANVAS_GROUP_PADDING * 2),
        "height": round(max_y - min_y + CANVAS_GROUP_PADDING * 2 + CANVAS_GROUP_TITLE_HEIGHT),
    }


def _sync_group_layout(db: Session, canvas_id: int, group_id: int) -> dict | None:
    group = (
        db.query(CanvasGroup)
        .filter(CanvasGroup.id == group_id, CanvasGroup.canvas_id == canvas_id)
        .first()
    )
    if not group:
        return None
    nodes = (
        db.query(CanvasNode)
        .filter(CanvasNode.canvas_id == canvas_id, CanvasNode.group_id == group_id)
        .order_by(CanvasNode.z_index.asc(), CanvasNode.id.asc())
        .all()
    )
    frame = _get_group_frame_from_nodes(nodes)
    if not frame:
        return None
    group.x = frame["x"]
    group.y = frame["y"]
    group.width = frame["width"]
    group.height = frame["height"]
    return _serialize_group(group, [node.id for node in nodes])


def _serialize_edge(edge: CanvasEdge) -> dict:
    return {
        "id": edge.id,
        "canvas_id": edge.canvas_id,
        "source_node_id": edge.source_node_id,
        "target_node_id": edge.target_node_id,
        "edge_type": edge.edge_type or "reference",
        "source_anchor": edge.source_anchor or "auto",
        "target_anchor": edge.target_anchor or "auto",
        "is_collapsed": bool(edge.is_collapsed),
        "created_at": edge.created_at,
        "updated_at": edge.updated_at,
    }


def _build_preview_map(db: Session, user_id: int | None, canvas_ids: list[int]) -> dict[int, list[str]]:
    if not canvas_ids:
        return {}
    cos_config = get_optional_cos_config(db)
    wanted_ids = set(canvas_ids)
    preview_map: dict[int, list[str]] = {canvas_id: [] for canvas_id in wanted_ids}
    recent_images_query = (
        db.query(Task.canvas_id, Image.image_url, Image.preview_url)
        .join(Task, Image.task_id == Task.id)
        .filter(
            Task.canvas_id.in_(canvas_ids),
            Task.is_deleted.is_(False),
            Image.is_deleted.is_(False),
            Image.status == "success",
        )
        .order_by(Task.created_at.desc(), Image.id.desc())
    )
    if user_id is not None:
        recent_images_query = recent_images_query.filter(Task.user_id == user_id)
    recent_images = recent_images_query.limit(max(60, len(canvas_ids) * DEFAULT_CANVAS_PREVIEW_LIMIT * 4)).all()
    for canvas_id, raw_image_url, raw_preview_url in recent_images:
        if canvas_id not in wanted_ids:
            continue
        previews = preview_map.setdefault(canvas_id, [])
        if len(previews) >= DEFAULT_CANVAS_PREVIEW_LIMIT:
            continue
        preview_url = _resolve_preview_url(raw_image_url, raw_preview_url=raw_preview_url, cos_config=cos_config)
        if preview_url and preview_url not in previews:
            previews.append(preview_url)
    image_nodes = (
        db.query(CanvasNode.canvas_id, CanvasNode.image_url)
        .filter(
            CanvasNode.canvas_id.in_(canvas_ids),
            CanvasNode.task_id.is_(None),
            CanvasNode.video_task_id.is_(None),
            CanvasNode.node_type == "image",
            CanvasNode.image_url != "",
        )
        .order_by(CanvasNode.updated_at.desc(), CanvasNode.id.desc())
        .limit(max(60, len(canvas_ids) * DEFAULT_CANVAS_PREVIEW_LIMIT * 4))
        .all()
    )
    for canvas_id, raw_image_url in image_nodes:
        previews = preview_map.setdefault(canvas_id, [])
        if len(previews) >= DEFAULT_CANVAS_PREVIEW_LIMIT:
            continue
        preview_url = _resolve_preview_url(raw_image_url, cos_config=cos_config)
        if preview_url and preview_url not in previews:
            previews.append(preview_url)
    video_nodes_query = (
        db.query(CanvasNode.canvas_id, CanvasNode.updated_at, CanvasNode.id, VideoResult.cover_url, VideoResult.video_url)
        .join(VideoTask, VideoTask.id == CanvasNode.video_task_id)
        .join(VideoResult, VideoResult.task_id == VideoTask.id)
        .filter(
            CanvasNode.canvas_id.in_(canvas_ids),
            CanvasNode.video_task_id.is_not(None),
            VideoTask.is_deleted.is_(False),
            VideoResult.status == "success",
        )
        .order_by(CanvasNode.updated_at.desc(), CanvasNode.id.desc(), VideoResult.id.desc())
    )
    if user_id is not None:
        video_nodes_query = video_nodes_query.filter(VideoTask.user_id == user_id)
    video_nodes = video_nodes_query.limit(max(60, len(canvas_ids) * DEFAULT_CANVAS_PREVIEW_LIMIT * 4)).all()
    for canvas_id, _updated_at, _node_id, raw_cover_url, raw_video_url in video_nodes:
        if canvas_id not in wanted_ids:
            continue
        previews = preview_map.setdefault(canvas_id, [])
        if len(previews) >= DEFAULT_CANVAS_PREVIEW_LIMIT:
            continue
        cover_url = (
            _resolve_preview_url(raw_cover_url, cos_config=cos_config)
            if raw_cover_url
            else normalize_external_image_url(raw_video_url, cos_config=cos_config)
        )
        if cover_url and cover_url not in previews:
            previews.append(cover_url)
    return preview_map


def get_user_canvas_or_404(db: Session, user_id: int, project_id: str) -> UserCanvas:
    normalized_project_id = _normalize_project_id(project_id)
    canvas = (
        db.query(UserCanvas)
        .filter(
            UserCanvas.project_id == normalized_project_id,
            UserCanvas.user_id == user_id,
            UserCanvas.is_deleted.is_(False),
        )
        .first()
    )
    if not canvas:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="画布不存在")
    return canvas


def get_canvas_for_read_or_404(
    db: Session,
    user_id: int,
    project_id: str,
    *,
    allow_admin_read: bool = False,
    allow_deleted_read: bool = False,
) -> tuple[UserCanvas, bool]:
    normalized_project_id = _normalize_project_id(project_id)
    query = db.query(UserCanvas).filter(UserCanvas.project_id == normalized_project_id)
    if not allow_deleted_read:
        query = query.filter(UserCanvas.is_deleted.is_(False))
    query = query.options(joinedload(UserCanvas.user))
    if not allow_admin_read:
        query = query.filter(UserCanvas.user_id == user_id)
    canvas = query.first()
    if not canvas:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="画布不存在")
    return canvas, canvas.user_id != user_id


def list_user_canvases(
    db: Session,
    user_id: int,
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
) -> dict:
    base_query = (
        db.query(UserCanvas)
        .filter(UserCanvas.user_id == user_id, UserCanvas.is_deleted.is_(False))
    )
    normalized_keyword = (keyword or "").strip()
    if normalized_keyword:
        base_query = base_query.filter(UserCanvas.name.ilike(f"%{normalized_keyword}%"))
    total = int(base_query.with_entities(func.count(UserCanvas.id)).scalar() or 0)
    canvases = (
        base_query
        .options(joinedload(UserCanvas.user))
        .order_by(UserCanvas.updated_at.desc(), UserCanvas.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    if not canvases:
        return {"items": [], "total": total, "page": page, "page_size": page_size, "has_more": False}

    canvas_ids = [canvas.id for canvas in canvases]
    count_rows = (
        db.query(CanvasNode.canvas_id, func.count(CanvasNode.id).label("node_count"))
        .outerjoin(Task, Task.id == CanvasNode.task_id)
        .outerjoin(VideoTask, VideoTask.id == CanvasNode.video_task_id)
        .filter(CanvasNode.canvas_id.in_(canvas_ids), _visible_canvas_node_filter(user_id=user_id))
        .group_by(CanvasNode.canvas_id)
        .all()
    )
    count_map = {row.canvas_id: int(row.node_count or 0) for row in count_rows}
    preview_map = _build_preview_map(db, user_id, canvas_ids)
    return {
        "items": [
            _serialize_canvas_summary(canvas, count_map.get(canvas.id, 0), preview_map.get(canvas.id, []))
            for canvas in canvases
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": page * page_size < total,
    }


def list_all_canvases(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    owner_user_id: int | None = None,
) -> dict:
    base_query = (
        db.query(UserCanvas)
        .join(User, User.id == UserCanvas.user_id)
        .filter(
            User.role.notin_(["admin", "superadmin"]),
            User.is_whitelisted.is_(False),
        )
    )
    normalized_keyword = (keyword or "").strip()
    if owner_user_id is not None:
        base_query = base_query.filter(UserCanvas.user_id == owner_user_id)
    if normalized_keyword:
        base_query = base_query.filter(UserCanvas.name.ilike(f"%{normalized_keyword}%"))
    total = int(base_query.with_entities(func.count(UserCanvas.id)).scalar() or 0)
    canvases = (
        base_query
        .options(joinedload(UserCanvas.user))
        .order_by(UserCanvas.updated_at.desc(), UserCanvas.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    if not canvases:
        return {"items": [], "total": total, "page": page, "page_size": page_size, "has_more": False}

    canvas_ids = [canvas.id for canvas in canvases]
    count_rows = (
        db.query(CanvasNode.canvas_id, func.count(CanvasNode.id).label("node_count"))
        .outerjoin(Task, Task.id == CanvasNode.task_id)
        .outerjoin(VideoTask, VideoTask.id == CanvasNode.video_task_id)
        .filter(CanvasNode.canvas_id.in_(canvas_ids), _visible_canvas_node_filter())
        .group_by(CanvasNode.canvas_id)
        .all()
    )
    count_map = {row.canvas_id: int(row.node_count or 0) for row in count_rows}
    preview_map = _build_preview_map(db, None, canvas_ids)
    return {
        "items": [
            _serialize_canvas_summary(
                canvas,
                count_map.get(canvas.id, 0),
                preview_map.get(canvas.id, []),
                is_readonly=True,
            )
            for canvas in canvases
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": page * page_size < total,
    }


def create_user_canvas(db: Session, user_id: int, name: str | None = None) -> dict:
    canvas = UserCanvas(
        user_id=user_id,
        project_id=_generate_unique_project_id(db),
        name=_normalize_canvas_name(name),
        zoom=DEFAULT_CANVAS_ZOOM,
    )
    db.add(canvas)
    db.commit()
    db.refresh(canvas)
    return _serialize_canvas_summary(canvas)


def update_user_canvas(
    db: Session,
    user_id: int,
    project_id: str,
    *,
    name: str | None = None,
    viewport_x: float | None = None,
    viewport_y: float | None = None,
    zoom: float | None = None,
) -> dict:
    canvas = get_user_canvas_or_404(db, user_id, project_id)
    if name is not None:
        canvas.name = _normalize_canvas_name(name, fallback=canvas.name or "未命名画布")
    if viewport_x is not None:
        canvas.viewport_x = viewport_x
    if viewport_y is not None:
        canvas.viewport_y = viewport_y
    if zoom is not None:
        canvas.zoom = zoom
    db.commit()
    db.refresh(canvas)
    return _serialize_canvas_summary(canvas, get_canvas_node_count(db, canvas.id))


def update_canvas_viewport(db: Session, user_id: int, project_id: str, *, viewport_x: float, viewport_y: float, zoom: float) -> dict:
    return update_user_canvas(
        db,
        user_id,
        project_id,
        viewport_x=viewport_x,
        viewport_y=viewport_y,
        zoom=zoom,
    )


def delete_user_canvas(db: Session, user_id: int, project_id: str) -> None:
    canvas = get_user_canvas_or_404(db, user_id, project_id)
    canvas.is_deleted = True
    canvas.deleted_at = now_local()
    db.commit()


def get_canvas_node_count(db: Session, canvas_id: int) -> int:
    return int(
        db.query(func.count(CanvasNode.id))
        .outerjoin(Task, Task.id == CanvasNode.task_id)
        .outerjoin(VideoTask, VideoTask.id == CanvasNode.video_task_id)
        .filter(CanvasNode.canvas_id == canvas_id, _visible_canvas_node_filter())
        .scalar()
        or 0
    )


def get_canvas_detail(db: Session, user_id: int, project_id: str, *, allow_admin_read: bool = False) -> dict:
    canvas, is_readonly = get_canvas_for_read_or_404(
        db,
        user_id,
        project_id,
        allow_admin_read=allow_admin_read,
        allow_deleted_read=allow_admin_read,
    )
    task_visibility_filter = _visible_canvas_node_filter(
        user_id=None if is_readonly else user_id,
    )
    nodes = (
        db.query(CanvasNode)
        .outerjoin(Task, Task.id == CanvasNode.task_id)
        .outerjoin(VideoTask, VideoTask.id == CanvasNode.video_task_id)
        .options(*CANVAS_NODE_LOAD_OPTIONS)
        .filter(
            CanvasNode.canvas_id == canvas.id,
            task_visibility_filter,
        )
        .order_by(CanvasNode.z_index.asc(), CanvasNode.id.asc())
        .all()
    )
    cos_config = get_optional_cos_config(db)
    detail = _serialize_canvas_summary(canvas, len(nodes), is_readonly=is_readonly)
    detail["nodes"] = _serialize_nodes(db, nodes, owner_user_id=canvas.user_id, cos_config=cos_config)
    node_ids = [node.id for node in nodes]
    edges = []
    if node_ids:
        edges = (
            db.query(CanvasEdge)
            .filter(
                CanvasEdge.canvas_id == canvas.id,
                CanvasEdge.source_node_id.in_(node_ids),
                CanvasEdge.target_node_id.in_(node_ids),
            )
            .order_by(CanvasEdge.id.asc())
            .all()
        )
    detail["edges"] = [_serialize_edge(edge) for edge in edges]
    group_rows = (
        db.query(CanvasGroup)
        .filter(CanvasGroup.canvas_id == canvas.id)
        .order_by(CanvasGroup.z_index.asc(), CanvasGroup.id.asc())
        .all()
    )
    visible_node_ids = set(node_ids)
    detail["groups"] = [
        _serialize_group(group, [node.id for node in nodes if node.group_id == group.id and node.id in visible_node_ids])
        for group in group_rows
    ]
    return detail


def update_canvas_node(
    db: Session,
    user_id: int,
    project_id: str,
    node_id: int,
    *,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
    z_index: int | None = None,
    content: str | None = None,
) -> dict:
    canvas = get_user_canvas_or_404(db, user_id, project_id)
    node = (
        db.query(CanvasNode)
        .outerjoin(Task, Task.id == CanvasNode.task_id)
        .outerjoin(VideoTask, VideoTask.id == CanvasNode.video_task_id)
        .options(*CANVAS_NODE_LOAD_OPTIONS)
        .filter(
            CanvasNode.id == node_id,
            CanvasNode.canvas_id == canvas.id,
            _visible_canvas_node_filter(user_id=user_id),
        )
        .first()
    )
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="画布节点不存在")
    if x is not None:
        node.x = x
    if y is not None:
        node.y = y
    if width is not None:
        node.width = width
    if height is not None:
        node.height = height
    if z_index is not None:
        node.z_index = z_index
    if content is not None:
        if (node.node_type or "") != "text":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只有文本节点可以编辑内容")
        node.content = content.strip() or "双击编辑文本"
    db.commit()
    db.refresh(node)
    return _serialize_nodes(db, [node], owner_user_id=user_id, cos_config=get_optional_cos_config(db))[0]


def update_canvas_nodes_batch(
    db: Session,
    user_id: int,
    project_id: str,
    *,
    updates: list,
) -> dict:
    canvas = get_user_canvas_or_404(db, user_id, project_id)
    if not updates:
        return {"nodes": []}

    node_ids = [int(item.id) for item in updates]
    nodes = (
        db.query(CanvasNode)
        .outerjoin(Task, Task.id == CanvasNode.task_id)
        .outerjoin(VideoTask, VideoTask.id == CanvasNode.video_task_id)
        .options(*CANVAS_NODE_LOAD_OPTIONS)
        .filter(
            CanvasNode.id.in_(node_ids),
            CanvasNode.canvas_id == canvas.id,
            _visible_canvas_node_filter(user_id=user_id),
        )
        .all()
    )
    node_map = {node.id: node for node in nodes}
    if len(node_map) != len(set(node_ids)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部分画布节点不存在")

    for item in updates:
        node = node_map[int(item.id)]
        if item.x is not None:
            node.x = item.x
        if item.y is not None:
            node.y = item.y
        if item.width is not None:
            node.width = item.width
        if item.height is not None:
            node.height = item.height
        if item.z_index is not None:
            node.z_index = item.z_index
        if item.content is not None:
            if (node.node_type or "") != "text":
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只有文本节点可以编辑内容")
            node.content = item.content.strip() or "双击编辑文本"

    canvas.updated_at = now_local()
    db.commit()
    for node in nodes:
        db.refresh(node)
    cos_config = get_optional_cos_config(db)
    ordered_nodes = [node_map[int(item.id)] for item in updates]
    return {"nodes": _serialize_nodes(db, ordered_nodes, owner_user_id=user_id, cos_config=cos_config)}


def create_canvas_group(
    db: Session,
    user_id: int,
    project_id: str,
    *,
    name: str,
    color: str,
    node_ids: list[int],
    node_updates: list,
    x: float,
    y: float,
    width: float,
    height: float,
    z_index: int,
) -> dict:
    canvas = get_user_canvas_or_404(db, user_id, project_id)
    normalized_node_ids = list(dict.fromkeys(int(node_id) for node_id in node_ids if int(node_id) > 0))
    if not normalized_node_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少选择一个节点")

    nodes = (
        db.query(CanvasNode)
        .outerjoin(Task, Task.id == CanvasNode.task_id)
        .outerjoin(VideoTask, VideoTask.id == CanvasNode.video_task_id)
        .options(*CANVAS_NODE_LOAD_OPTIONS)
        .filter(
            CanvasNode.id.in_(normalized_node_ids),
            CanvasNode.canvas_id == canvas.id,
            _visible_canvas_node_filter(user_id=user_id),
        )
        .all()
    )
    node_map = {node.id: node for node in nodes}
    if len(node_map) != len(normalized_node_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部分画布节点不存在")
    source_group_ids = [int(node.group_id) for node in nodes if node.group_id is not None]

    group = CanvasGroup(
        canvas_id=canvas.id,
        name=(name or "").strip() or "未命名分组",
        color=(color or "").strip() or "#ffab27",
        x=x,
        y=y,
        width=width,
        height=height,
        z_index=z_index,
    )
    db.add(group)
    db.flush()

    update_map = {int(item.id): item for item in node_updates}
    for node_id in normalized_node_ids:
        node = node_map[node_id]
        update = update_map.get(node_id)
        if update:
            if update.x is not None:
                node.x = update.x
            if update.y is not None:
                node.y = update.y
            if update.z_index is not None:
                node.z_index = update.z_index
        node.group_id = group.id

    _delete_empty_groups(db, canvas.id, source_group_ids)
    canvas.updated_at = now_local()
    db.commit()
    db.refresh(group)
    for node in nodes:
        db.refresh(node)
    cos_config = get_optional_cos_config(db)
    ordered_nodes = [node_map[node_id] for node_id in normalized_node_ids]
    return {
        "group": _serialize_group(group, normalized_node_ids),
        "nodes": _serialize_nodes(db, ordered_nodes, owner_user_id=user_id, cos_config=cos_config),
    }


def update_canvas_group(
    db: Session,
    user_id: int,
    project_id: str,
    group_id: int,
    *,
    name: str | None = None,
    color: str | None = None,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
    z_index: int | None = None,
) -> dict:
    canvas = get_user_canvas_or_404(db, user_id, project_id)
    group = (
        db.query(CanvasGroup)
        .filter(CanvasGroup.id == group_id, CanvasGroup.canvas_id == canvas.id)
        .first()
    )
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="画布分组不存在")
    if name is not None:
        group.name = name.strip() or "未命名分组"
    if color is not None:
        group.color = color.strip() or "#ffab27"
    if x is not None:
        group.x = x
    if y is not None:
        group.y = y
    if width is not None:
        group.width = width
    if height is not None:
        group.height = height
    if z_index is not None:
        group.z_index = z_index
    canvas.updated_at = now_local()
    db.commit()
    db.refresh(group)
    node_ids = [node_id for (node_id,) in db.query(CanvasNode.id).filter(CanvasNode.group_id == group.id).all()]
    return _serialize_group(group, node_ids)


def assign_nodes_to_canvas_group(
    db: Session,
    user_id: int,
    project_id: str,
    group_id: int,
    *,
    node_updates: list,
) -> dict:
    canvas = get_user_canvas_or_404(db, user_id, project_id)
    group = (
        db.query(CanvasGroup)
        .filter(CanvasGroup.id == group_id, CanvasGroup.canvas_id == canvas.id)
        .first()
    )
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="画布分组不存在")
    if not node_updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少选择一个节点")

    node_ids = list(dict.fromkeys(int(item.id) for item in node_updates if int(item.id) > 0))
    nodes = (
        db.query(CanvasNode)
        .outerjoin(Task, Task.id == CanvasNode.task_id)
        .outerjoin(VideoTask, VideoTask.id == CanvasNode.video_task_id)
        .options(*CANVAS_NODE_LOAD_OPTIONS)
        .filter(
            CanvasNode.id.in_(node_ids),
            CanvasNode.canvas_id == canvas.id,
            _visible_canvas_node_filter(user_id=user_id),
        )
        .all()
    )
    node_map = {node.id: node for node in nodes}
    if len(node_map) != len(node_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部分画布节点不存在")

    source_group_ids = [int(node.group_id) for node in nodes if node.group_id is not None and int(node.group_id) != group.id]
    update_map = {int(item.id): item for item in node_updates}
    for node_id in node_ids:
        node = node_map[node_id]
        update = update_map.get(node_id)
        if update:
            if update.x is not None:
                node.x = update.x
            if update.y is not None:
                node.y = update.y
            if update.z_index is not None:
                node.z_index = update.z_index
        node.group_id = group.id

    deleted_group_ids = _delete_empty_groups(db, canvas.id, source_group_ids)
    affected_group_ids = [group.id, *source_group_ids]
    updated_groups = [
        serialized_group
        for affected_group_id in dict.fromkeys(affected_group_ids)
        if affected_group_id not in deleted_group_ids
        for serialized_group in [_sync_group_layout(db, canvas.id, affected_group_id)]
        if serialized_group
    ]
    canvas.updated_at = now_local()
    db.commit()
    db.refresh(group)
    for node in nodes:
        db.refresh(node)
    cos_config = get_optional_cos_config(db)
    ordered_nodes = [node_map[node_id] for node_id in node_ids]
    target_group = next((item for item in updated_groups if item["id"] == group.id), _serialize_group(group, node_ids))
    return {
        "group": target_group,
        "groups": updated_groups,
        "nodes": _serialize_nodes(db, ordered_nodes, owner_user_id=user_id, cos_config=cos_config),
        "deleted_group_ids": sorted(deleted_group_ids),
    }


def remove_nodes_from_canvas_groups(
    db: Session,
    user_id: int,
    project_id: str,
    *,
    node_updates: list,
) -> dict:
    canvas = get_user_canvas_or_404(db, user_id, project_id)
    if not node_updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少选择一个节点")

    node_ids = list(dict.fromkeys(int(item.id) for item in node_updates if int(item.id) > 0))
    nodes = (
        db.query(CanvasNode)
        .outerjoin(Task, Task.id == CanvasNode.task_id)
        .outerjoin(VideoTask, VideoTask.id == CanvasNode.video_task_id)
        .options(*CANVAS_NODE_LOAD_OPTIONS)
        .filter(
            CanvasNode.id.in_(node_ids),
            CanvasNode.canvas_id == canvas.id,
            _visible_canvas_node_filter(user_id=user_id),
        )
        .all()
    )
    node_map = {node.id: node for node in nodes}
    if len(node_map) != len(node_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部分画布节点不存在")

    source_group_ids = [int(node.group_id) for node in nodes if node.group_id is not None]
    update_map = {int(item.id): item for item in node_updates}
    for node_id in node_ids:
        node = node_map[node_id]
        update = update_map.get(node_id)
        if update:
            if update.x is not None:
                node.x = update.x
            if update.y is not None:
                node.y = update.y
            if update.z_index is not None:
                node.z_index = update.z_index
        node.group_id = None

    deleted_group_ids = _delete_empty_groups(db, canvas.id, source_group_ids)
    updated_groups = [
        serialized_group
        for affected_group_id in dict.fromkeys(source_group_ids)
        if affected_group_id not in deleted_group_ids
        for serialized_group in [_sync_group_layout(db, canvas.id, affected_group_id)]
        if serialized_group
    ]
    canvas.updated_at = now_local()
    db.commit()
    for node in nodes:
        db.refresh(node)
    cos_config = get_optional_cos_config(db)
    ordered_nodes = [node_map[node_id] for node_id in node_ids]
    return {
        "groups": updated_groups,
        "nodes": _serialize_nodes(db, ordered_nodes, owner_user_id=user_id, cos_config=cos_config),
        "deleted_group_ids": sorted(deleted_group_ids),
    }


def delete_canvas_group(db: Session, user_id: int, project_id: str, group_id: int) -> None:
    canvas = get_user_canvas_or_404(db, user_id, project_id)
    group = (
        db.query(CanvasGroup)
        .filter(CanvasGroup.id == group_id, CanvasGroup.canvas_id == canvas.id)
        .first()
    )
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="画布分组不存在")
    db.query(CanvasNode).filter(
        CanvasNode.canvas_id == canvas.id,
        CanvasNode.group_id == group.id,
    ).update({CanvasNode.group_id: None}, synchronize_session=False)
    db.delete(group)
    canvas.updated_at = now_local()
    db.commit()


def delete_canvas_node(db: Session, user_id: int, project_id: str, node_id: int) -> None:
    canvas = get_user_canvas_or_404(db, user_id, project_id)
    node = (
        db.query(CanvasNode)
        .outerjoin(Task, Task.id == CanvasNode.task_id)
        .outerjoin(VideoTask, VideoTask.id == CanvasNode.video_task_id)
        .filter(
            CanvasNode.id == node_id,
            CanvasNode.canvas_id == canvas.id,
            _visible_canvas_node_filter(user_id=user_id),
        )
        .first()
    )
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="画布节点不存在")
    db.query(CanvasEdge).filter(
        CanvasEdge.canvas_id == canvas.id,
        ((CanvasEdge.source_node_id == node.id) | (CanvasEdge.target_node_id == node.id)),
    ).delete(synchronize_session=False)
    db.delete(node)
    canvas.updated_at = now_local()
    db.commit()


def create_canvas_free_node(
    db: Session,
    user_id: int,
    project_id: str,
    *,
    node_type: str,
    content: str = "",
    image_url: str = "",
    x: float = 0,
    y: float = 0,
    width: float = DEFAULT_NODE_WIDTH,
    height: float = 220,
) -> dict:
    canvas = get_user_canvas_or_404(db, user_id, project_id)
    normalized_type = (node_type or "").strip()
    if normalized_type not in {"text", "image"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="节点类型不支持")
    normalized_content = (content or "").strip()
    normalized_image_url = (image_url or "").strip()
    if normalized_type == "text" and not normalized_content:
        normalized_content = "双击编辑文本"
    if normalized_type == "image" and not normalized_image_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先上传图片")

    existing_max_z = (
        db.query(func.max(CanvasNode.z_index))
        .filter(CanvasNode.canvas_id == canvas.id)
        .scalar()
        or 0
    )
    node = CanvasNode(
        canvas_id=canvas.id,
        task_id=None,
        node_type=normalized_type,
        content=normalized_content,
        image_url=normalized_image_url,
        x=x,
        y=y,
        width=width,
        height=height,
        z_index=int(existing_max_z) + 1,
    )
    db.add(node)
    canvas.updated_at = now_local()
    db.commit()
    db.refresh(node)
    return _serialize_nodes(db, [node], owner_user_id=user_id, cos_config=get_optional_cos_config(db))[0]


def create_canvas_generation_tasks(
    db: Session,
    user_id: int,
    project_id: str,
    *,
    model: str,
    source: str,
    mode: str,
    prompt: str,
    num_images: int,
    size: str,
    resolution: str,
    custom_size: str = "",
    reference_images: list[str] | None = None,
    source_node_ids: list[int] | None = None,
    source_image: str = "",
    mask_image: str = "",
    x: float = 0,
    y: float = 0,
    width: float = DEFAULT_NODE_WIDTH,
    height: float = DEFAULT_NODE_HEIGHT,
) -> tuple[list[Task], list[dict]]:
    canvas = get_user_canvas_or_404(db, user_id, project_id)
    normalized_source_node_ids = list(dict.fromkeys(int(node_id) for node_id in (source_node_ids or []) if int(node_id) > 0))
    source_nodes: list[CanvasNode] = []
    if normalized_source_node_ids:
        source_nodes = (
            db.query(CanvasNode)
            .outerjoin(Task, Task.id == CanvasNode.task_id)
            .outerjoin(VideoTask, VideoTask.id == CanvasNode.video_task_id)
            .filter(
                CanvasNode.id.in_(normalized_source_node_ids),
                CanvasNode.canvas_id == canvas.id,
                _visible_canvas_node_filter(user_id=user_id),
            )
            .all()
        )
        if len({node.id for node in source_nodes}) != len(normalized_source_node_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="部分来源节点不可用")
    tasks = create_tasks(
        db,
        user_id=user_id,
        model=model,
        source=source,
        mode=mode,
        prompt=prompt,
        num_images=num_images,
        size=size,
        resolution=resolution,
        custom_size=custom_size,
        reference_images=reference_images,
        source_image=source_image,
        mask_image=mask_image,
        board_id=None,
        canvas_id=canvas.id,
    )

    existing_max_z = (
        db.query(func.max(CanvasNode.z_index))
        .filter(CanvasNode.canvas_id == canvas.id)
        .scalar()
        or 0
    )
    nodes: list[CanvasNode] = []
    for index, task in enumerate(tasks):
        node = CanvasNode(
            canvas_id=canvas.id,
            task_id=task.id,
            x=x + index * NODE_X_SPACING,
            y=y,
            width=width,
            height=height,
            z_index=int(existing_max_z) + index + 1,
        )
        db.add(node)
        nodes.append(node)
    db.flush()
    for source_node in source_nodes:
        for node in nodes:
            db.add(CanvasEdge(
                canvas_id=canvas.id,
                source_node_id=source_node.id,
                target_node_id=node.id,
                edge_type="generation",
            ))
    canvas.updated_at = now_local()
    db.commit()

    for node in nodes:
        db.refresh(node)
    cos_config = get_optional_cos_config(db)
    return tasks, _serialize_nodes(db, nodes, owner_user_id=user_id, cos_config=cos_config)


def create_canvas_video_tasks(
    db: Session,
    user_id: int,
    project_id: str,
    *,
    model: str,
    source: str,
    prompt: str,
    duration_seconds: int,
    aspect_ratio: str,
    resolution: str,
    reference_images: list[str] | None = None,
    source_node_ids: list[int] | None = None,
    x: float = 0,
    y: float = 0,
    width: float = DEFAULT_NODE_WIDTH,
    height: float = DEFAULT_NODE_HEIGHT,
) -> tuple[list[VideoTask], list[dict]]:
    canvas = get_user_canvas_or_404(db, user_id, project_id)
    normalized_source_node_ids = list(dict.fromkeys(int(node_id) for node_id in (source_node_ids or []) if int(node_id) > 0))
    source_nodes: list[CanvasNode] = []
    if normalized_source_node_ids:
        source_nodes = (
            db.query(CanvasNode)
            .outerjoin(Task, Task.id == CanvasNode.task_id)
            .outerjoin(VideoTask, VideoTask.id == CanvasNode.video_task_id)
            .filter(
                CanvasNode.id.in_(normalized_source_node_ids),
                CanvasNode.canvas_id == canvas.id,
                _visible_canvas_node_filter(user_id=user_id),
            )
            .all()
        )
        if len({node.id for node in source_nodes}) != len(normalized_source_node_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="部分来源节点不可用")

    task = create_video_task_record(
        db,
        user_id=user_id,
        model=model,
        source=source,
        generation_mode="image_to_video" if reference_images else "text_to_video",
        prompt=prompt,
        duration_seconds=duration_seconds,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        reference_images=reference_images,
    )

    existing_max_z = (
        db.query(func.max(CanvasNode.z_index))
        .filter(CanvasNode.canvas_id == canvas.id)
        .scalar()
        or 0
    )
    node = CanvasNode(
        canvas_id=canvas.id,
        task_id=None,
        video_task_id=task.id,
        x=x,
        y=y,
        width=width,
        height=height,
        z_index=int(existing_max_z) + 1,
    )
    db.add(node)
    db.flush()
    for source_node in source_nodes:
        db.add(CanvasEdge(
            canvas_id=canvas.id,
            source_node_id=source_node.id,
            target_node_id=node.id,
            edge_type="generation",
        ))
    canvas.updated_at = now_local()
    db.commit()

    db.refresh(node)
    cos_config = get_optional_cos_config(db)
    return [task], _serialize_nodes(db, [node], owner_user_id=user_id, cos_config=cos_config)


def update_canvas_edge(
    db: Session,
    user_id: int,
    project_id: str,
    edge_id: int,
    *,
    is_collapsed: bool | None = None,
) -> dict:
    canvas = get_user_canvas_or_404(db, user_id, project_id)
    edge = (
        db.query(CanvasEdge)
        .filter(CanvasEdge.id == edge_id, CanvasEdge.canvas_id == canvas.id)
        .first()
    )
    if not edge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="画布连线不存在")
    if is_collapsed is not None:
        edge.is_collapsed = is_collapsed
    canvas.updated_at = now_local()
    db.commit()
    db.refresh(edge)
    return _serialize_edge(edge)
