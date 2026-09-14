import base64
import mimetypes
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models.api_key import ApiKey

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MB
USER_ASSET_PREFIX = "user_assets"
UPLOAD_PURPOSE_PREFIXES = {
    "ref": "ref",
    "chat": "chat",
    "source": "source",
    "mask": "mask",
    "reverse": "reverse",
    "misc": "misc",
    "contact_qr": "contact_qr",
    "canvas_upload": "canvas_upload",
    "user_suggestion": "user_suggestion",
    "admin_ledger": "admin_ledger",
    "canvas": "canvas",
    "template": "template",
    "avatar": "avatar",
    "generated": "generated",
}
PUT_OBJECT_ACTIONS = [
    "name/cos:PutObject",
    "name/cos:InitiateMultipartUpload",
    "name/cos:UploadPart",
    "name/cos:CompleteMultipartUpload",
]


@dataclass
class CosRuntimeConfig:
    secret_id: str
    secret_key: str
    bucket: str
    region: str
    upload_domain: str
    public_base_url: str
    app_id: str


def _normalize_cos_base_url(value: str, bucket: str, region: str) -> str:
    if value.strip():
        return value.strip().rstrip("/")
    return f"https://{bucket}.cos.{region}.myqcloud.com"


def _normalize_cos_upload_domain(value: str, bucket: str, region: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return f"{bucket}.cos.{region}.myqcloud.com"
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    return (parsed.netloc or parsed.path).strip().rstrip("/")


def _extract_domain_from_url(value: str, fallback: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return fallback
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    return (parsed.netloc or parsed.path).strip().rstrip("/") or fallback


def _extract_app_id(bucket: str) -> str:
    _, sep, app_id = bucket.rpartition("-")
    if not sep or not app_id.isdigit():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="COS Bucket 配置不正确，需包含 AppId 后缀",
        )
    return app_id


def get_cos_config(db: Session) -> CosRuntimeConfig:
    record = db.query(ApiKey).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先在配置管理中填写 COS 配置")

    secret_id = (record.cos_secret_id or "").strip()
    secret_key = (record.cos_secret_key or "").strip()
    bucket = (record.cos_bucket or "").strip()
    region = (record.cos_region or "").strip()
    if not all([secret_id, secret_key, bucket, region]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="COS 配置不完整，请先补齐 SecretId、SecretKey、Bucket、Region")

    return CosRuntimeConfig(
        secret_id=secret_id,
        secret_key=secret_key,
        bucket=bucket,
        region=region,
        upload_domain=_normalize_cos_upload_domain(record.cos_upload_domain or "", bucket, region),
        public_base_url=_normalize_cos_base_url(record.cos_public_base_url or "", bucket, region),
        app_id=_extract_app_id(bucket),
    )


def build_cos_public_url(config: CosRuntimeConfig, key: str) -> str:
    encoded_key = quote(key.lstrip("/"), safe="/")
    return f"{config.public_base_url}/{encoded_key}"


def infer_mime_type(file_name: str, fallback: str = "image/jpeg") -> str:
    guessed, _ = mimetypes.guess_type(file_name)
    return guessed or fallback


def _normalize_ext(file_name: str, content_type: str) -> str:
    suffix = Path(file_name or "").suffix.lower()
    if suffix:
        return suffix
    if content_type == "image/png":
        return ".png"
    if content_type == "image/webp":
        return ".webp"
    if content_type == "image/gif":
        return ".gif"
    return ".jpg"


def validate_image_upload_request(file_name: str, file_size: int, content_type: str) -> None:
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 JPG/PNG/WEBP/GIF 格式")
    if file_size <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件大小无效")
    if file_size > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件大小不能超过 20 MB")
    if not Path(file_name or "").name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件名不能为空")


def validate_upload_request(file_name: str, file_size: int, content_type: str, purpose: str) -> None:
    if purpose not in UPLOAD_PURPOSE_PREFIXES or purpose == "generated":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的上传用途")
    validate_image_upload_request(file_name, file_size, content_type)


def build_object_key(purpose: str, file_name: str, content_type: str = "image/jpeg") -> str:
    prefix = UPLOAD_PURPOSE_PREFIXES.get(purpose)
    if not prefix:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的上传用途")
    ext = _normalize_ext(file_name, content_type)
    return f"{prefix}/{uuid.uuid4().hex}{ext}"


def build_user_asset_object_key(*, user_id: int, file_name: str, content_type: str = "image/jpeg") -> str:
    ext = _normalize_ext(file_name, content_type)
    return f"{USER_ASSET_PREFIX}/{user_id}/{uuid.uuid4().hex}{ext}"


def create_upload_credential_for_key(db: Session, *, key: str) -> dict:
    config = get_cos_config(db)
    resource = f"qcs::cos:{config.region}:uid/{config.app_id}:{config.bucket}/{key}"

    try:
        from sts.sts import Sts
    except ImportError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="服务端缺少 COS STS 依赖") from exc

    policy = {
        "version": "2.0",
        "statement": [{
            "action": PUT_OBJECT_ACTIONS,
            "effect": "allow",
            "resource": [resource],
        }],
    }
    options = {
        "secret_id": config.secret_id,
        "secret_key": config.secret_key,
        "bucket": config.bucket,
        "region": config.region,
        "duration_seconds": settings.COS_STS_DURATION_SECONDS,
        "policy": policy,
    }

    try:
        response = dict(Sts(options).get_credential())
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"获取 COS 临时凭证失败：{exc}") from exc

    credentials = response.get("credentials") or {}
    tmp_secret_id = credentials.get("tmpSecretId") or response.get("tmpSecretId")
    tmp_secret_key = credentials.get("tmpSecretKey") or response.get("tmpSecretKey")
    token = credentials.get("sessionToken") or response.get("sessionToken") or response.get("token")
    expired_time = response.get("expiredTime") or response.get("expiration")
    start_time = response.get("startTime")
    if not all([tmp_secret_id, tmp_secret_key, token, expired_time]):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="COS 临时凭证返回内容不完整")

    return {
        "bucket": config.bucket,
        "region": config.region,
        "key": key,
        "upload_domain": _extract_domain_from_url(config.public_base_url, config.upload_domain),
        "url": build_cos_public_url(config, key),
        "tmp_secret_id": tmp_secret_id,
        "tmp_secret_key": tmp_secret_key,
        "session_token": token,
        "start_time": int(start_time) if start_time is not None else None,
        "expired_time": int(expired_time),
    }


def create_upload_credential(
    db: Session,
    *,
    purpose: str,
    file_name: str,
    file_size: int,
    content_type: str,
) -> dict:
    validate_upload_request(file_name, file_size, content_type, purpose)
    key = build_object_key(purpose, file_name, content_type)
    return create_upload_credential_for_key(db, key=key)


def upload_bytes_to_cos(
    db: Session,
    *,
    data: bytes,
    key: str,
    content_type: str = "image/png",
    cache_control: str | None = None,
) -> str:
    config = get_cos_config(db)
    try:
        from qcloud_cos import CosConfig, CosS3Client
    except ImportError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="服务端缺少 COS 上传依赖") from exc

    client = CosS3Client(
        CosConfig(
            Region=config.region,
            SecretId=config.secret_id,
            SecretKey=config.secret_key,
            Domain=config.upload_domain,
            Scheme="https",
        )
    )
    try:
        extra_args = {
            "Bucket": config.bucket,
            "Body": data,
            "Key": key,
            "ContentType": content_type,
            "EnableMD5": False,
        }
        if cache_control:
            extra_args["CacheControl"] = cache_control
        client.put_object(
            **extra_args,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"上传图片到 COS 失败：{exc}") from exc
    return build_cos_public_url(config, key)


def delete_cos_object(db: Session, key: str, *, ignore_missing: bool = False) -> None:
    normalized_key = (key or "").strip().lstrip("/")
    if not normalized_key:
        return
    config = get_cos_config(db)
    try:
        from qcloud_cos import CosConfig, CosS3Client
    except ImportError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="服务端缺少 COS 上传依赖") from exc

    client = CosS3Client(
        CosConfig(
            Region=config.region,
            SecretId=config.secret_id,
            SecretKey=config.secret_key,
            Domain=config.upload_domain,
            Scheme="https",
        )
    )
    try:
        client.delete_object(Bucket=config.bucket, Key=normalized_key)
    except Exception as exc:
        message = str(exc)
        if ignore_missing and any(token in message for token in ["NoSuchKey", "NoSuchResource", "404"]):
            return
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"删除 COS 对象失败：{exc}") from exc


def load_image_bytes(image_url: str) -> tuple[bytes, str] | None:
    if not image_url:
        return None

    parsed = urlparse(image_url)
    if parsed.scheme in {"http", "https"}:
        response: httpx.Response | None = None
        for attempt in range(4):
            try:
                with httpx.Client(timeout=settings.IMAGE_FETCH_TIMEOUT, follow_redirects=True) as client:
                    response = client.get(image_url)
                response.raise_for_status()
                break
            except Exception:
                if attempt == 3:
                    return None
                time.sleep(5)
        mime_type = response.headers.get("content-type", "").split(";")[0].strip() or infer_mime_type(parsed.path)
        return response.content, mime_type

    relative = image_url.strip().lstrip("/")
    if relative.startswith("uploads/"):
        relative = relative[len("uploads/"):]
    file_path = Path(settings.UPLOAD_DIR) / relative
    if not file_path.exists():
        return None
    mime_type = infer_mime_type(file_path.name)
    return file_path.read_bytes(), mime_type


def load_image_as_data_url(image_url: str) -> str:
    result = load_image_bytes(image_url)
    if not result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="图片不存在或尚未上传成功")
    data, mime_type = result
    encoded = base64.b64encode(data).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"
