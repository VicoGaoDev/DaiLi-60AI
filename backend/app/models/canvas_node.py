from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.database import Base


class CanvasNode(Base):
    __tablename__ = "canvas_nodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    canvas_id = Column(Integer, ForeignKey("user_canvas.id"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("canvas_groups.id", ondelete="SET NULL"), nullable=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    video_task_id = Column(Integer, ForeignKey("video_tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    node_type = Column(String(20), nullable=False, default="task", server_default="task")
    content = Column(String(5000), nullable=False, default="", server_default="")
    image_url = Column(String(1000), nullable=False, default="", server_default="")
    x = Column(Float, nullable=False, default=0, server_default="0")
    y = Column(Float, nullable=False, default=0, server_default="0")
    width = Column(Float, nullable=False, default=320, server_default="320")
    height = Column(Float, nullable=False, default=420, server_default="420")
    z_index = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    canvas = relationship("UserCanvas", back_populates="nodes")
    group = relationship("CanvasGroup", back_populates="nodes")
    task = relationship("Task", back_populates="canvas_node")
    video_task = relationship("VideoTask", back_populates="canvas_node")
    outgoing_edges = relationship("CanvasEdge", foreign_keys="CanvasEdge.source_node_id", back_populates="source_node")
    incoming_edges = relationship("CanvasEdge", foreign_keys="CanvasEdge.target_node_id", back_populates="target_node")
    outgoing_edges = relationship("CanvasEdge", foreign_keys="CanvasEdge.source_node_id", back_populates="source_node")
    incoming_edges = relationship("CanvasEdge", foreign_keys="CanvasEdge.target_node_id", back_populates="target_node")
