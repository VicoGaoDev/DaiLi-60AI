from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import relationship

from app.database import Base
from app.utils.business_id import generate_business_id


class AdminLedger(Base):
    __tablename__ = "admin_ledgers"
    __table_args__ = (
        UniqueConstraint("ledger_month", name="uq_admin_ledgers_ledger_month"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    business_id = Column(String(32), unique=True, nullable=False, index=True, default=generate_business_id)
    ledger_month = Column(Date, nullable=False, index=True)
    title = Column(String(200), nullable=False, default="", server_default="")
    content = Column(Text, nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    screenshot_urls_json = Column(Text, nullable=False, default="[]")
    income_snapshot_json = Column(Text, nullable=False, default="{}")
    online_revenue_fen = Column(Integer, nullable=False, default=0, server_default="0")
    redeem_revenue_fen = Column(Integer, nullable=False, default=0, server_default="0")
    offline_revenue_fen = Column(Integer, nullable=False, default=0, server_default="0")
    total_income_fen = Column(Integer, nullable=False, default=0, server_default="0")
    total_expense_fen = Column(Integer, nullable=False, default=0, server_default="0")
    net_income_fen = Column(Integer, nullable=False, default=0, server_default="0")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=func.now())

    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
    expenses = relationship("AdminLedgerExpense", back_populates="ledger", cascade="all, delete-orphan")
    logs = relationship("AdminLedgerLog", back_populates="ledger", cascade="all, delete-orphan")


class AdminLedgerExpense(Base):
    __tablename__ = "admin_ledger_expenses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    business_id = Column(String(32), unique=True, nullable=False, index=True, default=generate_business_id)
    ledger_id = Column(Integer, ForeignKey("admin_ledgers.id"), nullable=False, index=True)
    expense_type = Column(String(30), nullable=False, default="other", server_default="other", index=True)
    title = Column(String(200), nullable=False, default="", server_default="")
    amount_fen = Column(Integer, nullable=False, default=0, server_default="0")
    content = Column(Text, nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    screenshot_urls_json = Column(Text, nullable=False, default="[]")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=func.now())

    ledger = relationship("AdminLedger", back_populates="expenses")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])


class AdminLedgerLog(Base):
    __tablename__ = "admin_ledger_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ledger_id = Column(Integer, ForeignKey("admin_ledgers.id"), nullable=False, index=True)
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action = Column(String(40), nullable=False, index=True)
    summary = Column(String(500), nullable=False, default="", server_default="")
    before_json = Column(Text, nullable=False, default="{}")
    after_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True)

    ledger = relationship("AdminLedger", back_populates="logs")
    operator = relationship("User", foreign_keys=[operator_id])
