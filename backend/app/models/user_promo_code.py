from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.database import Base


class UserPromoCode(Base):
    __tablename__ = "user_promo_codes"
    __table_args__ = (
        UniqueConstraint("code", name="uq_user_promo_codes_code"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    code = Column(String(32), nullable=False, index=True)
    platform_name = Column(String(50), nullable=False, default="", server_default="")
    status = Column(String(20), nullable=False, default="enabled", server_default="enabled", index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id], backref="promo_codes")
