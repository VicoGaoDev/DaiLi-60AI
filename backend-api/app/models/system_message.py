from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import relationship

from app.database import Base
from app.utils.business_id import generate_business_id


class SystemMessage(Base):
    __tablename__ = "system_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    business_id = Column(String(32), unique=True, nullable=False, index=True, default=generate_business_id)
    subject = Column(String(200), nullable=False, index=True)
    content_html = Column(LONGTEXT().with_variant(Text, "sqlite"), nullable=False)
    content_text = Column(LONGTEXT().with_variant(Text, "sqlite"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    recipient_scope = Column(String(20), nullable=False, default="selected", server_default="selected", index=True)
    recipient_count = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=func.now())

    sender = relationship("User", foreign_keys=[sender_id])
    recipients = relationship("SystemMessageRecipient", back_populates="message", cascade="all, delete-orphan")


class SystemMessageRecipient(Base):
    __tablename__ = "system_message_recipients"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_system_message_recipient_message_user"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey("system_messages.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    is_read = Column(Boolean, nullable=False, default=False, server_default=text("0"), index=True)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    message = relationship("SystemMessage", back_populates="recipients")
    user = relationship("User", foreign_keys=[user_id])
