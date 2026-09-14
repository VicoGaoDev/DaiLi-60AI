from sqlalchemy import Column, DateTime, Integer, String, Text, func, text

from app.database import Base
from app.utils.business_id import generate_business_id


class UpdateLog(Base):
    __tablename__ = "update_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    business_id = Column(String(32), unique=True, nullable=False, index=True, default=generate_business_id)
    title = Column(String(200), nullable=False, default="", server_default="", index=True)
    content = Column(Text, nullable=False)
    tag_type = Column(String(20), nullable=False, default="other", server_default="other", index=True)
    effective_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=func.now())
