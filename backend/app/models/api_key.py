from sqlalchemy import Column, Integer, String, DateTime, func
from app.database import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(255), nullable=False, default="")
    tongyi_key = Column(String(255), nullable=False, default="")
    contact_qr_image = Column(String(500), nullable=False, default="")
    cos_secret_id = Column(String(255), nullable=False, default="")
    cos_secret_key = Column(String(255), nullable=False, default="")
    cos_bucket = Column(String(255), nullable=False, default="")
    cos_region = Column(String(100), nullable=False, default="")
    cos_upload_domain = Column(String(500), nullable=False, default="")
    cos_public_base_url = Column(String(500), nullable=False, default="")
    announcement_enabled = Column(Integer, nullable=False, default=0)
    announcement_content = Column(String(5000), nullable=False, default="")
    announcement_updated_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
