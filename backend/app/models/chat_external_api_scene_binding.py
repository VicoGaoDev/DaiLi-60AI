from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func

from app.database import Base


class ChatExternalApiSceneBinding(Base):
    __tablename__ = "chat_external_api_scene_bindings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scene_key = Column(String(50), nullable=False, unique=True)
    is_deleted = Column(Boolean, nullable=False, default=False, server_default="0")
    scene_label = Column(String(100), nullable=False, default="", server_default="")
    scene_description = Column(String(255), nullable=False, default="", server_default="")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(String(20), nullable=False, default="enabled", server_default="enabled")
    api_config_id = Column(Integer, ForeignKey("chat_external_api_configs.id"), nullable=True)
    backup_api_config_id = Column(Integer, ForeignKey("chat_external_api_configs.id"), nullable=True)
    display_name = Column(String(100), nullable=False, default="", server_default="")
    subtitle = Column(String(255), nullable=False, default="", server_default="")
    credit_cost = Column(Integer, nullable=False, default=0, server_default="0")
    system_prompt = Column(Text, nullable=False, default="")
    context_message_limit = Column(Integer, nullable=False, default=10, server_default="10")
    opening_greeting = Column(String(1000), nullable=False, default="", server_default="")
    starter_prompts_json = Column(Text, nullable=False, default="[]", server_default="[]")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
