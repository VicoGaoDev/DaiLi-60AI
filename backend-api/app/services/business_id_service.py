from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.feedback import Feedback
from app.models.system_message import SystemMessage
from app.models.task import Task
from app.models.user import User
from app.utils.business_id import normalize_business_id


def user_external_id(user: User | None) -> str:
    if not user:
        return ""
    return (user.business_id or "").strip() or str(user.id)


def task_external_id(task: Task | None) -> str:
    if not task:
        return ""
    return (task.business_id or "").strip() or str(task.id)


def feedback_external_id(feedback: Feedback | None) -> str:
    if not feedback:
        return ""
    return (feedback.business_id or "").strip() or str(feedback.id)


def system_message_external_id(message: SystemMessage | None) -> str:
    if not message:
        return ""
    return (message.business_id or "").strip() or str(message.id)


def get_user_by_business_id(db: Session, business_id: str) -> User | None:
    normalized = normalize_business_id(business_id)
    if not normalized:
        return None
    return db.query(User).filter(User.business_id == normalized).first()


def require_user_by_business_id(db: Session, business_id: str) -> User:
    user = get_user_by_business_id(db, business_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return user


def get_task_by_business_id(db: Session, business_id: str) -> Task | None:
    normalized = normalize_business_id(business_id)
    if not normalized:
        return None
    return db.query(Task).filter(Task.business_id == normalized).first()


def require_task_by_business_id(db: Session, business_id: str) -> Task:
    task = get_task_by_business_id(db, business_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    return task


def get_feedback_by_business_id(db: Session, business_id: str) -> Feedback | None:
    normalized = normalize_business_id(business_id)
    if not normalized:
        return None
    return db.query(Feedback).filter(Feedback.business_id == normalized).first()


def require_feedback_by_business_id(db: Session, business_id: str) -> Feedback:
    feedback = get_feedback_by_business_id(db, business_id)
    if not feedback:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在")
    return feedback


def get_system_message_by_business_id(db: Session, business_id: str) -> SystemMessage | None:
    normalized = normalize_business_id(business_id)
    if not normalized:
        return None
    return db.query(SystemMessage).filter(SystemMessage.business_id == normalized).first()

