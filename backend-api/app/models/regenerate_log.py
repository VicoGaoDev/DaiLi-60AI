from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from app.database import Base


class RegenerateLog(Base):
    __tablename__ = "regenerate_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(Integer, ForeignKey("images.id"), nullable=False)
    old_image_url = Column(String(255), default="")
    new_image_url = Column(String(255), default="")
    created_at = Column(DateTime, server_default=func.now())
