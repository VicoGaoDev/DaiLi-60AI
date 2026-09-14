from sqlalchemy import Column, DateTime, Integer, String, Text, func

from app.database import Base


class ChatExternalApiConfig(Base):
    __tablename__ = "chat_external_api_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(255), nullable=False, default="")
    group_name = Column(String(100), nullable=False, default="默认")
    request_url = Column(String(500), nullable=False, default="")
    request_format = Column(String(20), nullable=False, default="json")
    headers_json = Column(Text, nullable=False, default="{}")
    payload_json = Column(Text, nullable=False, default="{}")
    response_json = Column(Text, nullable=False, default="{}")
    result_text_field = Column(String(255), nullable=False, default="")
    result_error_field = Column(String(255), nullable=False, default="")
    call_mode = Column(String(20), nullable=False, default="sync")
    submit_success_statuses_json = Column(Text, nullable=False, default="[200, 201, 202]")
    status = Column(String(20), nullable=False, default="enabled")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
