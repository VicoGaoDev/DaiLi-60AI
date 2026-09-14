from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.database import Base


class CanvasGroup(Base):
    __tablename__ = "canvas_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    canvas_id = Column(Integer, ForeignKey("user_canvas.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False, default="", server_default="")
    color = Column(String(32), nullable=False, default="#ffab27", server_default="#ffab27")
    x = Column(Float, nullable=False, default=0, server_default="0")
    y = Column(Float, nullable=False, default=0, server_default="0")
    width = Column(Float, nullable=False, default=320, server_default="320")
    height = Column(Float, nullable=False, default=220, server_default="220")
    z_index = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    canvas = relationship("UserCanvas", back_populates="groups")
    nodes = relationship("CanvasNode", back_populates="group")
