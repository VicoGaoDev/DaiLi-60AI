import json

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class ExampleCanvasProject(Base):
    __tablename__ = "example_canvas_projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_canvas_id = Column(Integer, ForeignKey("user_canvas.id"), nullable=False, index=True, unique=True)
    source_project_id = Column(String(16), nullable=False, index=True, unique=True)
    title = Column(String(100), nullable=False, default="", server_default="")
    subtitle = Column(String(255), nullable=False, default="", server_default="")
    cover_url = Column(String(1000), nullable=False, default="", server_default="")
    status = Column(String(20), nullable=False, default="draft", server_default="draft")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    preview_urls_json = Column(Text, nullable=False, default="[]")
    snapshot_json = Column(Text, nullable=False, default="{}")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    source_canvas = relationship("UserCanvas", foreign_keys=[source_canvas_id])
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    @property
    def preview_urls(self) -> list[str]:
        try:
            data = json.loads(self.preview_urls_json or "[]")
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
        return [str(item).strip() for item in data if str(item).strip()]
