from sqlalchemy import Boolean, Column, Integer, String, DateTime, func
from app.database import Base
from app.utils.business_id import generate_business_id


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    business_id = Column(String(32), unique=True, nullable=False, index=True, default=generate_business_id)
    username = Column(String(50), nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    email_verified = Column(Boolean, default=False, nullable=False, server_default="0")
    password_hash = Column(String(255), nullable=False)
    avatar_url = Column(String(500), default="")
    role = Column(String(20), default="user")
    status = Column(String(10), default="active")
    is_whitelisted = Column(Boolean, default=False, nullable=False, server_default="0")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
