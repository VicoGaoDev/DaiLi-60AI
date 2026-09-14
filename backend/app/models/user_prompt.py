from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class UserPrompt(Base):
    __tablename__ = "user_prompts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("user_prompt_categories.id"), nullable=True, index=True)
    title = Column(String(255), nullable=False, default="")
    content = Column(Text, nullable=False, default="")
    is_deleted = Column(Boolean, default=False, nullable=False, server_default="0")
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User")
    category = relationship("UserPromptCategory", back_populates="prompts")
