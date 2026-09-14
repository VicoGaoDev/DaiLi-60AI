from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func

from app.database import Base


class ExternalApiSceneBinding(Base):
    __tablename__ = "external_api_scene_bindings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scene_key = Column(String(50), nullable=False, unique=True)
    is_deleted = Column(Boolean, nullable=False, default=False, server_default="0")
    scene_type = Column(String(30), nullable=False, default="generate", server_default="generate")
    scene_label = Column(String(100), nullable=False, default="", server_default="")
    scene_description = Column(String(255), nullable=False, default="", server_default="")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    hide_aspect_ratio = Column(Boolean, nullable=False, default=False, server_default="0")
    hide_resolution = Column(Boolean, nullable=False, default=False, server_default="0")
    hide_custom_size = Column(Boolean, nullable=False, default=True, server_default="1")
    custom_size_min = Column(Integer, nullable=False, default=256, server_default="256")
    custom_size_max = Column(Integer, nullable=False, default=4096, server_default="4096")
    custom_size_step = Column(Integer, nullable=False, default=8, server_default="8")
    status = Column(String(20), nullable=False, default="enabled", server_default="enabled")
    api_config_id = Column(Integer, ForeignKey("external_api_configs.id"), nullable=True)
    backup_api_config_id = Column(Integer, ForeignKey("external_api_configs.id"), nullable=True)
    display_name = Column(String(100), nullable=False, default="", server_default="")
    subtitle = Column(String(255), nullable=False, default="", server_default="")
    credit_cost = Column(Integer, nullable=False, default=0, server_default="0")
    max_reference_images = Column(Integer, nullable=False, default=0, server_default="0")
    aspect_ratio_options_json = Column(Text, nullable=False, default="[]", server_default="[]")
    image_size_options_json = Column(Text, nullable=False, default="[]", server_default="[]")
    custom_size_options_json = Column(Text, nullable=False, default="[]", server_default="[]")
    resolution_mapping_json = Column(Text, nullable=False, default="{}", server_default="{}")
    resolution_credit_costs_json = Column(Text, nullable=False, default="{}", server_default="{}")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
