from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.database import Base


class UserAsset(Base):
    __tablename__ = "user_assets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("user_asset_categories.id"), nullable=True, index=True)
    file_name = Column(String(255), nullable=False, default="")
    object_key = Column(String(500), nullable=False, default="")
    url = Column(String(1000), nullable=False, default="")
    thumbnail_url = Column(String(1000), nullable=False, default="")
    mime_type = Column(String(100), nullable=False, default="")
    file_size = Column(Integer, nullable=False, default=0)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    is_deleted = Column(Boolean, default=False, nullable=False, server_default="0")
    deleted_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User")
    category = relationship("UserAssetCategory", back_populates="assets")
