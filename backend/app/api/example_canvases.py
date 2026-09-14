from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.example_canvas import (
    ExampleCanvasCopyResponse,
    ExampleCanvasProjectCreate,
    ExampleCanvasProjectListResponse,
    ExampleCanvasProjectOut,
    ExampleCanvasProjectUpdate,
)
from app.services.example_canvas_service import (
    copy_example_canvas_project,
    create_example_canvas_project,
    delete_example_canvas_project,
    list_admin_example_canvas_projects,
    list_published_example_canvas_projects,
    update_example_canvas_project,
)

router = APIRouter(prefix="/api/canvases/example-projects", tags=["画布示例项目"])
admin_router = APIRouter(prefix="/api/admin/example-canvases", tags=["管理员示例画布"])


@router.get("", response_model=ExampleCanvasProjectListResponse)
def list_example_canvas_projects(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_published_example_canvas_projects(db)


@router.post("/{example_id}/copy", response_model=ExampleCanvasCopyResponse, status_code=status.HTTP_201_CREATED)
def copy_example_project(
    example_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return copy_example_canvas_project(db, example_id=example_id, user_id=user.id)


@admin_router.get("", response_model=ExampleCanvasProjectListResponse)
def admin_list_example_canvas_projects(
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_admin_example_canvas_projects(db)


@admin_router.post("", response_model=ExampleCanvasProjectOut, status_code=status.HTTP_201_CREATED)
def admin_create_example_canvas_project(
    body: ExampleCanvasProjectCreate,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return create_example_canvas_project(
        db,
        project_id=body.project_id,
        title=body.title,
        subtitle=body.subtitle,
        cover_url=body.cover_url,
        sort_order=body.sort_order,
        status_value=body.status,
        operator=user,
    )


@admin_router.put("/{example_id}", response_model=ExampleCanvasProjectOut)
def admin_update_example_canvas_project(
    example_id: int,
    body: ExampleCanvasProjectUpdate,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return update_example_canvas_project(
        db,
        example_id=example_id,
        project_id=body.project_id,
        title=body.title,
        subtitle=body.subtitle,
        cover_url=body.cover_url,
        sort_order=body.sort_order,
        status_value=body.status,
        refresh_snapshot=body.refresh_snapshot,
        operator=user,
    )


@admin_router.delete("/{example_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_example_canvas_project(
    example_id: int,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    delete_example_canvas_project(db, example_id=example_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
