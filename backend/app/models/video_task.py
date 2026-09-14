from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base
from app.utils.business_id import generate_business_id


class VideoTask(Base):
    __tablename__ = "video_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    business_id = Column(String(32), unique=True, nullable=False, index=True, default=generate_business_id)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    model = Column(String(50), nullable=False, default="")
    source = Column(String(20), nullable=False, default="web", server_default="web")
    generation_mode = Column(String(30), nullable=False, default="", server_default="")
    prompt = Column(Text, nullable=False, default="")
    duration_seconds = Column(Integer, nullable=False, default=5, server_default="5")
    aspect_ratio = Column(String(20), nullable=False, default="")
    resolution = Column(String(50), nullable=False, default="")
    reference_images = Column(Text, nullable=False, default="")
    credit_cost = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(String(20), nullable=False, default="pending", server_default="pending")
    error_message = Column(Text, nullable=False, default="")
    provider_api_config_id = Column(Integer, nullable=True)
    provider_task_id = Column(String(255), nullable=False, default="")
    provider_status = Column(String(50), nullable=False, default="")
    provider_error_message = Column(Text, nullable=False, default="")
    provider_response_preview = Column(Text, nullable=False, default="")
    poll_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_polled_at = Column(DateTime, nullable=True)
    next_poll_at = Column(DateTime, nullable=True)
    used_fallback_api = Column(Boolean, nullable=False, default=False, server_default="0")
    is_deleted = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime, server_default=func.now())
    enqueued_at = Column(DateTime, nullable=True)
    request_started_at = Column(DateTime, nullable=True)
    request_finished_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", backref="video_tasks")
    canvas_node = relationship("CanvasNode", back_populates="video_task", uselist=False)
    results = relationship("VideoResult", back_populates="task", lazy="selectin")
    api_attempts = relationship("VideoTaskApiAttempt", back_populates="task", lazy="selectin")
