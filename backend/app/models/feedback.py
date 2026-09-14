from sqlalchemy import Boolean, Column, Integer, String, Text, DateTime, ForeignKey, func, text
from sqlalchemy.orm import relationship

from app.database import Base
from app.utils.business_id import generate_business_id


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    business_id = Column(String(32), unique=True, nullable=False, index=True, default=generate_business_id)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True, index=True)
    content = Column(Text, nullable=False)
    feedback_type = Column(String(32), nullable=False, default="general", server_default="general", index=True)
    attachments_json = Column(Text, nullable=False, default="[]")
    status = Column(String(20), nullable=False, default="pending", server_default="pending", index=True)
    is_read = Column(Boolean, nullable=False, default=False, server_default=text("0"), index=True)
    process_note = Column(String(5000), nullable=False, default="", server_default="")
    result_note = Column(String(5000), nullable=False, default="", server_default="")
    handled_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    handled_at = Column(DateTime, nullable=True)
    last_message_at = Column(DateTime, nullable=True, index=True)
    user_last_read_at = Column(DateTime, nullable=True)
    admin_last_read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id], backref="feedback_items")
    task = relationship("Task", foreign_keys=[task_id], backref="feedback_items")
    handler = relationship("User", foreign_keys=[handled_by])
    messages = relationship("FeedbackMessage", back_populates="feedback", cascade="all, delete-orphan")


class FeedbackMessage(Base):
    __tablename__ = "feedback_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    business_id = Column(String(32), unique=True, nullable=False, index=True, default=generate_business_id)
    feedback_id = Column(Integer, ForeignKey("feedback.id"), nullable=False, index=True)
    sender_role = Column(String(20), nullable=False, default="user", server_default="user", index=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    content = Column(Text, nullable=False, default="")
    attachments_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True)

    feedback = relationship("Feedback", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_id])
