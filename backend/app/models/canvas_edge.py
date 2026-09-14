from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.database import Base


class CanvasEdge(Base):
    __tablename__ = "canvas_edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    canvas_id = Column(Integer, ForeignKey("user_canvas.id", ondelete="CASCADE"), nullable=False, index=True)
    source_node_id = Column(Integer, ForeignKey("canvas_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    target_node_id = Column(Integer, ForeignKey("canvas_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    edge_type = Column(String(20), nullable=False, default="reference", server_default="reference")
    source_anchor = Column(String(10), nullable=False, default="auto", server_default="auto")
    target_anchor = Column(String(10), nullable=False, default="auto", server_default="auto")
    is_collapsed = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    canvas = relationship("UserCanvas", back_populates="edges")
    source_node = relationship("CanvasNode", foreign_keys=[source_node_id], back_populates="outgoing_edges")
    target_node = relationship("CanvasNode", foreign_keys=[target_node_id], back_populates="incoming_edges")
