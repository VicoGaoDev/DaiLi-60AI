import uuid
import shutil
from pathlib import Path
from app.config import settings


def save_upload_file(file_bytes: bytes, extension: str = "png") -> str:
    """Save bytes to uploads directory, return relative URL path."""
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{extension}"
    filepath = upload_dir / filename
    filepath.write_bytes(file_bytes)
    return f"/uploads/{filename}"


def save_file_from_path(src_path: str, extension: str = "png") -> str:
    """Copy a local file to uploads directory, return relative URL path."""
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{extension}"
    filepath = upload_dir / filename
    shutil.copy2(src_path, filepath)
    return f"/uploads/{filename}"
