from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func

from app.database import Base


class PromptOptimizeTask(Base):
    __tablename__ = "prompt_optimize_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    legacy_prompt_history_id = Column(Integer, nullable=True, unique=True, index=True)
    style_id = Column(Integer, ForeignKey("prompt_optimize_styles.id"), nullable=True, index=True)
    style_name_snapshot = Column(String(100), nullable=False, default="", server_default="")
    source = Column(String(20), nullable=False, default="web", server_default="web")
    original_prompt = Column(String(5000), nullable=False, default="", server_default="")
    optimized_prompt = Column(String(5000), nullable=False, default="", server_default="")
    reference_images_json = Column(Text, nullable=False, default="[]", server_default="[]")
    source_image = Column(String(500), nullable=False, default="", server_default="")
    status = Column(String(20), nullable=False, default="success", server_default="success")
    credit_cost = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
