from sqlalchemy import BigInteger, Column, Date, DateTime, Integer, String, UniqueConstraint, func, text

from app.database import Base


class DailyReportRun(Base):
    __tablename__ = "daily_report_runs"
    __table_args__ = (
        UniqueConstraint("report_date", name="uk_daily_report_runs_report_date"),
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    report_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=func.now())
