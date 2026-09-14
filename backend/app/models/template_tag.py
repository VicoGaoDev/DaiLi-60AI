from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import relationship
from app.database import Base


class TemplateTag(Base):
    __tablename__ = "template_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())

    template_relations = relationship(
        "TemplateTagRelation",
        back_populates="tag",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
