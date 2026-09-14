from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.database import Base


class UserApiKey(Base):
    __tablename__ = "user_api_key"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    subs_type = Column(String(50), nullable=False, default="", server_default="")
    expire_time = Column(DateTime, nullable=True)
    api_key = Column(String(35), nullable=False, unique=True, index=True)
    key_name = Column(String(100), nullable=False, default="", server_default="")
    status = Column(String(20), nullable=False, default="enabled", server_default="enabled", index=True)
    is_delete = Column(Boolean, nullable=False, default=False, server_default="0", index=True)
    key_prefix = Column(String(8), nullable=False, default="", server_default="")
    key_last4 = Column(String(4), nullable=False, default="", server_default="")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", backref="user_api_keys")
