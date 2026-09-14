from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.database import Base


class UserPromptCategory(Base):
    __tablename__ = "user_prompt_categories"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_prompt_categories_user_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False, default="")
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User")
    prompts = relationship("UserPrompt", back_populates="category")
