from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class TemplateTagRelation(Base):
    __tablename__ = "template_tag_relations"

    template_id = Column(Integer, ForeignKey("templates.id"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("template_tags.id"), primary_key=True)

    template = relationship("Template", back_populates="tag_relations")
    tag = relationship("TemplateTag", back_populates="template_relations")
