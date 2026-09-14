from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import relationship
from app.database import Base


class Image(Base):
    __tablename__ = "images"
    __table_args__ = (Index("idx_images_request_finished_at", "request_finished_at"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    image_url = Column(String(255), default="")
    preview_url = Column(String(500), default="")
    image_format = Column(String(20), default="")
    image_size_bytes = Column(Integer, default=0)
    status = Column(String(20), default="pending")
    error_message = Column(String(2000), default="")
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    request_started_at = Column(DateTime, nullable=True)
    request_finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    task = relationship("Task", back_populates="images")
