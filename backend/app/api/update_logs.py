from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.update_log import (
    UpdateLogCreateRequest,
    UpdateLogListResponse,
    UpdateLogOut,
    UpdateLogUpdateRequest,
)
from app.services.update_log_service import (
    create_update_log,
    delete_update_log,
    get_admin_update_log_detail,
    get_public_update_log_detail,
    list_admin_update_logs,
    list_public_update_logs,
    update_update_log,
)

router = APIRouter(prefix="/api/update-logs", tags=["更新日志"])
admin_router = APIRouter(prefix="/api/admin/update-logs", tags=["管理员更新日志"])


@router.get("", response_model=UpdateLogListResponse)
def list_update_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return list_public_update_logs(db, page=page, page_size=page_size)


@router.get("/{log_id}", response_model=UpdateLogOut)
def get_update_log_detail(
    log_id: str,
    db: Session = Depends(get_db),
):
    return get_public_update_log_detail(db, log_id)


@admin_router.get("", response_model=UpdateLogListResponse)
def admin_list_update_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_admin_update_logs(db, page=page, page_size=page_size)


@admin_router.post("", response_model=UpdateLogOut, status_code=status.HTTP_201_CREATED)
def admin_create_update_log(
    body: UpdateLogCreateRequest,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return create_update_log(
        db,
        title=body.title,
        content=body.content,
        tag_type=body.tag_type,
        effective_at=body.effective_at,
    )


@admin_router.get("/{log_id}", response_model=UpdateLogOut)
def admin_get_update_log_detail(
    log_id: str,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return get_admin_update_log_detail(db, log_id)


@admin_router.put("/{log_id}", response_model=UpdateLogOut)
def admin_update_update_log(
    log_id: str,
    body: UpdateLogUpdateRequest,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return update_update_log(
        db,
        log_id=log_id,
        title=body.title,
        content=body.content,
        tag_type=body.tag_type,
        effective_at=body.effective_at,
    )


@admin_router.delete("/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_update_log(
    log_id: str,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    delete_update_log(db, log_id=log_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
