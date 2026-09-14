import json
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.canvas_edge import CanvasEdge
from app.models.canvas_group import CanvasGroup
from app.models.canvas_node import CanvasNode
from app.models.example_canvas_project import ExampleCanvasProject
from app.models.image import Image
from app.models.task import Task
from app.models.user import User
from app.models.user_canvas import UserCanvas
from app.services.business_id_service import user_external_id
from app.services.canvas_service import (
    _generate_unique_project_id,
    _normalize_canvas_name,
    _serialize_canvas_summary,
    get_canvas_node_count,
)
from app.services.cos_service import build_object_key, load_image_bytes, upload_bytes_to_cos
from app.utils.datetime_utils import now_local

VALID_EXAMPLE_STATUSES = {"draft", "published", "disabled"}
MAX_TITLE_LENGTH = 100
MAX_SUBTITLE_LENGTH = 255
MAX_PREVIEW_COUNT = 3


def _parse_reference_images(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item).strip() for item in data if str(item).strip()]


def _normalize_status(value: str | None, *, fallback: str = "draft") -> str:
    normalized = (value or "").strip() or fallback
    if normalized not in VALID_EXAMPLE_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="示例项目状态不支持")
    return normalized


def _normalize_title(value: str | None, *, fallback: str = "") -> str:
    normalized = (value or "").strip() or (fallback or "").strip()
    if len(normalized) > MAX_TITLE_LENGTH:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"标题不能超过 {MAX_TITLE_LENGTH} 个字符")
    return normalized


def _normalize_subtitle(value: str | None, *, fallback: str = "") -> str:
    normalized = (value or "").strip() or (fallback or "").strip()
    if len(normalized) > MAX_SUBTITLE_LENGTH:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"副标题不能超过 {MAX_SUBTITLE_LENGTH} 个字符")
    return normalized


def _normalize_cover_url(value: str | None) -> str:
    return (value or "").strip()


def _is_canvas_asset_url(image_url: str) -> bool:
    if not image_url:
        return False
    parsed = urlparse(image_url)
    path = (parsed.path or image_url).lstrip("/")
    if path.startswith("uploads/"):
        path = path[len("uploads/"):]
    return path.startswith("canvas/")


def _ensure_canvas_asset_url(db: Session, image_url: str, *, label: str) -> str:
    normalized_image_url = (image_url or "").strip()
    if not normalized_image_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{label}不存在或不可用")
    if _is_canvas_asset_url(normalized_image_url):
        return normalized_image_url
    image_data = load_image_bytes(normalized_image_url)
    if not image_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{label}不存在或不可用")
    data, content_type = image_data
    key = build_object_key("canvas", f"{label}.jpg", content_type)
    return upload_bytes_to_cos(
        db,
        data=data,
        key=key,
        content_type=content_type,
        cache_control="public, max-age=31536000, immutable",
    )


def _pick_task_image_url(task: Task | None) -> str:
    if not task:
        return ""
    images = sorted(task.images or [], key=lambda item: (item.id or 0))
    for image in images:
        if image.status != "success" or image.is_deleted:
            continue
        candidate = (image.image_url or image.preview_url or "").strip()
        if candidate:
            return candidate
    return ""


def _archive_optional_canvas_asset(db: Session, image_url: str | None, *, label: str) -> str:
    normalized = (image_url or "").strip()
    if not normalized:
        return ""
    return _ensure_canvas_asset_url(db, normalized, label=label)


def _archive_task_image_snapshot(db: Session, task: Task, *, node_id: int) -> list[dict]:
    snapshots: list[dict] = []
    for image in sorted(task.images or [], key=lambda item: (item.id or 0)):
        if image.is_deleted:
            continue
        normalized_status = "success" if image.status == "success" and (image.image_url or image.preview_url) else "failed"
        archived_image_url = ""
        archived_preview_url = ""
        if normalized_status == "success":
            archived_image_url = _ensure_canvas_asset_url(
                db,
                (image.image_url or image.preview_url or "").strip(),
                label=f"canvas-task-{node_id}-image-{image.id}",
            )
            archived_preview_url = archived_image_url
        snapshots.append(
            {
                "status": normalized_status,
                "image_url": archived_image_url,
                "preview_url": archived_preview_url,
                "image_format": image.image_format or "",
                "image_size_bytes": int(image.image_size_bytes or 0),
                "error_message": image.error_message or "",
            }
        )
    return snapshots


def _get_source_canvas_or_404(db: Session, project_id: str) -> UserCanvas:
    normalized_project_id = (project_id or "").strip()
    canvas = (
        db.query(UserCanvas)
        .options(joinedload(UserCanvas.user))
        .filter(UserCanvas.project_id == normalized_project_id, UserCanvas.is_deleted.is_(False))
        .first()
    )
    if not canvas:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="源画布不存在")
    return canvas


def _get_example_project_or_404(db: Session, example_id: int) -> ExampleCanvasProject:
    example = (
        db.query(ExampleCanvasProject)
        .options(
            joinedload(ExampleCanvasProject.source_canvas).joinedload(UserCanvas.user),
            joinedload(ExampleCanvasProject.creator),
            joinedload(ExampleCanvasProject.updater),
        )
        .filter(ExampleCanvasProject.id == example_id)
        .first()
    )
    if not example:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="示例项目不存在")
    return example


def _parse_snapshot(snapshot_json: str) -> dict:
    try:
        data = json.loads(snapshot_json or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="示例项目快照损坏") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="示例项目快照损坏")
    return data


def _extract_preview_urls(snapshot: dict) -> list[str]:
    preview_urls: list[str] = []
    for node in snapshot.get("nodes") or []:
        image_url = str((node or {}).get("image_url") or "").strip()
        if not image_url:
            task_payload = (node or {}).get("task") or {}
            images = task_payload.get("images") or []
            if images:
                image_url = str((images[0] or {}).get("image_url") or (images[0] or {}).get("preview_url") or "").strip()
        if not image_url or image_url in preview_urls:
            continue
        preview_urls.append(image_url)
        if len(preview_urls) >= MAX_PREVIEW_COUNT:
            break
    return preview_urls


def _serialize_example_project(example: ExampleCanvasProject) -> dict:
    preview_urls = example.preview_urls
    return {
        "id": example.id,
        "source_canvas_id": example.source_canvas_id,
        "source_project_id": example.source_project_id,
        "source_canvas_name": example.source_canvas.name if example.source_canvas else "",
        "title": example.title,
        "subtitle": example.subtitle or "",
        "cover_url": example.cover_url or (preview_urls[0] if preview_urls else ""),
        "status": example.status,
        "sort_order": int(example.sort_order or 0),
        "preview_urls": preview_urls,
        "created_by": user_external_id(example.creator) if example.creator else "",
        "updated_by": user_external_id(example.updater) if example.updater else "",
        "created_at": example.created_at,
        "updated_at": example.updated_at,
    }


def _validate_source_canvas_uniqueness(
    db: Session,
    *,
    source_canvas_id: int,
    source_project_id: str,
    exclude_example_id: int | None = None,
) -> None:
    query = db.query(ExampleCanvasProject).filter(
        (ExampleCanvasProject.source_canvas_id == source_canvas_id)
        | (ExampleCanvasProject.source_project_id == source_project_id)
    )
    if exclude_example_id is not None:
        query = query.filter(ExampleCanvasProject.id != exclude_example_id)
    if query.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该画布已被创建为示例项目")


def _build_example_snapshot(db: Session, source_canvas: UserCanvas) -> tuple[dict, list[str]]:
    nodes = (
        db.query(CanvasNode)
        .outerjoin(Task, Task.id == CanvasNode.task_id)
        .options(selectinload(CanvasNode.task).selectinload(Task.images))
        .filter(
            CanvasNode.canvas_id == source_canvas.id,
            (CanvasNode.task_id.is_(None)) | (Task.is_deleted.is_(False)),
        )
        .order_by(CanvasNode.z_index.asc(), CanvasNode.id.asc())
        .all()
    )
    node_id_set = {node.id for node in nodes}
    groups = (
        db.query(CanvasGroup)
        .filter(CanvasGroup.canvas_id == source_canvas.id)
        .order_by(CanvasGroup.z_index.asc(), CanvasGroup.id.asc())
        .all()
    )
    edges = (
        db.query(CanvasEdge)
        .filter(
            CanvasEdge.canvas_id == source_canvas.id,
            CanvasEdge.source_node_id.in_(node_id_set) if node_id_set else False,
            CanvasEdge.target_node_id.in_(node_id_set) if node_id_set else False,
        )
        .order_by(CanvasEdge.id.asc())
        .all()
        if node_id_set
        else []
    )

    snapshot_nodes: list[dict] = []
    preview_urls: list[str] = []
    for node in nodes:
        node_type = (node.node_type or "").strip() or ("task" if node.task_id else "text")
        group_id = int(node.group_id) if node.group_id is not None else None
        if node_type == "text":
            snapshot_nodes.append(
                {
                    "source_id": int(node.id),
                    "group_id": group_id,
                    "node_type": "text",
                    "content": node.content or "",
                    "image_url": "",
                    "x": float(node.x or 0),
                    "y": float(node.y or 0),
                    "width": float(node.width or 320),
                    "height": float(node.height or 220),
                    "z_index": int(node.z_index or 1),
                }
            )
            continue

        if node_type == "task":
            task = node.task
            if not task:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"源画布中存在不可用的任务节点（node_id={node.id}）",
                )
            task_images = _archive_task_image_snapshot(db, task, node_id=node.id)
            if not task_images:
                # 任务节点的结果图都已被删除时，视为已删除节点，不再进入示例快照。
                continue
            preview_image_url = next(
                (
                    str(image.get("image_url") or image.get("preview_url") or "").strip()
                    for image in task_images
                    if (image.get("status") or "") == "success"
                ),
                "",
            )
            if preview_image_url and preview_image_url not in preview_urls and len(preview_urls) < MAX_PREVIEW_COUNT:
                preview_urls.append(preview_image_url)
            reference_images = [
                _archive_optional_canvas_asset(db, ref, label=f"canvas-task-{node.id}-ref-{index}")
                for index, ref in enumerate(_parse_reference_images(task.reference_images), start=1)
            ]
            source_image = _archive_optional_canvas_asset(db, task.source_image, label=f"canvas-task-{node.id}-source")
            mask_image = _archive_optional_canvas_asset(db, task.mask_image, label=f"canvas-task-{node.id}-mask")
            normalized_status = "success" if any((image.get("status") or "") == "success" for image in task_images) else "failed"
            snapshot_nodes.append(
                {
                    "source_id": int(node.id),
                    "group_id": group_id,
                    "node_type": "task",
                    "content": "",
                    "image_url": preview_image_url,
                    "x": float(node.x or 0),
                    "y": float(node.y or 0),
                    "width": float(node.width or 320),
                    "height": float(node.height or 420),
                    "z_index": int(node.z_index or 1),
                    "task": {
                        "mode": task.mode or "generate",
                        "model": task.model or "",
                        "source": task.source or "web",
                        "prompt": task.prompt or "",
                        "num_images": int(task.num_images or len(task_images) or 1),
                        "size": task.size or "3:4",
                        "resolution": task.resolution or "",
                        "custom_size": task.custom_size or "",
                        "reference_images": [url for url in reference_images if url],
                        "source_image": source_image,
                        "mask_image": mask_image,
                        "status": normalized_status,
                        "error_message": "" if normalized_status == "success" else (task.error_message or ""),
                        "images": task_images,
                    },
                }
            )
            continue

        raw_image_url = (node.image_url or "").strip()
        if not raw_image_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"源画布中存在不可归档的图片节点（node_id={node.id}）",
            )
        archived_image_url = _ensure_canvas_asset_url(db, raw_image_url, label=f"canvas-node-{node.id}")
        if archived_image_url not in preview_urls and len(preview_urls) < MAX_PREVIEW_COUNT:
            preview_urls.append(archived_image_url)
        snapshot_nodes.append(
            {
                "source_id": int(node.id),
                "group_id": group_id,
                "node_type": "image",
                "content": "",
                "image_url": archived_image_url,
                "x": float(node.x or 0),
                "y": float(node.y or 0),
                "width": float(node.width or 320),
                "height": float(node.height or 420),
                "z_index": int(node.z_index or 1),
            }
        )

    visible_group_ids = {
        int(node.get("group_id"))
        for node in snapshot_nodes
        if node.get("group_id") is not None
    }
    snapshot_groups = [
        {
            "source_id": int(group.id),
            "name": group.name or "未命名分组",
            "color": group.color or "#ffab27",
            "x": float(group.x or 0),
            "y": float(group.y or 0),
            "width": float(group.width or 320),
            "height": float(group.height or 220),
            "z_index": int(group.z_index or 1),
        }
        for group in groups
        if group.id in visible_group_ids
    ]
    snapshot_edges = [
        {
            "source_node_id": int(edge.source_node_id),
            "target_node_id": int(edge.target_node_id),
            "edge_type": edge.edge_type or "reference",
            "source_anchor": edge.source_anchor or "auto",
            "target_anchor": edge.target_anchor or "auto",
            "is_collapsed": bool(edge.is_collapsed),
        }
        for edge in edges
    ]
    snapshot = {
        "source_canvas_id": int(source_canvas.id),
        "source_project_id": source_canvas.project_id,
        "title": source_canvas.name or "未命名示例项目",
        "viewport_x": float(source_canvas.viewport_x or 0),
        "viewport_y": float(source_canvas.viewport_y or 0),
        "zoom": float(source_canvas.zoom or 0.5),
        "nodes": snapshot_nodes,
        "groups": snapshot_groups,
        "edges": snapshot_edges,
    }
    if not preview_urls:
        preview_urls = _extract_preview_urls(snapshot)
    return snapshot, preview_urls


def list_admin_example_canvas_projects(db: Session) -> dict:
    items = (
        db.query(ExampleCanvasProject)
        .options(
            joinedload(ExampleCanvasProject.source_canvas).joinedload(UserCanvas.user),
            joinedload(ExampleCanvasProject.creator),
            joinedload(ExampleCanvasProject.updater),
        )
        .order_by(ExampleCanvasProject.sort_order.desc(), ExampleCanvasProject.id.desc())
        .all()
    )
    return {"items": [_serialize_example_project(item) for item in items]}


def list_published_example_canvas_projects(db: Session) -> dict:
    items = (
        db.query(ExampleCanvasProject)
        .options(joinedload(ExampleCanvasProject.source_canvas))
        .filter(ExampleCanvasProject.status == "published")
        .order_by(ExampleCanvasProject.sort_order.desc(), ExampleCanvasProject.id.desc())
        .all()
    )
    return {"items": [_serialize_example_project(item) for item in items]}


def create_example_canvas_project(
    db: Session,
    *,
    project_id: str,
    title: str | None,
    subtitle: str | None,
    cover_url: str | None,
    sort_order: int = 0,
    status_value: str = "draft",
    operator: User,
) -> dict:
    source_canvas = _get_source_canvas_or_404(db, project_id)
    _validate_source_canvas_uniqueness(
        db,
        source_canvas_id=source_canvas.id,
        source_project_id=source_canvas.project_id,
    )
    snapshot, preview_urls = _build_example_snapshot(db, source_canvas)
    final_title = _normalize_title(title, fallback=source_canvas.name or "未命名示例项目")
    final_subtitle = _normalize_subtitle(subtitle)
    final_cover_url = _normalize_cover_url(cover_url) or (preview_urls[0] if preview_urls else "")
    example = ExampleCanvasProject(
        source_canvas_id=source_canvas.id,
        source_project_id=source_canvas.project_id,
        title=final_title,
        subtitle=final_subtitle,
        cover_url=final_cover_url,
        status=_normalize_status(status_value),
        sort_order=int(sort_order or 0),
        preview_urls_json=json.dumps(preview_urls, ensure_ascii=False),
        snapshot_json=json.dumps({**snapshot, "title": final_title}, ensure_ascii=False),
        created_by=operator.id,
        updated_by=operator.id,
    )
    db.add(example)
    db.commit()
    db.refresh(example)
    return _serialize_example_project(example)


def update_example_canvas_project(
    db: Session,
    *,
    example_id: int,
    project_id: str | None,
    title: str | None,
    subtitle: str | None,
    cover_url: str | None,
    sort_order: int | None,
    status_value: str | None,
    refresh_snapshot: bool,
    operator: User,
) -> dict:
    example = _get_example_project_or_404(db, example_id)
    source_canvas = example.source_canvas
    if project_id:
        source_canvas = _get_source_canvas_or_404(db, project_id)
    if source_canvas is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="源画布不存在")

    if source_canvas.id != example.source_canvas_id or source_canvas.project_id != example.source_project_id:
        _validate_source_canvas_uniqueness(
            db,
            source_canvas_id=source_canvas.id,
            source_project_id=source_canvas.project_id,
            exclude_example_id=example.id,
        )

    preview_urls = example.preview_urls
    snapshot = _parse_snapshot(example.snapshot_json)
    if refresh_snapshot or source_canvas.id != example.source_canvas_id or source_canvas.project_id != example.source_project_id:
        snapshot, preview_urls = _build_example_snapshot(db, source_canvas)

    next_title = _normalize_title(title, fallback=example.title or source_canvas.name or "未命名示例项目")
    next_subtitle = _normalize_subtitle(subtitle, fallback=example.subtitle or "")
    next_cover_url = _normalize_cover_url(cover_url) or example.cover_url or (preview_urls[0] if preview_urls else "")

    example.source_canvas_id = source_canvas.id
    example.source_project_id = source_canvas.project_id
    example.title = next_title
    example.subtitle = next_subtitle
    example.cover_url = next_cover_url
    if sort_order is not None:
        example.sort_order = int(sort_order)
    if status_value is not None:
        example.status = _normalize_status(status_value, fallback=example.status)
    example.preview_urls_json = json.dumps(preview_urls, ensure_ascii=False)
    example.snapshot_json = json.dumps({**snapshot, "title": next_title}, ensure_ascii=False)
    example.updated_by = operator.id
    db.commit()
    db.refresh(example)
    return _serialize_example_project(example)


def delete_example_canvas_project(db: Session, *, example_id: int) -> None:
    example = db.query(ExampleCanvasProject).filter(ExampleCanvasProject.id == example_id).first()
    if not example:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="示例项目不存在")
    db.delete(example)
    db.commit()


def copy_example_canvas_project(db: Session, *, example_id: int, user_id: int) -> dict:
    example = (
        db.query(ExampleCanvasProject)
        .filter(ExampleCanvasProject.id == example_id, ExampleCanvasProject.status == "published")
        .first()
    )
    if not example:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="示例项目不存在或未发布")

    snapshot = _parse_snapshot(example.snapshot_json)
    nodes_snapshot = snapshot.get("nodes") or []
    groups_snapshot = snapshot.get("groups") or []
    edges_snapshot = snapshot.get("edges") or []

    canvas = UserCanvas(
        user_id=user_id,
        source_example_id=example.id,
        project_id=_generate_unique_project_id(db),
        name=_normalize_canvas_name(example.title or snapshot.get("title") or "示例项目"),
        viewport_x=float(snapshot.get("viewport_x") or 0),
        viewport_y=float(snapshot.get("viewport_y") or 0),
        zoom=float(snapshot.get("zoom") or 0.5),
    )
    db.add(canvas)
    db.flush()

    group_id_map: dict[int, int] = {}
    for group_snapshot in groups_snapshot:
        source_group_id = int(group_snapshot.get("source_id") or 0)
        if source_group_id <= 0:
            continue
        group = CanvasGroup(
            canvas_id=canvas.id,
            name=(group_snapshot.get("name") or "未命名分组").strip() or "未命名分组",
            color=(group_snapshot.get("color") or "#ffab27").strip() or "#ffab27",
            x=float(group_snapshot.get("x") or 0),
            y=float(group_snapshot.get("y") or 0),
            width=float(group_snapshot.get("width") or 320),
            height=float(group_snapshot.get("height") or 220),
            z_index=int(group_snapshot.get("z_index") or 1),
        )
        db.add(group)
        db.flush()
        group_id_map[source_group_id] = group.id

    node_id_map: dict[int, int] = {}
    for node_snapshot in nodes_snapshot:
        source_node_id = int(node_snapshot.get("source_id") or 0)
        if source_node_id <= 0:
            continue
        group_id = node_snapshot.get("group_id")
        node_type = (node_snapshot.get("node_type") or "text").strip() or "text"
        task_payload = node_snapshot.get("task") or {}
        task_id = None
        if node_type == "task" and isinstance(task_payload, dict):
            task = Task(
                user_id=user_id,
                board_id=None,
                canvas_id=canvas.id,
                model=(task_payload.get("model") or "").strip(),
                source=(task_payload.get("source") or "web").strip() or "web",
                mode=(task_payload.get("mode") or "generate").strip() or "generate",
                prompt=(task_payload.get("prompt") or "").strip(),
                num_images=max(int(task_payload.get("num_images") or 1), 1),
                size=(task_payload.get("size") or "3:4").strip() or "3:4",
                resolution=(task_payload.get("resolution") or "").strip(),
                custom_size=(task_payload.get("custom_size") or "").strip(),
                reference_images=json.dumps(task_payload.get("reference_images") or [], ensure_ascii=False),
                source_image=(task_payload.get("source_image") or "").strip(),
                mask_image=(task_payload.get("mask_image") or "").strip(),
                credit_cost=0,
                is_example_template_seed=True,
                status=(task_payload.get("status") or "success").strip() or "success",
                error_message=(task_payload.get("error_message") or "").strip(),
            )
            db.add(task)
            db.flush()
            task_id = task.id
            task_images = task_payload.get("images") or []
            if isinstance(task_images, list):
                for image_snapshot in task_images:
                    image_data = image_snapshot or {}
                    db.add(
                        Image(
                            task_id=task.id,
                            image_url=(image_data.get("image_url") or "").strip(),
                            preview_url=(image_data.get("preview_url") or "").strip(),
                            image_format=(image_data.get("image_format") or "").strip(),
                            image_size_bytes=int(image_data.get("image_size_bytes") or 0),
                            status=(image_data.get("status") or "success").strip() or "success",
                            error_message=(image_data.get("error_message") or "").strip(),
                            is_deleted=False,
                        )
                    )
        node = CanvasNode(
            canvas_id=canvas.id,
            group_id=group_id_map.get(int(group_id)) if group_id is not None else None,
            task_id=task_id,
            node_type=node_type,
            content=(node_snapshot.get("content") or "").strip() if node_type == "text" else "",
            image_url=(node_snapshot.get("image_url") or "").strip() if node_type == "image" else "",
            x=float(node_snapshot.get("x") or 0),
            y=float(node_snapshot.get("y") or 0),
            width=float(node_snapshot.get("width") or 320),
            height=float(node_snapshot.get("height") or 220),
            z_index=int(node_snapshot.get("z_index") or 1),
        )
        db.add(node)
        db.flush()
        node_id_map[source_node_id] = node.id

    for edge_snapshot in edges_snapshot:
        source_node_id = node_id_map.get(int(edge_snapshot.get("source_node_id") or 0))
        target_node_id = node_id_map.get(int(edge_snapshot.get("target_node_id") or 0))
        if not source_node_id or not target_node_id:
            continue
        db.add(
            CanvasEdge(
                canvas_id=canvas.id,
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                edge_type=(edge_snapshot.get("edge_type") or "reference").strip() or "reference",
                source_anchor=(edge_snapshot.get("source_anchor") or "auto").strip() or "auto",
                target_anchor=(edge_snapshot.get("target_anchor") or "auto").strip() or "auto",
                is_collapsed=bool(edge_snapshot.get("is_collapsed")),
            )
        )

    canvas.updated_at = now_local()
    db.commit()
    db.refresh(canvas)
    summary = _serialize_canvas_summary(
        canvas,
        get_canvas_node_count(db, canvas.id),
        _extract_preview_urls(snapshot),
    )
    return {"canvas": summary}
