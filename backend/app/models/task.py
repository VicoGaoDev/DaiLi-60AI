from sqlalchemy import Boolean, Column, Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base
from app.utils.business_id import generate_business_id


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    business_id = Column(String(32), unique=True, nullable=False, index=True, default=generate_business_id)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    board_id = Column(Integer, ForeignKey("user_boards.id", ondelete="SET NULL"), nullable=True, index=True)
    canvas_id = Column(Integer, ForeignKey("user_canvas.id", ondelete="SET NULL"), nullable=True, index=True)
    model = Column(String(50), default="")
    source = Column(String(20), nullable=False, default="web", server_default="web")
    mode = Column(String(20), default="generate")
    prompt = Column(Text, default="")
    num_images = Column(Integer, default=4)
    size = Column(String(20), default="3:4")
    resolution = Column(String(10), default="4K")
    custom_size = Column(String(50), default="")
    reference_image = Column(String(500), default="")
    reference_images = Column(Text, default="")
    source_image = Column(String(500), default="")
    mask_image = Column(String(500), default="")
    credit_cost = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(String(20), default="pending")
    error_message = Column(Text, default="")
    provider_api_config_id = Column(Integer, nullable=True)
    provider_task_id = Column(String(255), nullable=False, default="")
    provider_status = Column(String(50), nullable=False, default="")
    provider_error_message = Column(Text, default="")
    provider_response_preview = Column(Text, default="")
    poll_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_polled_at = Column(DateTime, nullable=True)
    next_poll_at = Column(DateTime, nullable=True)
    provider_started_at = Column(DateTime, nullable=True)
    used_fallback_api = Column(Boolean, nullable=False, default=False, server_default="0")
    is_example_template_seed = Column(Boolean, nullable=False, default=False, server_default="0")
    is_deleted = Column(Boolean, default=False, nullable=False, server_default="0")
    created_at = Column(DateTime, server_default=func.now())
    enqueued_at = Column(DateTime, nullable=True)
    request_started_at = Column(DateTime, nullable=True)
    request_finished_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", backref="tasks")
    board = relationship("UserBoard", back_populates="tasks")
    canvas = relationship("UserCanvas", back_populates="tasks")
    canvas_node = relationship("CanvasNode", back_populates="task", uselist=False)
    images = relationship("Image", back_populates="task", lazy="selectin")
    api_attempts = relationship("TaskApiAttempt", back_populates="task", lazy="selectin")
