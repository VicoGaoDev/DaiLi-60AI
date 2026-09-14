from sqlalchemy import Column, DateTime, Integer, String, Text, func

from app.database import Base


class VideoExternalApiConfig(Base):
    __tablename__ = "video_external_api_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(255), nullable=False, default="")
    group_name = Column(String(100), nullable=False, default="默认")
    request_url = Column(String(500), nullable=False, default="")
    request_format = Column(String(20), nullable=False, default="json")
    headers_json = Column(Text, nullable=False, default="{}")
    payload_json = Column(Text, nullable=False, default="{}")
    response_json = Column(Text, nullable=False, default="{}")
    result_video_url_field = Column(String(255), nullable=False, default="")
    result_video_base64_field = Column(String(255), nullable=False, default="")
    result_cover_url_field = Column(String(255), nullable=False, default="")
    call_mode = Column(String(20), nullable=False, default="async")
    submit_success_statuses_json = Column(Text, nullable=False, default="[200, 201, 202]")
    poll_url = Column(String(500), nullable=False, default="")
    poll_method = Column(String(10), nullable=False, default="GET")
    poll_headers_json = Column(Text, nullable=False, default="{}")
    poll_payload_json = Column(Text, nullable=False, default="{}")
    task_id_field = Column(String(255), nullable=False, default="")
    result_status_field = Column(String(255), nullable=False, default="")
    result_success_values_json = Column(Text, nullable=False, default='["success", "succeeded", "completed"]')
    result_failed_values_json = Column(Text, nullable=False, default='["failed", "error", "cancelled"]')
    result_error_field = Column(String(255), nullable=False, default="")
    poll_result_video_url_field = Column(String(255), nullable=False, default="")
    poll_result_video_base64_field = Column(String(255), nullable=False, default="")
    poll_result_cover_url_field = Column(String(255), nullable=False, default="")
    poll_interval_seconds = Column(Integer, nullable=False, default=5)
    poll_timeout_seconds = Column(Integer, nullable=False, default=600)
    status = Column(String(20), nullable=False, default="enabled")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
