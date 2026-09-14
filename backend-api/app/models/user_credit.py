from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint, func, text
from sqlalchemy.orm import relationship

from app.database import Base

DEFAULT_CREDIT_EXPIRE_AT = datetime(2027, 12, 30, 23, 59, 59)
DEFAULT_USER_CREDIT_STATUS = 1


class UserCredit(Base):
    __tablename__ = "user_credits"
    __table_args__ = (
        UniqueConstraint("user_id", "type", name="uq_user_credits_user_id_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(Integer, nullable=False, default=0, server_default="0", index=True)
    remain_credit = Column(Integer, nullable=False, default=0, server_default="0")
    used_credit = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(
        Integer,
        nullable=False,
        default=DEFAULT_USER_CREDIT_STATUS,
        server_default="1",
        index=True,
    )
    expire_time = Column(
        DateTime,
        nullable=False,
        default=lambda: DEFAULT_CREDIT_EXPIRE_AT,
        server_default=text("'2027-12-30 23:59:59'"),
    )
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", backref="credit_accounts")
