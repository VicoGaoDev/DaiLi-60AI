from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.orm import relationship

from app.database import Base


class HistoryPin(Base):
    __tablename__ = "history_pins"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    item_type = Column(String(20), nullable=False, default="task", server_default="task")
    item_key = Column(String(64), nullable=False)
    image_id = Column(Integer, nullable=True)
    history_id = Column(Integer, nullable=True)
    pinned_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    user = relationship("User", foreign_keys=[user_id], backref="history_pins")
