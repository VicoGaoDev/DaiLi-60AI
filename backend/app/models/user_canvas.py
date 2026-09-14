import secrets
import string

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.database import Base


CANVAS_PROJECT_ID_ALPHABET = string.ascii_letters + string.digits
CANVAS_PROJECT_ID_LENGTH = 16


def generate_canvas_project_id() -> str:
    return "".join(secrets.choice(CANVAS_PROJECT_ID_ALPHABET) for _ in range(CANVAS_PROJECT_ID_LENGTH))


class UserCanvas(Base):
    __tablename__ = "user_canvas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(16), unique=True, nullable=False, index=True, default=generate_canvas_project_id)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source_example_id = Column(Integer, nullable=True, index=True)
    name = Column(String(100), nullable=False, default="", server_default="")
    viewport_x = Column(Float, nullable=False, default=0, server_default="0")
    viewport_y = Column(Float, nullable=False, default=0, server_default="0")
    zoom = Column(Float, nullable=False, default=0.5, server_default="0.5")
    is_deleted = Column(Boolean, nullable=False, default=False, server_default="0")
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", backref="canvases")
    nodes = relationship("CanvasNode", back_populates="canvas")
    tasks = relationship("Task", back_populates="canvas")
    edges = relationship("CanvasEdge", back_populates="canvas")
    groups = relationship("CanvasGroup", back_populates="canvas")
