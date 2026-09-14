from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.image import Image
from app.models.regenerate_log import RegenerateLog


def get_image(db: Session, image_id: int) -> Image:
    image = db.query(Image).filter(Image.id == image_id, Image.is_deleted.is_(False)).first()
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图片不存在")
    return image


def request_regenerate(
    db: Session,
    image_id: int,
    user_id: int,
    *,
    queued: bool = True,
) -> Image:
    image = db.query(Image).filter(Image.id == image_id, Image.is_deleted.is_(False)).first()
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图片不存在")

    if image.task.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作此图片")

    log = RegenerateLog(image_id=image.id, old_image_url=image.image_url)
    db.add(log)

    image.task.status = "queued" if queued else "pending"
    image.task.error_message = ""
    image.task.provider_api_config_id = None
    image.task.provider_task_id = ""
    image.task.provider_status = ""
    image.task.provider_error_message = ""
    image.task.provider_response_preview = ""
    image.task.poll_count = 0
    image.task.last_polled_at = None
    image.task.next_poll_at = None
    image.task.provider_started_at = None
    image.status = "pending"
    image.error_message = ""
    image.image_url = ""
    image.preview_url = ""
    db.commit()
    db.refresh(image)
    return image


def restore_regenerate_request(
    db: Session,
    image_id: int,
    *,
    error_message: str,
) -> Image | None:
    image = db.query(Image).filter(Image.id == image_id, Image.is_deleted.is_(False)).first()
    if not image:
        return None

    log = (
        db.query(RegenerateLog)
        .filter(RegenerateLog.image_id == image_id, RegenerateLog.new_image_url == "")
        .order_by(RegenerateLog.created_at.desc(), RegenerateLog.id.desc())
        .first()
    )
    restored_image_url = (log.old_image_url or "").strip() if log else ""
    normalized_error = (error_message or "重新生成任务入队失败").strip()

    image.image_url = restored_image_url
    image.preview_url = ""
    image.status = "success" if restored_image_url else "failed"
    image.error_message = "" if restored_image_url else normalized_error

    task = image.task
    visible_statuses = [item.status for item in task.images if not item.is_deleted]
    if any(status_value in {"pending", "queued", "processing"} for status_value in visible_statuses):
        task.status = "processing"
        task.error_message = normalized_error
    elif visible_statuses and all(status_value == "success" for status_value in visible_statuses):
        task.status = "success"
        task.error_message = ""
    else:
        task.status = "failed"
        task.error_message = normalized_error

    db.commit()
    db.refresh(image)
    return image


def delete_image_for_user(db: Session, image_id: int, user_id: int) -> bool:
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        return False
    task = image.task
    if task.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作此图片所属任务")
    if task.is_deleted:
        return True

    task.is_deleted = True
    db.commit()
    return True
