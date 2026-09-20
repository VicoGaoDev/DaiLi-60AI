from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base
from app.utils.business_id import generate_business_id


class WecomNotifyRule(Base):
    __tablename__ = "wecom_notify_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    business_id = Column(String(32), unique=True, nullable=False, index=True, default=generate_business_id)
    channel_id = Column(Integer, ForeignKey("wecom_webhook_channels.id"), nullable=False, index=True)
    event_key = Column(String(50), nullable=False, index=True)
    name = Column(String(80), nullable=False, default="")
    is_enabled = Column(Boolean, nullable=False, default=True, server_default="1")
    conditions_json = Column(Text, nullable=False, default="{}")
    template_markdown = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    channel = relationship("WecomWebhookChannel", back_populates="rules")
