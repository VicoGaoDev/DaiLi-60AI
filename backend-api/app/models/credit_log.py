from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base


class CreditLog(Base):
    __tablename__ = "credit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    type = Column(String(20), nullable=False)  # "allocate" | "consume"
    description = Column(String(500), default="")
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", foreign_keys=[user_id], backref="credit_logs")
    operator = relationship("User", foreign_keys=[operator_id])
