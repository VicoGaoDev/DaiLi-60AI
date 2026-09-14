from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func

from app.database import Base


class GenerationSceneCategory(Base):
    __tablename__ = "generation_scene_categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, default="", server_default="")
    description = Column(String(255), nullable=False, default="", server_default="")
    scene_type = Column(String(20), nullable=False, default="generate", server_default="generate")
    scene_keys_json = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False, default=100, server_default="100")
    status = Column(String(20), nullable=False, default="enabled", server_default="enabled")
    is_deleted = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
