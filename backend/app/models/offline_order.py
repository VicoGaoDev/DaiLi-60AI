from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.database import Base
from app.utils.business_id import generate_business_id


class OfflineOrder(Base):
    __tablename__ = "offline_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    business_id = Column(String(32), unique=True, nullable=False, index=True, default=generate_business_id)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    order_type = Column(String(20), nullable=False, default="purchase", server_default="purchase", index=True)
    credit_amount = Column(Integer, nullable=False, default=0, server_default="0")
    amount_fen = Column(Integer, nullable=False, default=0, server_default="0")
    remark = Column(String(500), nullable=False, default="", server_default="")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id], backref="offline_orders")
    creator = relationship("User", foreign_keys=[created_by])
