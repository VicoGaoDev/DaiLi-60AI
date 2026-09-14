from sqlalchemy import BigInteger, Column, DateTime, Integer, String, UniqueConstraint, func, text

from app.database import Base


class ApiAlertRun(Base):
    __tablename__ = "api_alert_runs"
    __table_args__ = (
        UniqueConstraint("slot_start", "alert_type", name="uk_api_alert_runs_slot_type"),
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    slot_start = Column(DateTime, nullable=False)
    alert_type = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=func.now())
