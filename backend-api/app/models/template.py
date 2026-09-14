from sqlalchemy import Column, Integer, String, Text, DateTime, func
from sqlalchemy.orm import relationship
from app.database import Base


class Template(Base):
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    prompt = Column(Text, nullable=False)
    model = Column(String(50), default="banana_pro")
    reference_images = Column(Text, default="")
    size = Column(String(20), default="1:1")
    resolution = Column(String(10), default="2K")
    custom_size = Column(String(50), default="")
    num_images = Column(Integer, default=1)
    result_image = Column(String(255), default="")
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    tag_relations = relationship(
        "TemplateTagRelation",
        back_populates="template",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
