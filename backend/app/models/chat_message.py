from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func

from app.database import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    reply_to_message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=True)
    role = Column(String(20), nullable=False, default="user", server_default="user")
    content = Column(Text, nullable=False, default="")
    images_json = Column(Text, nullable=True, default="[]")
    extra_json = Column(Text, nullable=True)
    model = Column(String(50), nullable=False, default="", server_default="")
    client_message_id = Column(String(64), nullable=True)
    credit_cost = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(String(20), nullable=False, default="success", server_default="success")
    error_message = Column(String(2000), nullable=False, default="", server_default="")
    provider_api_config_id = Column(Integer, nullable=True)
    used_fallback_api = Column(Boolean, nullable=False, default=False, server_default="0")
    provider_response_preview = Column(Text, nullable=True, default="")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
