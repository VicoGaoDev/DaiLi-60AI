from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func

from app.database import Base


class PromptOptimizeStyle(Base):
    __tablename__ = "prompt_optimize_styles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, default="", server_default="")
    description = Column(String(255), nullable=False, default="", server_default="")
    style_prompt = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False, default=100, server_default="100")
    status = Column(String(20), nullable=False, default="enabled", server_default="enabled", index=True)
    is_default = Column(Boolean, nullable=False, default=False, server_default="0", index=True)
    is_deleted = Column(Boolean, nullable=False, default=False, server_default="0", index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
