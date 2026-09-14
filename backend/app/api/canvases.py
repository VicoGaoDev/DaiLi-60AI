import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.canvas import (
    CanvasCreate,
    CanvasDetail,
    CanvasEdgeOut,
    CanvasEdgeUpdate,
    CanvasFreeNodeCreate,
    CanvasGroupAssignNodesRequest,
    CanvasGroupAssignNodesResponse,
    CanvasGroupCreate,
    CanvasGroupCreateResponse,
    CanvasGroupOut,
    CanvasGroupRemoveNodesResponse,
    CanvasGroupUpdate,
    CanvasListResponse,
    CanvasNodeBatchUpdate,
    CanvasNodeBatchUpdateResponse,
    CanvasNodeOut,
    CanvasNodeUpdate,
    CanvasSummary,
    CanvasTaskCreate,
    CanvasTaskCreateResponse,
    CanvasVideoTaskCreate,
    CanvasUpdate,
    CanvasViewportUpdate,
)
from app.services.business_id_service import task_external_id, user_external_id
from app.services.canvas_service import (
    assign_nodes_to_canvas_group,
    create_canvas_generation_tasks,
    create_canvas_group,
    create_canvas_free_node,
    create_user_canvas,
    create_canvas_video_tasks,
    delete_canvas_group,
    delete_canvas_node,
    delete_user_canvas,
    get_canvas_detail,
    list_user_canvases,
    remove_nodes_from_canvas_groups,
    update_canvas_node,
    update_canvas_nodes_batch,
    update_canvas_group,
    update_canvas_edge,
    update_canvas_viewport,
    update_user_canvas,
)
from app.services.external_api_config_service import (
    SCENE_INPAINT,
    get_default_generation_model_key,
    require_scene_config,
)
from app.services.video_external_api_config_service import require_video_scene_config
from app.services.task_service import (
    mark_tasks_dispatched,
    mark_tasks_enqueue_failed,
    mark_tasks_queued,
)
from app.services.video_task_service import (
    mark_video_tasks_dispatched,
    mark_video_tasks_enqueue_failed,
    mark_video_tasks_queued,
)

router = APIRouter(prefix="/api/canvases", tags=["无限画布"])
canvas_logger = logging.getLogger("app.canvas")


@router.get("", response_model=CanvasListResponse)
def list_canvases(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None),
):
    return list_user_canvases(db, user.id, page=page, page_size=page_size, keyword=keyword)


@router.post("", response_model=CanvasSummary, status_code=status.HTTP_201_CREATED)
def create_canvas(
    body: CanvasCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_user_canvas(db, user.id, body.name)


@router.get("/{project_id}", response_model=CanvasDetail)
def get_canvas(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_canvas_detail(db, user.id, project_id, allow_admin_read=user.role in {"admin", "superadmin"})


@router.patch("/{project_id}", response_model=CanvasSummary)
def update_canvas(
    project_id: str,
    body: CanvasUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_user_canvas(
        db,
        user.id,
        project_id,
        name=body.name,
        viewport_x=body.viewport_x,
        viewport_y=body.viewport_y,
        zoom=body.zoom,
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_canvas(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_user_canvas(db, user.id, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{project_id}/viewport", response_model=CanvasSummary)
def update_viewport(
    project_id: str,
    body: CanvasViewportUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_canvas_viewport(
        db,
        user.id,
        project_id,
        viewport_x=body.viewport_x,
        viewport_y=body.viewport_y,
        zoom=body.zoom,
    )


@router.patch("/{project_id}/nodes/batch", response_model=CanvasNodeBatchUpdateResponse)
def update_nodes_batch(
    project_id: str,
    body: CanvasNodeBatchUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_canvas_nodes_batch(db, user.id, project_id, updates=body.nodes)


@router.patch("/{project_id}/nodes/{node_id}", response_model=CanvasNodeOut)
def update_node(
    project_id: str,
    node_id: int,
    body: CanvasNodeUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_canvas_node(
        db,
        user.id,
        project_id,
        node_id,
        x=body.x,
        y=body.y,
        width=body.width,
        height=body.height,
        z_index=body.z_index,
        content=body.content,
    )


@router.post("/{project_id}/groups", response_model=CanvasGroupCreateResponse, status_code=status.HTTP_201_CREATED)
def create_group(
    project_id: str,
    body: CanvasGroupCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_canvas_group(
        db,
        user.id,
        project_id,
        name=body.name,
        color=body.color,
        node_ids=body.node_ids,
        node_updates=body.nodes,
        x=body.x,
        y=body.y,
        width=body.width,
        height=body.height,
        z_index=body.z_index,
    )


@router.patch("/{project_id}/groups/{group_id}", response_model=CanvasGroupOut)
def update_group(
    project_id: str,
    group_id: int,
    body: CanvasGroupUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_canvas_group(
        db,
        user.id,
        project_id,
        group_id,
        name=body.name,
        color=body.color,
        x=body.x,
        y=body.y,
        width=body.width,
        height=body.height,
        z_index=body.z_index,
    )


@router.post("/{project_id}/groups/{group_id}/nodes", response_model=CanvasGroupAssignNodesResponse)
def assign_group_nodes(
    project_id: str,
    group_id: int,
    body: CanvasGroupAssignNodesRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return assign_nodes_to_canvas_group(
        db,
        user.id,
        project_id,
        group_id,
        node_updates=body.nodes,
    )


@router.post("/{project_id}/groups/nodes/remove", response_model=CanvasGroupRemoveNodesResponse)
def remove_group_nodes(
    project_id: str,
    body: CanvasGroupAssignNodesRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return remove_nodes_from_canvas_groups(
        db,
        user.id,
        project_id,
        node_updates=body.nodes,
    )


@router.delete("/{project_id}/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    project_id: str,
    group_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_canvas_group(db, user.id, project_id, group_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{project_id}/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node(
    project_id: str,
    node_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_canvas_node(db, user.id, project_id, node_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{project_id}/edges/{edge_id}", response_model=CanvasEdgeOut)
def update_edge(
    project_id: str,
    edge_id: int,
    body: CanvasEdgeUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_canvas_edge(
        db,
        user.id,
        project_id,
        edge_id,
        is_collapsed=body.is_collapsed,
    )


@router.post("/{project_id}/nodes", response_model=CanvasNodeOut, status_code=status.HTTP_201_CREATED)
def create_free_node(
    project_id: str,
    body: CanvasFreeNodeCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_canvas_free_node(
        db,
        user.id,
        project_id,
        node_type=body.node_type,
        content=body.content,
        image_url=body.image_url,
        x=body.x,
        y=body.y,
        width=body.width,
        height=body.height,
    )


@router.post("/{project_id}/tasks", response_model=CanvasTaskCreateResponse, status_code=status.HTTP_201_CREATED)
def create_canvas_task(
    project_id: str,
    body: CanvasTaskCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.mode == "inpaint":
        require_scene_config(db, SCENE_INPAINT)
        task_model = SCENE_INPAINT
        resolved_resolution = body.resolution
    else:
        task_model = body.model.strip() or get_default_generation_model_key(db)
        require_scene_config(db, task_model)
        resolved_resolution = "" if task_model == "banana" else body.resolution

    try:
        from app.workers.generation import dispatch_generation_task, get_generation_dispatch_mode

        dispatch_mode = get_generation_dispatch_mode()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    tasks, nodes = create_canvas_generation_tasks(
        db,
        user.id,
        project_id,
        model=task_model,
        source=body.source,
        mode=body.mode,
        prompt=body.prompt,
        num_images=body.num_images,
        size=body.size,
        resolution=resolved_resolution,
        custom_size=body.custom_size,
        reference_images=body.reference_images,
        source_node_ids=body.source_node_ids,
        source_image=body.source_image,
        mask_image=body.mask_image,
        x=body.x,
        y=body.y,
        width=body.width,
        height=body.height,
    )

    dispatched_task_ids: list[int] = []
    try:
        for task in tasks:
            actual_dispatch_mode = dispatch_generation_task(task.id)
            dispatched_task_ids.append(task.id)
            canvas_logger.info(
                "canvas task dispatched",
                extra={
                    "event": "canvas.task.dispatch.sent",
                    "user_id": user_external_id(user),
                    "project_id": project_id,
                    "task_id": task_external_id(task),
                    "dispatch_mode": actual_dispatch_mode,
                },
            )
        mark_tasks_dispatched(db, dispatched_task_ids)
        if dispatch_mode == "celery":
            mark_tasks_queued(db, dispatched_task_ids)
    except Exception as exc:
        failed_task_ids = [task.id for task in tasks if task.id not in set(dispatched_task_ids)]
        mark_tasks_enqueue_failed(db, failed_task_ids, error_message=str(exc))
        if not dispatched_task_ids:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="任务队列暂不可用，请稍后重试",
            ) from exc

    task_ids = [task_external_id(task) for task in tasks]
    return CanvasTaskCreateResponse(task_id=task_ids[0] if task_ids else None, task_ids=task_ids, nodes=nodes)


@router.post("/{project_id}/video-tasks", response_model=CanvasTaskCreateResponse, status_code=status.HTTP_201_CREATED)
def create_canvas_video_task(
    project_id: str,
    body: CanvasVideoTaskCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task_model = (body.model or "").strip()
    if not task_model:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择视频模型")
    require_video_scene_config(db, task_model)

    tasks, nodes = create_canvas_video_tasks(
        db,
        user.id,
        project_id,
        model=task_model,
        source=body.source,
        prompt=body.prompt,
        duration_seconds=body.duration_seconds,
        aspect_ratio=body.aspect_ratio,
        resolution=body.resolution,
        reference_images=body.reference_images,
        source_node_ids=body.source_node_ids,
        x=body.x,
        y=body.y,
        width=body.width,
        height=body.height,
    )

    dispatched_task_ids: list[int] = []
    try:
        from app.workers.video_generation import dispatch_video_generation_task

        for task in tasks:
            dispatch_mode = dispatch_video_generation_task(task.id)
            dispatched_task_ids.append(task.id)
            canvas_logger.info(
                "canvas video task dispatched",
                extra={
                    "event": "canvas.video_task.dispatch.sent",
                    "user_id": user_external_id(user),
                    "project_id": project_id,
                    "task_id": task.business_id,
                    "dispatch_mode": dispatch_mode,
                },
            )
        mark_video_tasks_dispatched(db, dispatched_task_ids)
        mark_video_tasks_queued(db, dispatched_task_ids)
    except Exception as exc:
        failed_task_ids = [task.id for task in tasks if task.id not in set(dispatched_task_ids)]
        mark_video_tasks_enqueue_failed(db, failed_task_ids, error_message=str(exc))
        if not dispatched_task_ids:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="视频任务队列暂不可用，请稍后重试",
            ) from exc

    task_ids = [task.business_id for task in tasks]
    return CanvasTaskCreateResponse(task_id=task_ids[0] if task_ids else None, task_ids=task_ids, nodes=nodes)
