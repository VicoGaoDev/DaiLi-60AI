from __future__ import annotations

import json
import logging
import logging.config
from contextvars import ContextVar
from datetime import datetime, timezone

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
user_id_var: ContextVar[str] = ContextVar("user_id", default="-")


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(record, "request_id", request_id_var.get())
        record.user_id = getattr(record, "user_id", user_id_var.get())
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", request_id_var.get()),
            "user_id": getattr(record, "user_id", user_id_var.get()),
        }
        for field_name in (
            "event",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "queue_duration_ms",
            "total_duration_ms",
            "client_ip",
            "user_agent",
            "account",
            "task_id",
            "task_ids",
            "image_id",
            "task_status",
            "dispatch_mode",
            "task_count",
            "mode",
            "model",
            "prompt_length",
            "credit_cost",
            "total_cost",
        ):
            value = getattr(record, field_name, None)
            if value not in (None, ""):
                payload[field_name] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(*, level: str = "INFO", json_logs: bool = False) -> None:
    normalized_level = (level or "INFO").upper()
    formatter_name = "json" if json_logs else "plain"
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "request_context": {
                    "()": "app.logging_utils.RequestContextFilter",
                }
            },
            "formatters": {
                "plain": {
                    "format": (
                        "%(asctime)s %(levelname)s [%(name)s] "
                        "[request_id=%(request_id)s user_id=%(user_id)s] %(message)s"
                    )
                },
                "json": {
                    "()": "app.logging_utils.JsonFormatter",
                },
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": formatter_name,
                    "filters": ["request_context"],
                }
            },
            "root": {
                "level": normalized_level,
                "handlers": ["default"],
            },
        }
    )


def set_request_context(request_id: str, user_id: int | str | None = None) -> None:
    request_id_var.set((request_id or "-").strip() or "-")
    user_id_var.set("-" if user_id in (None, "") else str(user_id))


def clear_request_context() -> None:
    request_id_var.set("-")
    user_id_var.set("-")

