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
    status = Column(String(20), nullable=False, default="pending", server_default="pending", index=True)
    is_read = Column(Boolean, nullable=False, default=False, server_default=text("0"), index=True)
    process_note = Column(String(5000), nullable=False, default="", server_default="")
    result_note = Column(String(5000), nullable=False, default="", server_default="")
    handled_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    handled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id], backref="feedback_items")
    task = relationship("Task", foreign_keys=[task_id], backref="feedback_items")
    handler = relationship("User", foreign_keys=[handled_by])
