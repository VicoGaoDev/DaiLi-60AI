from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class VideoTaskApiAttempt(Base):
    __tablename__ = "video_task_api_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("video_tasks.id"), nullable=False, index=True)
    result_id = Column(Integer, ForeignKey("video_results.id"), nullable=True, index=True)
    api_config_id = Column(Integer, ForeignKey("video_external_api_configs.id"), nullable=True)
    api_config_name = Column(String(100), nullable=False, default="", server_default="")
    attempt_index = Column(Integer, nullable=False, default=1, server_default="1")
    is_fallback = Column(Boolean, nullable=False, default=False, server_default="0")
    status = Column(String(20), nullable=False, default="failed", server_default="failed")
    http_status = Column(Integer, nullable=True)
    error_message = Column(Text, default="")
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    task = relationship("VideoTask", back_populates="api_attempts")
