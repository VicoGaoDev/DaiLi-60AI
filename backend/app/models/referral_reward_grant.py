from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.database import Base


class ReferralRewardGrant(Base):
    __tablename__ = "referral_reward_grants"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", "referrer_id", name="ux_referral_reward_source"),
        UniqueConstraint("referrer_id", "invitee_id", "reward_index", name="ux_referral_reward_index"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    referrer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    invitee_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source_type = Column(String(20), nullable=False, index=True)
    source_id = Column(String(64), nullable=False, index=True)
    source_credits = Column(Integer, nullable=False, default=0, server_default="0")
    reward_rate = Column(Integer, nullable=False, default=15, server_default="15")
    reward_credits = Column(Integer, nullable=False, default=0, server_default="0")
    reward_index = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    referrer = relationship("User", foreign_keys=[referrer_id], backref="referral_reward_grants")
    invitee = relationship("User", foreign_keys=[invitee_id])
