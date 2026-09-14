from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.prompt_optimize_style import (
    PromptOptimizeStyleCreate,
    PromptOptimizeStyleOut,
    PromptOptimizeStyleStatusUpdate,
    PromptOptimizeStyleUpdate,
    PublicPromptOptimizeStyleOut,
)
from app.services.prompt_optimize_style_service import (
    create_prompt_optimize_style,
    delete_prompt_optimize_style,
    list_admin_prompt_optimize_styles,
    list_public_prompt_optimize_styles,
    set_prompt_optimize_style_default,
    update_prompt_optimize_style,
    update_prompt_optimize_style_status,
)

admin_router = APIRouter(prefix="/api/admin/prompt-optimize-styles", tags=["管理员提示词优化风格"])
public_router = APIRouter(prefix="/api/config", tags=["提示词优化风格"])


@public_router.get("/prompt-optimize-styles", response_model=list[PublicPromptOptimizeStyleOut])
def get_public_prompt_optimize_styles(
    db: Session = Depends(get_db),
):
    return list_public_prompt_optimize_styles(db)


@admin_router.get("", response_model=list[PromptOptimizeStyleOut])
def get_admin_prompt_optimize_styles(
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_admin_prompt_optimize_styles(db)


@admin_router.post("", response_model=PromptOptimizeStyleOut, status_code=status.HTTP_201_CREATED)
def create_admin_prompt_optimize_style(
    body: PromptOptimizeStyleCreate,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return create_prompt_optimize_style(
        db,
        name=body.name,
        description=body.description,
        style_prompt=body.style_prompt,
        sort_order=body.sort_order,
        status_value=body.status,
        is_default=body.is_default,
    )


@admin_router.put("/{style_id}", response_model=PromptOptimizeStyleOut)
def update_admin_prompt_optimize_style(
    style_id: int,
    body: PromptOptimizeStyleUpdate,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return update_prompt_optimize_style(
        db,
        style_id=style_id,
        name=body.name,
        description=body.description,
        style_prompt=body.style_prompt,
        sort_order=body.sort_order,
        status_value=body.status,
        is_default=body.is_default,
    )


@admin_router.patch("/{style_id}/status", response_model=PromptOptimizeStyleOut)
def patch_admin_prompt_optimize_style_status(
    style_id: int,
    body: PromptOptimizeStyleStatusUpdate,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return update_prompt_optimize_style_status(db, style_id=style_id, status_value=body.status)


@admin_router.post("/{style_id}/set-default", response_model=PromptOptimizeStyleOut)
def set_admin_prompt_optimize_style_default(
    style_id: int,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return set_prompt_optimize_style_default(db, style_id=style_id)


@admin_router.delete("/{style_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_prompt_optimize_style(
    style_id: int,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    delete_prompt_optimize_style(db, style_id=style_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
