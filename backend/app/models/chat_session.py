from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func

from app.database import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(16), nullable=False, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(100), nullable=False, default="", server_default="")
    model = Column(String(50), nullable=False, default="", server_default="")
    is_deleted = Column(Boolean, nullable=False, default=False, server_default="0")
    last_message_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
