from sqlalchemy import Boolean, Column, DateTime, Integer, String, func
from sqlalchemy.orm import relationship

from app.database import Base
from app.utils.business_id import generate_business_id


class WecomWebhookChannel(Base):
    __tablename__ = "wecom_webhook_channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    business_id = Column(String(32), unique=True, nullable=False, index=True, default=generate_business_id)
    name = Column(String(50), nullable=False, default="")
    webhook_url = Column(String(500), nullable=False, default="", server_default="")
    is_enabled = Column(Boolean, nullable=False, default=False, server_default="0")
    remark = Column(String(200), nullable=False, default="", server_default="")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    rules = relationship("WecomNotifyRule", back_populates="channel")
