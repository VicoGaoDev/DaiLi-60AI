import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.image_service import get_image

router = APIRouter(prefix="/api/images", tags=["图片"])


def _build_download_filename(image_id: int, image_url: str, content_type: str = "") -> str:
    suffix = Path(urlparse(image_url).path).suffix
    if not suffix and content_type:
        suffix = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ""
    if not suffix:
        suffix = ".png"
    return f"banana_{image_id}{suffix}"


@router.get("/{image_id}/download")
def download_image(
    image_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    image = get_image(db, image_id)
    if image.task.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权下载此图片")
    if not image.image_url:
        raise HTTPException(status_code=404, detail="图片尚未生成")

    if image.image_url.startswith("http://") or image.image_url.startswith("https://"):
        try:
            with httpx.Client(timeout=settings.IMAGE_FETCH_TIMEOUT, follow_redirects=True) as client:
                remote = client.get(image.image_url)
            remote.raise_for_status()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"下载远程图片失败：{exc}") from exc

        media_type = remote.headers.get("content-type", "application/octet-stream")
        filename = _build_download_filename(image_id, image.image_url, media_type)
        return Response(
            content=remote.content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    url_path = image.image_url.lstrip("/")
    file_path = Path(settings.UPLOAD_DIR).parent / url_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="图片文件不存在")

    media_type = mimetypes.guess_type(file_path.name)[0] or "image/png"
    filename = _build_download_filename(image_id, image.image_url, media_type)
    return FileResponse(str(file_path), filename=filename, media_type=media_type)
