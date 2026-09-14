from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_superadmin
from app.database import get_db
from app.models.api_key import ApiKey
from app.models.user import User
from app.schemas.api_key import (
    AdminConfigOut,
    AdminConfigUpdate,
    AnnouncementConfigOut,
    CosConfigOut,
    CosConfigUpdate,
    ExternalApiSecretConfigOut,
    ExternalApiSecretConfigUpdate,
)
from app.utils.datetime_utils import now_local

router = APIRouter(prefix="/api/admin/api-key", tags=["API Key 管理"])
cos_router = APIRouter(prefix="/api/admin/cos-config", tags=["COS 配置"])
secret_router = APIRouter(prefix="/api/admin/external-api-secrets", tags=["接口密钥配置"])
public_router = APIRouter(prefix="/api/config", tags=["公开配置"])


def _get_record(db: Session) -> ApiKey | None:
    return db.query(ApiKey).first()


def _get_or_create_record(db: Session) -> ApiKey:
    record = _get_record(db)
    if record:
        return record
    record = ApiKey()
    db.add(record)
    db.flush()
    return record


@public_router.get("/contact")
def get_contact_config(db: Session = Depends(get_db)):
    record = _get_record(db)
    return {"contact_qr_image": record.contact_qr_image if record else ""}


@public_router.get("/announcement", response_model=AnnouncementConfigOut)
def get_announcement_config(db: Session = Depends(get_db)):
    record = _get_record(db)
    if not record:
        return AnnouncementConfigOut()
    return AnnouncementConfigOut(
        announcement_enabled=bool(record.announcement_enabled),
        announcement_content=record.announcement_content or "",
        announcement_updated_at=record.announcement_updated_at,
    )


@router.get("", response_model=AdminConfigOut | None)
def get_api_key(
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _get_record(db)


@router.put("", response_model=AdminConfigOut)
def set_api_key(
    body: AdminConfigUpdate,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    record = _get_or_create_record(db)
    normalized_announcement_content = body.announcement_content.strip()
    announcement_changed = (
        bool(record.announcement_enabled) != bool(body.announcement_enabled)
        or (record.announcement_content or "") != normalized_announcement_content
    )
    record.contact_qr_image = body.contact_qr_image
    record.announcement_enabled = 1 if body.announcement_enabled else 0
    record.announcement_content = normalized_announcement_content
    if announcement_changed:
        record.announcement_updated_at = now_local()
    elif not record.announcement_updated_at and (body.announcement_enabled or normalized_announcement_content):
        record.announcement_updated_at = now_local()
    db.commit()
    db.refresh(record)
    return record


@router.delete("")
def delete_api_key(
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    record = _get_record(db)
    if record:
        record.contact_qr_image = ""
        record.announcement_enabled = 0
        record.announcement_content = ""
        record.announcement_updated_at = None
        db.commit()
    return {"detail": "已删除"}


@secret_router.get("", response_model=ExternalApiSecretConfigOut | None)
def get_external_api_secrets(
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return _get_record(db)


@secret_router.put("", response_model=ExternalApiSecretConfigOut)
def set_external_api_secrets(
    body: ExternalApiSecretConfigUpdate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    record = _get_or_create_record(db)
    record.key = body.key
    record.tongyi_key = body.tongyi_key
    db.commit()
    db.refresh(record)
    return record


@cos_router.get("", response_model=CosConfigOut | None)
def get_cos_config_endpoint(
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return _get_record(db)


@cos_router.put("", response_model=CosConfigOut)
def set_cos_config(
    body: CosConfigUpdate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    record = _get_or_create_record(db)
    record.cos_secret_id = body.cos_secret_id
    record.cos_secret_key = body.cos_secret_key
    record.cos_bucket = body.cos_bucket
    record.cos_region = body.cos_region
    record.cos_upload_domain = body.cos_upload_domain
    record.cos_public_base_url = body.cos_public_base_url
    db.commit()
    db.refresh(record)
    return record


@cos_router.delete("")
def delete_cos_config(
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    record = _get_record(db)
    if record:
        record.cos_secret_id = ""
        record.cos_secret_key = ""
        record.cos_bucket = ""
        record.cos_region = ""
        record.cos_upload_domain = ""
        record.cos_public_base_url = ""
        db.commit()
    return {"detail": "已删除"}
