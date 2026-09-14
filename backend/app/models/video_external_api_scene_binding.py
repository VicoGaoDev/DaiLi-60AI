from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func

from app.database import Base


class VideoExternalApiSceneBinding(Base):
    __tablename__ = "video_external_api_scene_bindings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scene_key = Column(String(50), nullable=False, unique=True)
    is_deleted = Column(Boolean, nullable=False, default=False, server_default="0")
    scene_label = Column(String(100), nullable=False, default="", server_default="")
    scene_description = Column(String(255), nullable=False, default="", server_default="")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    hide_aspect_ratio = Column(Boolean, nullable=False, default=False, server_default="0")
    hide_duration = Column(Boolean, nullable=False, default=False, server_default="0")
    hide_resolution = Column(Boolean, nullable=False, default=False, server_default="0")
    status = Column(String(20), nullable=False, default="enabled", server_default="enabled")
    api_config_id = Column(Integer, ForeignKey("video_external_api_configs.id"), nullable=True)
    backup_api_config_id = Column(Integer, ForeignKey("video_external_api_configs.id"), nullable=True)
    display_name = Column(String(100), nullable=False, default="", server_default="")
    subtitle = Column(String(255), nullable=False, default="", server_default="")
    availability_mode = Column(String(20), nullable=False, default="both", server_default="both")
    availability_modes_json = Column(Text, nullable=False, default="[]")
    max_reference_images = Column(Integer, nullable=False, default=1, server_default="1")
    credit_billing_mode = Column(String(20), nullable=False, default="fixed", server_default="fixed")
    credit_cost = Column(Integer, nullable=False, default=0, server_default="0")
    per_second_credit_cost = Column(Integer, nullable=False, default=0, server_default="0")
    aspect_ratio_options_json = Column(Text, nullable=False, default="[]")
    duration_options_json = Column(Text, nullable=False, default="[]")
    resolution_options_json = Column(Text, nullable=False, default="[]")
    resolution_mapping_json = Column(Text, nullable=False, default="{}")
    resolution_credit_costs_json = Column(Text, nullable=False, default="{}")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
