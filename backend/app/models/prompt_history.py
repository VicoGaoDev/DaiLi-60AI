from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from app.database import Base


class PromptHistory(Base):
    __tablename__ = "prompt_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    prompt = Column(String(5000), nullable=False)
    mode = Column(String(20), nullable=False, default="generate", server_default="generate")
    source_image = Column(String(500), nullable=False, default="", server_default="")
    created_at = Column(DateTime, server_default=func.now())
