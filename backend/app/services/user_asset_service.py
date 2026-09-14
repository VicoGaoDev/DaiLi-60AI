from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models.user_asset import UserAsset
from app.models.user_asset_category import UserAssetCategory
from app.schemas.user_asset import UserAssetQuota
from app.services.cos_service import (
    build_cos_public_url,
    build_user_asset_object_key,
    create_upload_credential_for_key,
    delete_cos_object,
    get_cos_config,
    load_image_bytes,
    infer_mime_type,
    upload_bytes_to_cos,
    validate_image_upload_request,
)
from app.services.image_delivery_service import build_thumb_url, get_optional_cos_config
from app.utils.datetime_utils import now_local

logger = logging.getLogger(__name__)

USER_ASSET_LIMIT = 100
MAX_CATEGORY_NAME_LENGTH = 100
PENDING_ASSET_STATUS = "pending"
READY_ASSET_STATUS = "ready"
DELETED_ASSET_STATUS = "deleted"
STALE_PENDING_ASSET_TTL_MINUTES = max(int(settings.USER_ASSET_PENDING_TTL_MINUTES or 0), 1)
STALE_PENDING_ASSET_CLEANUP_BATCH_SIZE = max(int(settings.USER_ASSET_PENDING_CLEANUP_BATCH_SIZE or 0), 1)
UNCATEGORIZED_FILTER_ID = 0


def _normalize_category_name(name: str | None) -> str:
    normalized = (name or "").strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分类名称不能为空")
    if len(normalized) > MAX_CATEGORY_NAME_LENGTH:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"分类名称不能超过 {MAX_CATEGORY_NAME_LENGTH} 个字符")
    return normalized


def _active_asset_filter(query, user_id: int):
    return query.filter(
        UserAsset.user_id == user_id,
        UserAsset.is_deleted.is_(False),
    )


def _ready_asset_filter(query, user_id: int):
    return _active_asset_filter(query, user_id).filter(
        UserAsset.status == READY_ASSET_STATUS,
    )


def cleanup_stale_pending_assets(
    db: Session,
    *,
    user_id: int | None = None,
    limit: int = STALE_PENDING_ASSET_CLEANUP_BATCH_SIZE,
) -> int:
    cutoff = now_local() - timedelta(minutes=STALE_PENDING_ASSET_TTL_MINUTES)
    query = (
        db.query(UserAsset)
        .filter(
            UserAsset.is_deleted.is_(False),
            UserAsset.status == PENDING_ASSET_STATUS,
            UserAsset.completed_at.is_(None),
            UserAsset.created_at < cutoff,
        )
    )
    if user_id is not None:
        query = query.filter(UserAsset.user_id == user_id)
    stale_assets = (
        query.order_by(UserAsset.created_at.asc(), UserAsset.id.asc())
        .limit(max(int(limit or 0), 1))
        .all()
    )
    if not stale_assets:
        return 0

    deleted_at = now_local()
    cleaned_count = 0
    for asset in stale_assets:
        try:
            delete_cos_object(db, asset.object_key, ignore_missing=True)
        except HTTPException:
            logger.warning(
                "Failed to delete stale pending user asset object",
                extra={"asset_id": asset.id, "user_id": asset.user_id, "object_key": asset.object_key},
                exc_info=True,
            )
        asset.is_deleted = True
        asset.deleted_at = deleted_at
        asset.status = DELETED_ASSET_STATUS
        cleaned_count += 1
    if cleaned_count:
        db.commit()
    return cleaned_count


def get_user_asset_quota(db: Session, user_id: int) -> dict:
    # Clean up expired upload sessions before reporting visible quota.
    cleanup_stale_pending_assets(db, user_id=user_id)
    used = int(
        _ready_asset_filter(db.query(func.count(UserAsset.id)), user_id).scalar() or 0
    )
    remaining = max(USER_ASSET_LIMIT - used, 0)
    return UserAssetQuota(used=used, limit=USER_ASSET_LIMIT, remaining=remaining).model_dump()


def _get_user_asset_category_or_404(db: Session, user_id: int, category_id: int) -> UserAssetCategory:
    category = (
        db.query(UserAssetCategory)
        .filter(UserAssetCategory.id == category_id, UserAssetCategory.user_id == user_id)
        .first()
    )
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="素材分类不存在")
    return category


def _normalize_category_id(db: Session, user_id: int, category_id: int | None) -> int | None:
    if category_id in (None, UNCATEGORIZED_FILTER_ID):
        return None
    return _get_user_asset_category_or_404(db, user_id, category_id).id


def _serialize_user_asset(asset: UserAsset, *, cos_config=None) -> dict:
    image_url = (asset.url or "").strip()
    thumb_url = (asset.thumbnail_url or "").strip() or build_thumb_url(image_url, cos_config=cos_config)
    category_name = asset.category.name if asset.category else ""
    return {
        "id": asset.id,
        "category_id": asset.category_id,
        "category_name": category_name,
        "file_name": asset.file_name or "",
        "image_url": image_url,
        "thumb_url": thumb_url,
        "mime_type": asset.mime_type or "",
        "file_size": int(asset.file_size or 0),
        "width": asset.width,
        "height": asset.height,
        "status": asset.status or PENDING_ASSET_STATUS,
        "created_at": asset.created_at,
        "completed_at": asset.completed_at,
    }


def list_user_asset_categories(db: Session, user_id: int) -> dict:
    categories = (
        db.query(UserAssetCategory)
        .filter(UserAssetCategory.user_id == user_id)
        .order_by(UserAssetCategory.sort_order.asc(), UserAssetCategory.updated_at.desc(), UserAssetCategory.id.desc())
        .all()
    )
    stat_rows = (
        db.query(
            UserAsset.category_id,
            func.count(UserAsset.id).label("asset_count"),
        )
        .filter(
            UserAsset.user_id == user_id,
            UserAsset.is_deleted.is_(False),
            UserAsset.status == READY_ASSET_STATUS,
        )
        .group_by(UserAsset.category_id)
        .all()
    )
    count_map = {
        row.category_id: int(row.asset_count or 0)
        for row in stat_rows
    }

    preview_rows = (
        db.query(UserAsset)
        .options(joinedload(UserAsset.category))
        .filter(
            UserAsset.user_id == user_id,
            UserAsset.is_deleted.is_(False),
            UserAsset.status == READY_ASSET_STATUS,
        )
        .order_by(UserAsset.completed_at.desc(), UserAsset.id.desc())
        .limit(200)
        .all()
    )
    cos_config = get_optional_cos_config(db)
    preview_map: dict[int, list[str]] = {}
    uncategorized_count = count_map.get(None, 0)
    for asset in preview_rows:
        if asset.category_id is None:
            continue
        previews = preview_map.setdefault(asset.category_id, [])
        if len(previews) >= 3:
            continue
        thumb_url = _serialize_user_asset(asset, cos_config=cos_config)["thumb_url"]
        if thumb_url:
            previews.append(thumb_url)

    return {
        "items": [
            {
                "id": category.id,
                "name": category.name or "未命名分类",
                "sort_order": int(category.sort_order or 0),
                "asset_count": count_map.get(category.id, 0),
                "preview_urls": preview_map.get(category.id, []),
                "updated_at": category.updated_at,
            }
            for category in categories
        ],
        "uncategorized_count": uncategorized_count,
    }


def create_user_asset_category(db: Session, user_id: int, name: str) -> dict:
    normalized_name = _normalize_category_name(name)
    exists = (
        db.query(UserAssetCategory.id)
        .filter(UserAssetCategory.user_id == user_id, UserAssetCategory.name == normalized_name)
        .first()
    )
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分类名称已存在")

    max_sort_order = db.query(func.max(UserAssetCategory.sort_order)).filter(UserAssetCategory.user_id == user_id).scalar()
    category = UserAssetCategory(
        user_id=user_id,
        name=normalized_name,
        sort_order=int(max_sort_order or 0) + 1,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return {
        "id": category.id,
        "name": category.name,
        "sort_order": int(category.sort_order or 0),
        "asset_count": 0,
        "preview_urls": [],
        "updated_at": category.updated_at,
    }


def update_user_asset_category(db: Session, user_id: int, category_id: int, name: str) -> dict:
    category = _get_user_asset_category_or_404(db, user_id, category_id)
    normalized_name = _normalize_category_name(name)
    exists = (
        db.query(UserAssetCategory.id)
        .filter(
            UserAssetCategory.user_id == user_id,
            UserAssetCategory.name == normalized_name,
            UserAssetCategory.id != category.id,
        )
        .first()
    )
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分类名称已存在")

    category.name = normalized_name
    db.commit()
    db.refresh(category)
    return {
        "id": category.id,
        "name": category.name,
        "sort_order": int(category.sort_order or 0),
        "asset_count": 0,
        "preview_urls": [],
        "updated_at": category.updated_at,
    }


def delete_user_asset_category(db: Session, user_id: int, category_id: int) -> None:
    category = _get_user_asset_category_or_404(db, user_id, category_id)
    active_assets = (
        db.query(func.count(UserAsset.id))
        .filter(
            UserAsset.user_id == user_id,
            UserAsset.category_id == category.id,
            UserAsset.is_deleted.is_(False),
        )
        .scalar()
    )
    if int(active_assets or 0) > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该分类下仍有素材，请先删除或移动素材")
    db.delete(category)
    db.commit()


def list_user_assets(
    db: Session,
    user_id: int,
    *,
    category_id: int | None = None,
    keyword: str | None = None,
    limit: int = 100,
) -> dict:
    normalized_category_id = None if category_id is None else _normalize_category_id(db, user_id, category_id)
    trimmed_keyword = (keyword or "").strip()

    query = (
        db.query(UserAsset)
        .options(joinedload(UserAsset.category))
        .filter(
            UserAsset.user_id == user_id,
            UserAsset.is_deleted.is_(False),
            UserAsset.status == READY_ASSET_STATUS,
        )
    )
    if category_id == UNCATEGORIZED_FILTER_ID:
        query = query.filter(UserAsset.category_id.is_(None))
    elif normalized_category_id is not None:
        query = query.filter(UserAsset.category_id == normalized_category_id)
    if trimmed_keyword:
        query = query.filter(UserAsset.file_name.like(f"%{trimmed_keyword}%"))

    safe_limit = max(1, min(limit, 200))
    items = (
        query.order_by(UserAsset.completed_at.desc(), UserAsset.id.desc())
        .limit(safe_limit)
        .all()
    )
    total = int(query.order_by(None).count())
    cos_config = get_optional_cos_config(db)
    return {
        "items": [_serialize_user_asset(item, cos_config=cos_config) for item in items],
        "total": total,
        "quota": get_user_asset_quota(db, user_id),
    }


def create_user_asset_upload_session(
    db: Session,
    user_id: int,
    *,
    file_name: str,
    file_size: int,
    content_type: str,
    category_id: int | None = None,
) -> dict:
    validate_image_upload_request(file_name, file_size, content_type)
    normalized_category_id = _normalize_category_id(db, user_id, category_id)
    quota = get_user_asset_quota(db, user_id)
    if quota["used"] >= USER_ASSET_LIMIT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"素材库最多可上传 {USER_ASSET_LIMIT} 个素材，请删除后再试")

    object_key = build_user_asset_object_key(user_id=user_id, file_name=file_name, content_type=content_type)
    cos_config = get_cos_config(db)
    asset = UserAsset(
        user_id=user_id,
        category_id=normalized_category_id,
        file_name=(file_name or "").strip() or "未命名素材",
        object_key=object_key,
        url=build_cos_public_url(cos_config, object_key),
        mime_type=content_type,
        file_size=file_size,
        status=PENDING_ASSET_STATUS,
    )
    db.add(asset)
    db.flush()

    credential = create_upload_credential_for_key(db, key=object_key)
    db.commit()
    db.refresh(asset)
    return {
        "asset": _serialize_user_asset(asset, cos_config=cos_config),
        "quota": get_user_asset_quota(db, user_id),
        "credential": credential,
    }


def import_user_asset_from_url(
    db: Session,
    user_id: int,
    *,
    image_url: str,
    file_name: str,
    category_id: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> dict:
    normalized_image_url = (image_url or "").strip()
    if not normalized_image_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="图片地址不能为空")

    quota = get_user_asset_quota(db, user_id)
    if quota["used"] >= USER_ASSET_LIMIT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"素材库最多可上传 {USER_ASSET_LIMIT} 个素材，请删除后再试")

    normalized_category_id = _normalize_category_id(db, user_id, category_id)
    normalized_file_name = (file_name or "").strip() or "未命名素材"
    image_data = load_image_bytes(normalized_image_url)
    if not image_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="图片不存在或无法读取")
    data, mime_type = image_data
    content_type = (mime_type or "").strip() or infer_mime_type(normalized_file_name)
    validate_image_upload_request(normalized_file_name, len(data), content_type)

    object_key = build_user_asset_object_key(user_id=user_id, file_name=normalized_file_name, content_type=content_type)
    uploaded_url = upload_bytes_to_cos(
        db,
        data=data,
        key=object_key,
        content_type=content_type,
    )
    asset = UserAsset(
        user_id=user_id,
        category_id=normalized_category_id,
        file_name=normalized_file_name,
        object_key=object_key,
        url=uploaded_url,
        mime_type=content_type,
        file_size=len(data),
        width=width,
        height=height,
        status=READY_ASSET_STATUS,
        completed_at=now_local(),
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return {
        "asset": _serialize_user_asset(asset, cos_config=get_optional_cos_config(db)),
        "quota": get_user_asset_quota(db, user_id),
    }


def get_user_asset_or_404(db: Session, user_id: int, asset_id: int) -> UserAsset:
    asset = (
        db.query(UserAsset)
        .options(joinedload(UserAsset.category))
        .filter(
            UserAsset.id == asset_id,
            UserAsset.user_id == user_id,
            UserAsset.is_deleted.is_(False),
        )
        .first()
    )
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="素材不存在")
    return asset


def complete_user_asset_upload(
    db: Session,
    user_id: int,
    asset_id: int,
    *,
    width: int | None = None,
    height: int | None = None,
) -> dict:
    asset = get_user_asset_or_404(db, user_id, asset_id)
    if asset.status == READY_ASSET_STATUS:
        return _serialize_user_asset(asset, cos_config=get_optional_cos_config(db))

    cleanup_stale_pending_assets(db, user_id=user_id)
    ready_used = int(
        _ready_asset_filter(db.query(func.count(UserAsset.id)), user_id).scalar() or 0
    )
    if ready_used >= USER_ASSET_LIMIT:
        delete_cos_object(db, asset.object_key, ignore_missing=True)
        asset.is_deleted = True
        asset.deleted_at = now_local()
        asset.status = DELETED_ASSET_STATUS
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"素材库最多可保存 {USER_ASSET_LIMIT} 个素材，请删除后再试",
        )

    asset.status = READY_ASSET_STATUS
    asset.width = width
    asset.height = height
    asset.completed_at = now_local()
    db.commit()
    db.refresh(asset)
    return _serialize_user_asset(asset, cos_config=get_optional_cos_config(db))


def update_user_asset(
    db: Session,
    user_id: int,
    asset_id: int,
    *,
    category_id: int | None = None,
    update_category: bool = False,
    file_name: str | None = None,
) -> dict:
    asset = get_user_asset_or_404(db, user_id, asset_id)
    if update_category:
        asset.category_id = _normalize_category_id(db, user_id, category_id)
    if file_name is not None:
        normalized_file_name = file_name.strip()
        if not normalized_file_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="素材名称不能为空")
        asset.file_name = normalized_file_name
    db.commit()
    db.refresh(asset)
    return _serialize_user_asset(asset, cos_config=get_optional_cos_config(db))


def delete_user_asset(db: Session, user_id: int, asset_id: int) -> dict:
    asset = (
        db.query(UserAsset)
        .filter(UserAsset.id == asset_id, UserAsset.user_id == user_id)
        .first()
    )
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="素材不存在")
    if asset.is_deleted:
        return {"quota": get_user_asset_quota(db, user_id)}

    delete_cos_object(db, asset.object_key, ignore_missing=True)
    asset.is_deleted = True
    asset.deleted_at = now_local()
    asset.status = DELETED_ASSET_STATUS
    db.commit()
    return {"quota": get_user_asset_quota(db, user_id)}
