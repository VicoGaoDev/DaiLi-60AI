from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.user_api_key import (
    UserApiKeyCreateRequest,
    UserApiKeyListResponse,
    UserApiKeyOut,
    UserApiKeyResetResponse,
    UserApiKeyUpdateRequest,
)
from app.services.user_api_key_service import (
    create_user_api_key,
    list_user_api_keys,
    reset_user_api_key,
    soft_delete_user_api_key,
    update_user_api_key,
)

router = APIRouter(prefix="/api/user-api-keys", tags=["用户 API Key"])


@router.get("", response_model=UserApiKeyListResponse)
def list_my_api_keys(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"items": list_user_api_keys(db, user)}


@router.post("", response_model=UserApiKeyOut)
def create_my_api_key(
    body: UserApiKeyCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_user_api_key(
        db,
        user,
        key_name=body.key_name,
        expire_time=body.expire_time,
    )


@router.patch("/{key_id}", response_model=UserApiKeyOut)
def update_my_api_key(
    key_id: int,
    body: UserApiKeyUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    provided_fields = body.model_fields_set
    return update_user_api_key(
        db,
        user,
        key_id,
        key_name=body.key_name if "key_name" in provided_fields else None,
        status_value=body.status if "status" in provided_fields else None,
        expire_time=body.expire_time,
        expire_time_provided="expire_time" in provided_fields,
    )


@router.delete("/{key_id}")
def delete_my_api_key(
    key_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    soft_delete_user_api_key(db, user, key_id)
    return {"ok": True}


@router.post("/{key_id}/reset", response_model=UserApiKeyResetResponse)
def reset_my_api_key(
    key_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"item": reset_user_api_key(db, user, key_id)}
