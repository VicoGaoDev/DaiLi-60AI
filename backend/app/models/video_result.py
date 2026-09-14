from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.database import Base


class VideoResult(Base):
    __tablename__ = "video_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("video_tasks.id"), nullable=False, index=True)
    video_url = Column(String(500), nullable=False, default="")
    cover_url = Column(String(500), nullable=False, default="")
    video_format = Column(String(50), nullable=False, default="")
    video_size_bytes = Column(Integer, nullable=False, default=0)
    duration_seconds = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    error_message = Column(String(2000), nullable=False, default="")
    created_at = Column(DateTime, server_default=func.now())

    task = relationship("VideoTask", back_populates="results")
