import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.config import settings
from app.services.cos_service import (
    ALLOWED_IMAGE_TYPES,
    MAX_UPLOAD_SIZE,
    create_upload_credential,
)
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/upload", tags=["文件上传"])


class UploadCredentialRequest(BaseModel):
    file_name: str
    file_size: int
    content_type: str
    purpose: str = "ref"


class UploadCredentialResponse(BaseModel):
    bucket: str
    region: str
    key: str
    upload_domain: str
    url: str
    tmp_secret_id: str
    tmp_secret_key: str
    session_token: str
    start_time: int | None = None
    expired_time: int


@router.post("")
async def upload_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="仅支持 JPG/PNG/WEBP/GIF 格式")

    data = await file.read()
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="文件大小不能超过 20 MB")

    ext = Path(file.filename or "img.jpg").suffix or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = Path(settings.UPLOAD_DIR) / "ref" / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    url = f"/uploads/ref/{filename}"
    return {"url": url}


@router.post("/credential", response_model=UploadCredentialResponse)
def get_upload_credential(
    body: UploadCredentialRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = user
    return create_upload_credential(
        db,
        purpose=body.purpose,
        file_name=body.file_name,
        file_size=body.file_size,
        content_type=body.content_type,
    )
