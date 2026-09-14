from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_superadmin
from app.database import get_db
from app.models.user import User
from app.schemas.generation_scene_category import (
    GenerationSceneCategoryCreate,
    GenerationSceneCategoryOut,
    GenerationSceneCategoryStatusUpdate,
    GenerationSceneCategoryUpdate,
)
from app.services.generation_scene_category_service import (
    create_generation_scene_category,
    delete_generation_scene_category,
    list_admin_generation_scene_categories,
    update_generation_scene_category,
    update_generation_scene_category_status,
)

admin_router = APIRouter(prefix="/api/admin/generation-scene-categories", tags=["管理员生图场景分类"])


@admin_router.get("", response_model=list[GenerationSceneCategoryOut])
def get_admin_generation_scene_categories(
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return list_admin_generation_scene_categories(db)


@admin_router.post("", response_model=GenerationSceneCategoryOut, status_code=status.HTTP_201_CREATED)
def create_admin_generation_scene_category(
    body: GenerationSceneCategoryCreate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return create_generation_scene_category(
        db,
        name=body.name,
        description=body.description,
        scene_type=body.scene_type,
        scene_keys=body.scene_keys,
        sort_order=body.sort_order,
        status_value=body.status,
    )


@admin_router.put("/{category_id}", response_model=GenerationSceneCategoryOut)
def update_admin_generation_scene_category(
    category_id: int,
    body: GenerationSceneCategoryUpdate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return update_generation_scene_category(
        db,
        category_id=category_id,
        name=body.name,
        description=body.description,
        scene_type=body.scene_type,
        scene_keys=body.scene_keys,
        sort_order=body.sort_order,
        status_value=body.status,
    )


@admin_router.patch("/{category_id}/status", response_model=GenerationSceneCategoryOut)
def patch_admin_generation_scene_category_status(
    category_id: int,
    body: GenerationSceneCategoryStatusUpdate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return update_generation_scene_category_status(db, category_id=category_id, status_value=body.status)


@admin_router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_admin_generation_scene_category(
    category_id: int,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    delete_generation_scene_category(db, category_id=category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
