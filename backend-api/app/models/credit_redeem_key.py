from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.database import Base


class CreditRedeemKey(Base):
    __tablename__ = "credit_redeem_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    redeem_key = Column(String(16), nullable=False, unique=True, index=True)
    credit_amount = Column(Integer, nullable=False, default=0, server_default="0")
    batch_no = Column(String(32), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="enabled", server_default="enabled", index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    used_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    creator = relationship("User", foreign_keys=[created_by])
    used_by_user = relationship("User", foreign_keys=[used_by_user_id])
