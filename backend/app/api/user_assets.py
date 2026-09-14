from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.user_asset import (
    UserAssetCategoryCreate,
    UserAssetCategoryListResponse,
    UserAssetCategorySummary,
    UserAssetCategoryUpdate,
    UserAssetCompleteRequest,
    UserAssetDeleteResponse,
    UserAssetImportRequest,
    UserAssetImportResponse,
    UserAssetListResponse,
    UserAssetQuota,
    UserAssetSummary,
    UserAssetUpdateRequest,
    UserAssetUploadSessionRequest,
    UserAssetUploadSessionResponse,
)
from app.services.user_asset_service import (
    complete_user_asset_upload,
    create_user_asset_category,
    create_user_asset_upload_session,
    delete_user_asset,
    delete_user_asset_category,
    get_user_asset_quota,
    import_user_asset_from_url,
    list_user_asset_categories,
    list_user_assets,
    update_user_asset,
    update_user_asset_category,
)

router = APIRouter(prefix="/api/user-assets", tags=["素材库"])
category_router = APIRouter(prefix="/api/user-assets/categories", tags=["素材分类"])


@category_router.get("", response_model=UserAssetCategoryListResponse)
def get_categories(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_user_asset_categories(db, user.id)


@category_router.post("", response_model=UserAssetCategorySummary, status_code=status.HTTP_201_CREATED)
def create_category(
    body: UserAssetCategoryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_user_asset_category(db, user.id, body.name)


@category_router.patch("/{category_id}", response_model=UserAssetCategorySummary)
def patch_category(
    category_id: int,
    body: UserAssetCategoryUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_user_asset_category(db, user.id, category_id, body.name)


@category_router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_category(
    category_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_user_asset_category(db, user.id, category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=UserAssetListResponse)
def get_assets(
    category_id: int | None = Query(default=None),
    keyword: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_user_assets(
        db,
        user.id,
        category_id=category_id,
        keyword=keyword,
        limit=limit,
    )


@router.get("/stats", response_model=UserAssetQuota)
def get_asset_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_user_asset_quota(db, user.id)


@router.post("/upload-session", response_model=UserAssetUploadSessionResponse, status_code=status.HTTP_201_CREATED)
def create_upload_session(
    body: UserAssetUploadSessionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_user_asset_upload_session(
        db,
        user.id,
        file_name=body.file_name,
        file_size=body.file_size,
        content_type=body.content_type,
        category_id=body.category_id,
    )


@router.post("/import", response_model=UserAssetImportResponse, status_code=status.HTTP_201_CREATED)
def import_asset(
    body: UserAssetImportRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return import_user_asset_from_url(
        db,
        user.id,
        image_url=body.image_url,
        file_name=body.file_name,
        category_id=body.category_id,
        width=body.width,
        height=body.height,
    )


@router.post("/{asset_id}/complete", response_model=UserAssetSummary)
def complete_upload(
    asset_id: int,
    body: UserAssetCompleteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return complete_user_asset_upload(
        db,
        user.id,
        asset_id,
        width=body.width,
        height=body.height,
    )


@router.patch("/{asset_id}", response_model=UserAssetSummary)
def patch_asset(
    asset_id: int,
    body: UserAssetUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payload = body.model_dump(exclude_unset=True)
    return update_user_asset(
        db,
        user.id,
        asset_id,
        category_id=payload.get("category_id"),
        update_category="category_id" in payload,
        file_name=payload.get("file_name"),
    )


@router.delete("/{asset_id}", response_model=UserAssetDeleteResponse)
def remove_asset(
    asset_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return delete_user_asset(db, user.id, asset_id)
