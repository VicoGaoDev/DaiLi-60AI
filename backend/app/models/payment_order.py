from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_no = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    plan_key = Column(String(50), nullable=False, default="", server_default="")
    subject = Column(String(255), nullable=False, default="", server_default="")
    amount_fen = Column(Integer, nullable=False, default=0, server_default="0")
    credits = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(String(20), nullable=False, default="created", server_default="created", index=True)
    out_trade_no = Column(String(64), unique=True, nullable=False, default="", server_default="")
    alipay_trade_no = Column(String(64), unique=True, nullable=True, index=True)
    buyer_id = Column(String(64), nullable=False, default="", server_default="")
    trade_status = Column(String(32), nullable=False, default="", server_default="")
    notify_payload = Column(Text, nullable=False, default="")
    return_payload = Column(Text, nullable=False, default="")
    paid_at = Column(DateTime, nullable=True)
    credited_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", backref="payment_orders")
