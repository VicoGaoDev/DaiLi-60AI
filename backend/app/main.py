import logging
import secrets
import string
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import MutableHeaders
from sqlalchemy import func, inspect, text
from app.database import engine, Base
from app.config import settings
from app.logging_utils import clear_request_context, set_request_context, setup_logging
from app.utils.business_id import generate_business_id
import app.models  # noqa: F401 — ensure all models are registered

setup_logging(level=settings.LOG_LEVEL, json_logs=settings.LOG_JSON)

access_logger = logging.getLogger("app.access")
error_logger = logging.getLogger("app.error")

class RequestLoggingASGIMiddleware:
    """纯 ASGI 中间件：不要用 BaseHTTPMiddleware，否则会把 SSE 整段攒完再发给浏览器。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = MutableHeaders(scope=scope)
        request_id = headers.get("x-request-id") or str(uuid.uuid4())
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        state.setdefault("user_id", None)
        set_request_context(request_id)
        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status") or 500)
                response_headers = MutableHeaders(scope=message)
                response_headers["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            user_id = (scope.get("state") or {}).get("user_id")
            set_request_context(request_id, user_id)
            client = scope.get("client")
            header_list = scope.get("headers") or []
            user_agent = ""
            for key, value in header_list:
                if key == b"user-agent":
                    user_agent = value.decode("latin-1", errors="replace")
                    break
            access_logger.info(
                "request completed",
                extra={
                    "event": "http.request.completed",
                    "method": scope.get("method") or "",
                    "path": scope.get("path") or "",
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "client_ip": client[0] if client else "",
                    "user_agent": user_agent,
                },
            )
            clear_request_context()


app = FastAPI(title="Banana Web - AI 绘图系统", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingASGIMiddleware)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "-")
    user_id = getattr(request.state, "user_id", None)
    set_request_context(request_id, user_id)
    error_logger.exception(
        "unhandled exception",
        extra={
            "event": "http.request.unhandled_exception",
            "method": request.method,
            "path": request.url.path,
            "client_ip": request.client.host if request.client else "",
            "user_agent": request.headers.get("user-agent", ""),
        },
    )
    clear_request_context()
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误", "request_id": request_id})


@app.on_event("startup")
def on_startup():
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    if settings.DB_AUTO_CREATE_TABLES:
        Base.metadata.create_all(bind=engine)
    if settings.should_run_startup_schema_sync:
        _run_startup_schema_sync()
    if settings.should_run_seed:
        _seed_default_data()
    from app.services.api_alert_scheduler import start_api_alert_scheduler
    from app.services.daily_report_scheduler import start_daily_report_scheduler

    start_api_alert_scheduler()
    start_daily_report_scheduler()


@app.on_event("shutdown")
def on_shutdown():
    from app.services.api_alert_scheduler import stop_api_alert_scheduler
    from app.services.daily_report_scheduler import stop_daily_report_scheduler

    stop_api_alert_scheduler()
    stop_daily_report_scheduler()


def _run_startup_schema_sync():
    _ensure_user_credit_schema()
    _ensure_payment_order_schema()
    _ensure_offline_order_schema()
    _ensure_credit_redeem_key_schema()
    _ensure_user_api_key_schema()
    _drop_legacy_user_credits_column()
    _ensure_user_whitelist_column()
    _ensure_user_referral_schema()
    _ensure_user_promo_code_schema()
    _ensure_invite_reward_schema()
    _ensure_promo_reward_schema()
    _backfill_invite_codes()
    _ensure_user_identity_schema()
    _ensure_business_id_schema()
    _ensure_prompt_history_columns()
    _ensure_prompt_optimize_schema()
    _ensure_image_required_columns()
    _ensure_task_credit_cost_column()
    _ensure_task_api_attempt_schema()
    _ensure_external_api_config_required_columns()
    _ensure_scene_binding_required_columns()
    _ensure_generation_scene_category_schema()
    _ensure_video_external_api_config_schema()
    _ensure_video_scene_binding_schema()
    _ensure_video_task_schema()
    _ensure_video_result_schema()
    _ensure_video_task_api_attempt_schema()
    _ensure_chat_schema()
    _ensure_template_required_columns()
    _ensure_feedback_schema()
    _ensure_system_message_schema()
    _ensure_update_log_schema()
    _ensure_admin_ledger_schema()
    _ensure_history_pin_schema()
    _ensure_user_asset_schema()
    _ensure_user_board_schema()
    _ensure_user_canvas_schema()
    _ensure_example_canvas_schema()
    _ensure_api_alert_schema()
    _ensure_daily_report_schema()
    if settings.should_run_schema_compat:
        _ensure_schema_compat()
    _backfill_task_credit_costs()
    _initialize_template_sort_orders()


def _ensure_schema_compat():
    inspector = inspect(engine)

    user_columns = {col["name"] for col in inspector.get_columns("users")}
    with engine.begin() as conn:
        if "avatar_url" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN avatar_url VARCHAR(500) DEFAULT ''"))
        if "is_whitelisted" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_whitelisted BOOLEAN DEFAULT 0"))
    task_columns = {col["name"] for col in inspector.get_columns("tasks")}
    with engine.begin() as conn:
        if "model" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN model VARCHAR(50) DEFAULT ''"))
        if "source" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN source VARCHAR(20) DEFAULT 'web'"))
        if "resolution" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN resolution VARCHAR(10) DEFAULT '4K'"))
        if "custom_size" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN custom_size VARCHAR(50) DEFAULT ''"))
        if "prompt" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN prompt TEXT DEFAULT ''"))
        if "num_images" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN num_images INTEGER DEFAULT 4"))
        if "reference_images" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN reference_images TEXT DEFAULT ''"))
        if "mode" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN mode VARCHAR(20) DEFAULT 'generate'"))
        if "source_image" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN source_image VARCHAR(500) DEFAULT ''"))
        if "mask_image" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN mask_image VARCHAR(500) DEFAULT ''"))
        if "credit_cost" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN credit_cost INTEGER DEFAULT 0"))
        if "error_message" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN error_message TEXT"))
        if "provider_api_config_id" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN provider_api_config_id INTEGER NULL"))
        if "provider_task_id" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN provider_task_id VARCHAR(255) DEFAULT ''"))
        if "provider_status" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN provider_status VARCHAR(50) DEFAULT ''"))
        if "provider_error_message" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN provider_error_message TEXT"))
        if "provider_response_preview" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN provider_response_preview TEXT"))
        if "poll_count" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN poll_count INTEGER NOT NULL DEFAULT 0"))
        if "last_polled_at" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN last_polled_at DATETIME"))
        if "next_poll_at" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN next_poll_at DATETIME"))
        if "is_deleted" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN is_deleted BOOLEAN DEFAULT 0"))
        if "enqueued_at" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN enqueued_at DATETIME"))
        if "request_started_at" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN request_started_at DATETIME"))
        if "request_finished_at" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN request_finished_at DATETIME"))
        if "provider_started_at" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN provider_started_at DATETIME"))

    image_columns = {col["name"] for col in inspector.get_columns("images")}
    with engine.begin() as conn:
        if "is_deleted" not in image_columns:
            conn.execute(text("ALTER TABLE images ADD COLUMN is_deleted BOOLEAN DEFAULT 0"))
        if "deleted_at" not in image_columns:
            conn.execute(text("ALTER TABLE images ADD COLUMN deleted_at DATETIME"))
        if "preview_url" not in image_columns:
            conn.execute(text("ALTER TABLE images ADD COLUMN preview_url VARCHAR(500) DEFAULT ''"))
        if "image_format" not in image_columns:
            conn.execute(text("ALTER TABLE images ADD COLUMN image_format VARCHAR(20) DEFAULT ''"))
        if "image_size_bytes" not in image_columns:
            conn.execute(text("ALTER TABLE images ADD COLUMN image_size_bytes INTEGER DEFAULT 0"))
        if "error_message" not in image_columns:
            conn.execute(text("ALTER TABLE images ADD COLUMN error_message VARCHAR(2000) DEFAULT ''"))

    api_key_tables = set(inspector.get_table_names())
    if "prompt_history" in api_key_tables:
        prompt_history_columns = {col["name"] for col in inspector.get_columns("prompt_history")}
        with engine.begin() as conn:
            if "mode" not in prompt_history_columns:
                conn.execute(text("ALTER TABLE prompt_history ADD COLUMN mode VARCHAR(20) DEFAULT 'generate'"))
            if "source_image" not in prompt_history_columns:
                conn.execute(text("ALTER TABLE prompt_history ADD COLUMN source_image VARCHAR(500) DEFAULT ''"))

    if "api_keys" in api_key_tables:
        api_key_columns = {col["name"] for col in inspector.get_columns("api_keys")}
        with engine.begin() as conn:
            if "tongyi_key" not in api_key_columns:
                conn.execute(text("ALTER TABLE api_keys ADD COLUMN tongyi_key VARCHAR(255) DEFAULT ''"))
            if "contact_qr_image" not in api_key_columns:
                conn.execute(text("ALTER TABLE api_keys ADD COLUMN contact_qr_image VARCHAR(500) DEFAULT ''"))
            if "cos_secret_id" not in api_key_columns:
                conn.execute(text("ALTER TABLE api_keys ADD COLUMN cos_secret_id VARCHAR(255) DEFAULT ''"))
            if "cos_secret_key" not in api_key_columns:
                conn.execute(text("ALTER TABLE api_keys ADD COLUMN cos_secret_key VARCHAR(255) DEFAULT ''"))
            if "cos_bucket" not in api_key_columns:
                conn.execute(text("ALTER TABLE api_keys ADD COLUMN cos_bucket VARCHAR(255) DEFAULT ''"))
            if "cos_region" not in api_key_columns:
                conn.execute(text("ALTER TABLE api_keys ADD COLUMN cos_region VARCHAR(100) DEFAULT ''"))
            if "cos_upload_domain" not in api_key_columns:
                conn.execute(text("ALTER TABLE api_keys ADD COLUMN cos_upload_domain VARCHAR(500) DEFAULT ''"))
            if "cos_public_base_url" not in api_key_columns:
                conn.execute(text("ALTER TABLE api_keys ADD COLUMN cos_public_base_url VARCHAR(500) DEFAULT ''"))
            if "announcement_enabled" not in api_key_columns:
                conn.execute(text("ALTER TABLE api_keys ADD COLUMN announcement_enabled INTEGER DEFAULT 0"))
            if "announcement_content" not in api_key_columns:
                conn.execute(text("ALTER TABLE api_keys ADD COLUMN announcement_content VARCHAR(5000) DEFAULT ''"))
            if "announcement_updated_at" not in api_key_columns:
                conn.execute(text("ALTER TABLE api_keys ADD COLUMN announcement_updated_at DATETIME"))

    if "external_api_configs" in api_key_tables:
        external_api_columns = {col["name"] for col in inspector.get_columns("external_api_configs")}
        with engine.begin() as conn:
            if "group_name" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN group_name VARCHAR(100) DEFAULT '默认'"))
            if "model_key" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN model_key VARCHAR(50) DEFAULT ''"))
            if "model_label" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN model_label VARCHAR(100) DEFAULT ''"))
            if "model_description" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN model_description VARCHAR(255) DEFAULT ''"))
            if "sort_order" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN sort_order INTEGER DEFAULT 0"))
            if "hide_resolution" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN hide_resolution BOOLEAN DEFAULT 0"))
            if "request_format" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN request_format VARCHAR(20) DEFAULT 'json'"))
            if "response_json" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN response_json TEXT"))
            if "result_base64_field" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN result_base64_field VARCHAR(255) DEFAULT ''"))
            if "call_mode" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN call_mode VARCHAR(20) DEFAULT 'sync'"))
            if "submit_success_statuses_json" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN submit_success_statuses_json TEXT"))
            if "poll_url" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN poll_url VARCHAR(500) DEFAULT ''"))
            if "poll_method" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN poll_method VARCHAR(10) DEFAULT 'GET'"))
            if "poll_headers_json" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN poll_headers_json TEXT"))
            if "poll_payload_json" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN poll_payload_json TEXT"))
            if "task_id_field" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN task_id_field VARCHAR(255) DEFAULT ''"))
            if "result_status_field" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN result_status_field VARCHAR(255) DEFAULT ''"))
            if "result_success_values_json" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN result_success_values_json TEXT"))
            if "result_failed_values_json" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN result_failed_values_json TEXT"))
            if "result_error_field" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN result_error_field VARCHAR(255) DEFAULT ''"))
            if "poll_result_base64_field" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN poll_result_base64_field VARCHAR(255) DEFAULT ''"))
            if "poll_result_url_field" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN poll_result_url_field VARCHAR(255) DEFAULT ''"))
            if "poll_interval_seconds" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN poll_interval_seconds INTEGER DEFAULT 5"))
            if "poll_timeout_seconds" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN poll_timeout_seconds INTEGER DEFAULT 600"))
            if "supports_inpaint" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN supports_inpaint BOOLEAN DEFAULT 0"))
            if "is_active_inpaint" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN is_active_inpaint BOOLEAN DEFAULT 0"))
            if "supports_smart_cutout" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN supports_smart_cutout BOOLEAN DEFAULT 0"))
            if "is_active_smart_cutout" not in external_api_columns:
                conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN is_active_smart_cutout BOOLEAN DEFAULT 0"))
            conn.execute(
                text(
                    """
                    UPDATE external_api_configs
                    SET call_mode = 'sync'
                    WHERE call_mode IS NULL OR call_mode = ''
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE external_api_configs
                    SET submit_success_statuses_json = '[200, 201, 202]'
                    WHERE submit_success_statuses_json IS NULL OR submit_success_statuses_json = ''
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE external_api_configs
                    SET poll_headers_json = '{}'
                    WHERE poll_headers_json IS NULL OR poll_headers_json = ''
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE external_api_configs
                    SET poll_payload_json = '{}'
                    WHERE poll_payload_json IS NULL
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE external_api_configs
                    SET result_success_values_json = '["success", "succeeded", "completed"]'
                    WHERE result_success_values_json IS NULL OR result_success_values_json = ''
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE external_api_configs
                    SET result_failed_values_json = '["failed", "error", "cancelled"]'
                    WHERE result_failed_values_json IS NULL OR result_failed_values_json = ''
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE external_api_configs
                    SET poll_method = 'GET'
                    WHERE poll_method IS NULL OR poll_method = ''
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE external_api_configs
                    SET poll_interval_seconds = 5
                    WHERE poll_interval_seconds IS NULL OR poll_interval_seconds <= 0
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE external_api_configs
                    SET poll_timeout_seconds = 600
                    WHERE poll_timeout_seconds IS NULL OR poll_timeout_seconds <= 0
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE external_api_configs
                    SET request_format = 'json'
                    WHERE request_format IS NULL OR request_format = ''
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE external_api_configs
                    SET response_json = :response_json
                    WHERE response_json IS NULL OR response_json = ''
                    """
                ),
                {
                    "response_json": '{"candidates":[{"content":{"parts":[{"inlineData":{"mimeType":"image/png","data":"<base64>"}}]}}]}',
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE external_api_configs
                    SET result_base64_field = :result_base64_field
                    WHERE result_base64_field IS NULL OR result_base64_field = ''
                    """
                ),
                {"result_base64_field": "candidates.0.content.parts.0.inlineData.data"},
            )

    if "external_api_scene_bindings" in api_key_tables:
        scene_binding_columns = {col["name"] for col in inspector.get_columns("external_api_scene_bindings")}
        credit_cost_added = False
        max_reference_images_added = False
        with engine.begin() as conn:
            if "is_deleted" not in scene_binding_columns:
                conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN is_deleted BOOLEAN DEFAULT 0"))
            if "scene_type" not in scene_binding_columns:
                conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN scene_type VARCHAR(30) DEFAULT 'generate'"))
            if "scene_label" not in scene_binding_columns:
                conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN scene_label VARCHAR(100) DEFAULT ''"))
            if "scene_description" not in scene_binding_columns:
                conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN scene_description VARCHAR(255) DEFAULT ''"))
            if "sort_order" not in scene_binding_columns:
                conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN sort_order INTEGER DEFAULT 0"))
            if "hide_aspect_ratio" not in scene_binding_columns:
                conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN hide_aspect_ratio BOOLEAN DEFAULT 0"))
            if "hide_resolution" not in scene_binding_columns:
                conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN hide_resolution BOOLEAN DEFAULT 0"))
            if "hide_custom_size" not in scene_binding_columns:
                conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN hide_custom_size BOOLEAN DEFAULT 1"))
            if "status" not in scene_binding_columns:
                conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN status VARCHAR(20) DEFAULT 'enabled'"))
            if "api_config_id" not in scene_binding_columns:
                conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN api_config_id INTEGER"))
            if "display_name" not in scene_binding_columns:
                conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN display_name VARCHAR(100) DEFAULT ''"))
            if "subtitle" not in scene_binding_columns:
                conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN subtitle VARCHAR(255) DEFAULT ''"))
            if "credit_cost" not in scene_binding_columns:
                conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN credit_cost INTEGER DEFAULT 0"))
                credit_cost_added = True
            if "max_reference_images" not in scene_binding_columns:
                conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN max_reference_images INTEGER DEFAULT 0"))
                max_reference_images_added = True
            if "aspect_ratio_options_json" not in scene_binding_columns:
                conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN aspect_ratio_options_json TEXT"))
            if "image_size_options_json" not in scene_binding_columns:
                conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN image_size_options_json TEXT"))
            if "custom_size_options_json" not in scene_binding_columns:
                conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN custom_size_options_json TEXT"))
            if "resolution_credit_costs_json" not in scene_binding_columns:
                conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN resolution_credit_costs_json TEXT"))
            conn.execute(
                text(
                    """
                    UPDATE external_api_scene_bindings
                    SET is_deleted = 0
                    WHERE is_deleted IS NULL
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE external_api_scene_bindings
                    SET resolution_credit_costs_json = '{}'
                    WHERE resolution_credit_costs_json IS NULL
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE external_api_scene_bindings
                    SET status = 'enabled'
                    WHERE status IS NULL OR status = ''
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE external_api_scene_bindings
                    SET aspect_ratio_options_json = '[]'
                    WHERE aspect_ratio_options_json IS NULL
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE external_api_scene_bindings
                    SET image_size_options_json = '[]'
                    WHERE image_size_options_json IS NULL
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE external_api_scene_bindings
                    SET custom_size_options_json = '[]'
                    WHERE custom_size_options_json IS NULL
                    """
                )
            )

    from app.services.external_api_config_service import get_default_credit_cost, get_default_max_reference_images

    if "external_api_scene_bindings" in api_key_tables:
        with engine.begin() as conn:
            for scene_key in [
                "banana",
                "banana2",
                "banana_pro",
                "banana_pro_plus",
                "banana_edit",
                "banana2_edit",
                "banana_pro_edit",
                "banana_pro_plus_edit",
                "prompt_reverse",
                "inpaint",
                "smart_cutout",
            ]:
                conn.execute(
                    text(
                        """
                        UPDATE external_api_scene_bindings
                        SET credit_cost = :credit_cost
                        WHERE scene_key = :scene_key
                          AND credit_cost IS NULL
                        """
                    ),
                    {"scene_key": scene_key, "credit_cost": get_default_credit_cost(scene_key)},
                )
                if credit_cost_added:
                    conn.execute(
                        text(
                            """
                            UPDATE external_api_scene_bindings
                            SET credit_cost = :credit_cost
                            WHERE scene_key = :scene_key
                              AND credit_cost = 0
                            """
                        ),
                        {"scene_key": scene_key, "credit_cost": get_default_credit_cost(scene_key)},
                    )
            if max_reference_images_added:
                conn.execute(
                    text(
                        """
                        UPDATE external_api_scene_bindings
                        SET max_reference_images = :image_edit_default
                        WHERE scene_type = 'image_edit'
                          AND (max_reference_images IS NULL OR max_reference_images = 0)
                        """
                    ),
                    {"image_edit_default": get_default_max_reference_images("image_edit")},
                )


def _ensure_template_required_columns():
    inspector = inspect(engine)
    if "templates" not in inspector.get_table_names():
        return

    template_columns = {col["name"] for col in inspector.get_columns("templates")}
    with engine.begin() as conn:
        if "model" not in template_columns:
            conn.execute(text("ALTER TABLE templates ADD COLUMN model VARCHAR(50) DEFAULT 'banana_pro'"))
        if "sort_order" not in template_columns:
            conn.execute(text("ALTER TABLE templates ADD COLUMN sort_order INTEGER DEFAULT 0"))
        if "custom_size" not in template_columns:
            conn.execute(text("ALTER TABLE templates ADD COLUMN custom_size VARCHAR(50) DEFAULT ''"))


def _ensure_user_whitelist_column():
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    user_columns = {col["name"] for col in inspector.get_columns("users")}
    if "is_whitelisted" in user_columns:
        return

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN is_whitelisted BOOLEAN DEFAULT 0"))


def _ensure_user_referral_schema():
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    user_columns = {col["name"] for col in inspector.get_columns("users")}
    with engine.begin() as conn:
        if "referrer_id" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN referrer_id INTEGER NULL"))
            conn.execute(text("CREATE INDEX ix_users_referrer_id ON users (referrer_id)"))
            conn.execute(
                text(
                    """
                    ALTER TABLE users
                    ADD CONSTRAINT fk_users_referrer_id
                    FOREIGN KEY (referrer_id) REFERENCES users (id)
                    """
                )
            )
        if "used_promo_code_id" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN used_promo_code_id INTEGER NULL"))
            conn.execute(text("CREATE INDEX ix_users_used_promo_code_id ON users (used_promo_code_id)"))


def _ensure_user_promo_code_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        return

    if "user_promo_codes" not in table_names:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE user_promo_codes (
                        id INTEGER NOT NULL AUTO_INCREMENT,
                        user_id INTEGER NOT NULL,
                        code VARCHAR(32) NOT NULL,
                        platform_name VARCHAR(50) NOT NULL DEFAULT '',
                        status VARCHAR(20) NOT NULL DEFAULT 'enabled',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (id),
                        UNIQUE KEY uq_user_promo_codes_code (code),
                        INDEX ix_user_promo_codes_user_id (user_id),
                        INDEX ix_user_promo_codes_code (code),
                        INDEX ix_user_promo_codes_status (status),
                        CONSTRAINT fk_user_promo_codes_user_id FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                    """
                )
            )
        inspector = inspect(engine)

    promo_columns = {col["name"] for col in inspector.get_columns("user_promo_codes")}
    with engine.begin() as conn:
        if "platform_name" not in promo_columns:
            conn.execute(
                text(
                    """
                    ALTER TABLE user_promo_codes
                    ADD COLUMN platform_name VARCHAR(50) NOT NULL DEFAULT ''
                    AFTER code
                    """
                )
            )
        if "status" not in promo_columns:
            conn.execute(
                text(
                    """
                    ALTER TABLE user_promo_codes
                    ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'enabled'
                    AFTER platform_name
                    """
                )
            )
        conn.execute(
            text(
                """
                UPDATE user_promo_codes
                SET status = 'enabled'
                WHERE status IS NULL OR status = ''
                """
            )
        )


def _ensure_invite_reward_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        return

    user_columns = {col["name"] for col in inspector.get_columns("users")}
    user_indexes = {idx["name"] for idx in inspector.get_indexes("users")}
    with engine.begin() as conn:
        if "invite_code" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN invite_code VARCHAR(16) NULL AFTER is_whitelisted"))
        if "ux_users_invite_code" not in user_indexes:
            conn.execute(text("CREATE UNIQUE INDEX ux_users_invite_code ON users (invite_code)"))

    if "referral_reward_grants" in table_names:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE referral_reward_grants (
                    id INTEGER NOT NULL AUTO_INCREMENT,
                    referrer_id INTEGER NOT NULL,
                    invitee_id INTEGER NOT NULL,
                    source_type VARCHAR(20) NOT NULL,
                    source_id VARCHAR(64) NOT NULL,
                    source_credits INTEGER NOT NULL DEFAULT 0,
                    reward_rate INTEGER NOT NULL DEFAULT 15,
                    reward_credits INTEGER NOT NULL DEFAULT 0,
                    reward_index INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    INDEX ix_referral_reward_grants_referrer_id (referrer_id),
                    INDEX ix_referral_reward_grants_invitee_id (invitee_id),
                    INDEX ix_referral_reward_grants_source_type (source_type),
                    INDEX ix_referral_reward_grants_source_id (source_id),
                    UNIQUE KEY ux_referral_reward_source (source_type, source_id, referrer_id),
                    UNIQUE KEY ux_referral_reward_index (referrer_id, invitee_id, reward_index),
                    CONSTRAINT fk_referral_reward_referrer_id FOREIGN KEY (referrer_id) REFERENCES users (id),
                    CONSTRAINT fk_referral_reward_invitee_id FOREIGN KEY (invitee_id) REFERENCES users (id)
                )
                """
            )
        )


def _ensure_promo_reward_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names or "promo_reward_grants" in table_names:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE promo_reward_grants (
                    id INTEGER NOT NULL AUTO_INCREMENT,
                    referrer_id INTEGER NOT NULL,
                    invitee_id INTEGER NOT NULL,
                    promo_code_id INTEGER NULL,
                    source_type VARCHAR(20) NOT NULL,
                    source_id VARCHAR(64) NOT NULL,
                    source_credits INTEGER NOT NULL DEFAULT 0,
                    source_amount_fen INTEGER NOT NULL DEFAULT 0,
                    reward_rate INTEGER NOT NULL DEFAULT 30,
                    reward_amount_fen INTEGER NOT NULL DEFAULT 0,
                    reward_index INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    INDEX ix_promo_reward_grants_referrer_id (referrer_id),
                    INDEX ix_promo_reward_grants_invitee_id (invitee_id),
                    INDEX ix_promo_reward_grants_promo_code_id (promo_code_id),
                    INDEX ix_promo_reward_grants_source_type (source_type),
                    INDEX ix_promo_reward_grants_source_id (source_id),
                    UNIQUE KEY ux_promo_reward_source (source_type, source_id, referrer_id),
                    UNIQUE KEY ux_promo_reward_index (referrer_id, invitee_id, reward_index),
                    CONSTRAINT fk_promo_reward_referrer_id FOREIGN KEY (referrer_id) REFERENCES users (id),
                    CONSTRAINT fk_promo_reward_invitee_id FOREIGN KEY (invitee_id) REFERENCES users (id)
                )
                """
            )
        )


def _backfill_invite_codes():
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    from app.database import SessionLocal
    from app.services.referral_reward_service import backfill_user_invite_codes

    db = SessionLocal()
    try:
        changed = backfill_user_invite_codes(db)
        if changed:
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _ensure_user_credit_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        return

    if "user_credits" not in table_names:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE user_credits (
                        id INTEGER NOT NULL AUTO_INCREMENT,
                        user_id INTEGER NOT NULL,
                        type INTEGER NOT NULL DEFAULT 0,
                        remain_credit INTEGER NOT NULL DEFAULT 0,
                        used_credit INTEGER NOT NULL DEFAULT 0,
                        status TINYINT(1) NOT NULL DEFAULT 1,
                        expire_time DATETIME NOT NULL DEFAULT '2027-12-30 23:59:59',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (id),
                        CONSTRAINT uq_user_credits_user_id_type UNIQUE (user_id, type),
                        INDEX ix_user_credits_user_id (user_id),
                        INDEX ix_user_credits_type (type),
                        CONSTRAINT fk_user_credits_user_id FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                    """
                )
            )
        inspector = inspect(engine)

    user_credit_columns = {col["name"] for col in inspector.get_columns("user_credits")}
    user_columns = {col["name"] for col in inspector.get_columns("users")}
    with engine.begin() as conn:
        if "remain_credit" not in user_credit_columns and "balance" in user_credit_columns:
            conn.execute(
                text(
                    """
                    ALTER TABLE user_credits
                    CHANGE COLUMN balance remain_credit INTEGER NOT NULL DEFAULT 0
                    """
                )
            )
            inspector = inspect(engine)
            user_credit_columns = {col["name"] for col in inspector.get_columns("user_credits")}
        if "used_credit" not in user_credit_columns:
            conn.execute(
                text(
                    """
                    ALTER TABLE user_credits
                    ADD COLUMN used_credit INTEGER NOT NULL DEFAULT 0
                    AFTER remain_credit
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE user_credits uc
                    LEFT JOIN (
                        SELECT user_id, COALESCE(SUM(ABS(amount)), 0) AS total_used_credit
                        FROM credit_logs
                        WHERE type = 'consume'
                        GROUP BY user_id
                    ) cl ON cl.user_id = uc.user_id
                    SET uc.used_credit = COALESCE(cl.total_used_credit, 0)
                    WHERE uc.type = 0
                    """
                )
            )
            inspector = inspect(engine)
            user_credit_columns = {col["name"] for col in inspector.get_columns("user_credits")}
        if "status" not in user_credit_columns:
            conn.execute(
                text(
                    """
                    ALTER TABLE user_credits
                    ADD COLUMN status TINYINT(1) NOT NULL DEFAULT 1
                    AFTER used_credit
                    """
                )
            )
            conn.execute(text("UPDATE user_credits SET status = 1 WHERE status IS NULL"))
            inspector = inspect(engine)
            user_credit_columns = {col["name"] for col in inspector.get_columns("user_credits")}
        user_credit_status_type = next(
            (str(col["type"]) for col in inspector.get_columns("user_credits") if col["name"] == "status"),
            "",
        ).lower()
        if "varchar" in user_credit_status_type or "char" in user_credit_status_type:
            conn.execute(
                text(
                    """
                    UPDATE user_credits
                    SET status = CASE
                        WHEN status IN ('enabled', '1', 'true', 'TRUE') THEN 1
                        ELSE 0
                    END
                    """
                )
            )
            conn.execute(
                text(
                    """
                    ALTER TABLE user_credits
                    MODIFY COLUMN status TINYINT(1) NOT NULL DEFAULT 1
                    """
                )
            )
        if "expire_time" not in user_credit_columns:
            conn.execute(
                text(
                    """
                    ALTER TABLE user_credits
                    ADD COLUMN expire_time DATETIME NOT NULL DEFAULT '2027-12-30 23:59:59'
                    AFTER status
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE user_credits
                    SET expire_time = '2027-12-30 23:59:59'
                    WHERE expire_time IS NULL
                    """
                )
            )
        if "credits" in user_columns:
            conn.execute(
                text(
                    """
                    INSERT INTO user_credits (user_id, type, remain_credit, used_credit, status, expire_time, created_at, updated_at)
                    SELECT users.id, 0, COALESCE(users.credits, 0), 0, 1, '2027-12-30 23:59:59', NOW(), NOW()
                    FROM users
                    LEFT JOIN user_credits
                      ON user_credits.user_id = users.id
                     AND user_credits.type = 0
                    WHERE user_credits.id IS NULL
                    """
                )
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO user_credits (user_id, type, remain_credit, used_credit, status, expire_time, created_at, updated_at)
                    SELECT users.id, 0, 0, 0, 1, '2027-12-30 23:59:59', NOW(), NOW()
                    FROM users
                    LEFT JOIN user_credits
                      ON user_credits.user_id = users.id
                     AND user_credits.type = 0
                    WHERE user_credits.id IS NULL
                    """
                )
            )


def _ensure_credit_redeem_key_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        return

    if "credit_redeem_keys" not in table_names:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE credit_redeem_keys (
                        id INTEGER NOT NULL AUTO_INCREMENT,
                        redeem_key VARCHAR(16) NOT NULL,
                        credit_amount INTEGER NOT NULL DEFAULT 0,
                        batch_no VARCHAR(32) NOT NULL,
                        status VARCHAR(20) NOT NULL DEFAULT 'enabled',
                        created_by INTEGER NULL,
                        used_by_user_id INTEGER NULL,
                        used_at DATETIME NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (id),
                        UNIQUE KEY uq_credit_redeem_keys_redeem_key (redeem_key),
                        INDEX ix_credit_redeem_keys_redeem_key (redeem_key),
                        INDEX ix_credit_redeem_keys_batch_no (batch_no),
                        INDEX ix_credit_redeem_keys_status (status),
                        INDEX ix_credit_redeem_keys_created_by (created_by),
                        INDEX ix_credit_redeem_keys_used_by_user_id (used_by_user_id),
                        CONSTRAINT fk_credit_redeem_keys_created_by FOREIGN KEY (created_by) REFERENCES users (id),
                        CONSTRAINT fk_credit_redeem_keys_used_by_user_id FOREIGN KEY (used_by_user_id) REFERENCES users (id)
                    )
                    """
                )
            )
        return

    credit_redeem_columns = {col["name"] for col in inspector.get_columns("credit_redeem_keys")}
    with engine.begin() as conn:
        if "status" not in credit_redeem_columns:
            conn.execute(
                text(
                    """
                    ALTER TABLE credit_redeem_keys
                    ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'enabled'
                    AFTER batch_no
                    """
                )
            )
        conn.execute(
            text(
                """
                UPDATE credit_redeem_keys
                SET status = 'enabled'
                WHERE status IS NULL OR status = ''
                """
            )
        )


def _ensure_payment_order_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        return

    if "payment_orders" not in table_names:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE payment_orders (
                        id INTEGER NOT NULL AUTO_INCREMENT,
                        order_no VARCHAR(64) NOT NULL,
                        user_id INTEGER NOT NULL,
                        plan_key VARCHAR(50) NOT NULL DEFAULT '',
                        subject VARCHAR(255) NOT NULL DEFAULT '',
                        amount_fen INTEGER NOT NULL DEFAULT 0,
                        credits INTEGER NOT NULL DEFAULT 0,
                        status VARCHAR(20) NOT NULL DEFAULT 'created',
                        out_trade_no VARCHAR(64) NOT NULL,
                        alipay_trade_no VARCHAR(64) NULL,
                        buyer_id VARCHAR(64) NOT NULL DEFAULT '',
                        trade_status VARCHAR(32) NOT NULL DEFAULT '',
                        notify_payload TEXT NULL,
                        return_payload TEXT NULL,
                        paid_at DATETIME NULL,
                        credited_at DATETIME NULL,
                        closed_at DATETIME NULL,
                        failed_at DATETIME NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (id),
                        UNIQUE KEY uq_payment_orders_order_no (order_no),
                        UNIQUE KEY uq_payment_orders_out_trade_no (out_trade_no),
                        UNIQUE KEY uq_payment_orders_alipay_trade_no (alipay_trade_no),
                        INDEX ix_payment_orders_user_id (user_id),
                        INDEX ix_payment_orders_status (status),
                        INDEX ix_payment_orders_user_created_at (user_id, created_at),
                        CONSTRAINT fk_payment_orders_user_id FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                    """
                )
            )
        return

    payment_columns = {col["name"] for col in inspector.get_columns("payment_orders")}
    with engine.begin() as conn:
        if "subject" not in payment_columns:
            conn.execute(text("ALTER TABLE payment_orders ADD COLUMN subject VARCHAR(255) NOT NULL DEFAULT '' AFTER plan_key"))
        if "trade_status" not in payment_columns:
            conn.execute(text("ALTER TABLE payment_orders ADD COLUMN trade_status VARCHAR(32) NOT NULL DEFAULT '' AFTER buyer_id"))
        if "notify_payload" not in payment_columns:
            conn.execute(text("ALTER TABLE payment_orders ADD COLUMN notify_payload TEXT NULL AFTER trade_status"))
        if "return_payload" not in payment_columns:
            conn.execute(text("ALTER TABLE payment_orders ADD COLUMN return_payload TEXT NULL AFTER notify_payload"))
        if "paid_at" not in payment_columns:
            conn.execute(text("ALTER TABLE payment_orders ADD COLUMN paid_at DATETIME NULL AFTER return_payload"))
        if "credited_at" not in payment_columns:
            conn.execute(text("ALTER TABLE payment_orders ADD COLUMN credited_at DATETIME NULL AFTER paid_at"))
        if "closed_at" not in payment_columns:
            conn.execute(text("ALTER TABLE payment_orders ADD COLUMN closed_at DATETIME NULL AFTER credited_at"))
        if "failed_at" not in payment_columns:
            conn.execute(text("ALTER TABLE payment_orders ADD COLUMN failed_at DATETIME NULL AFTER closed_at"))


def _ensure_offline_order_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        return

    if "offline_orders" not in table_names:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE offline_orders (
                        id INTEGER NOT NULL AUTO_INCREMENT,
                        business_id VARCHAR(32) NOT NULL,
                        user_id INTEGER NOT NULL,
                        order_type VARCHAR(20) NOT NULL DEFAULT 'purchase',
                        credit_amount INTEGER NOT NULL DEFAULT 0,
                        amount_fen INTEGER NOT NULL DEFAULT 0,
                        remark VARCHAR(500) NOT NULL DEFAULT '',
                        created_by INTEGER NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (id),
                        UNIQUE KEY uq_offline_orders_business_id (business_id),
                        INDEX ix_offline_orders_user_id (user_id),
                        INDEX ix_offline_orders_order_type (order_type),
                        INDEX ix_offline_orders_created_by (created_by),
                        INDEX ix_offline_orders_created_at (created_at),
                        CONSTRAINT fk_offline_orders_user_id FOREIGN KEY (user_id) REFERENCES users (id),
                        CONSTRAINT fk_offline_orders_created_by FOREIGN KEY (created_by) REFERENCES users (id)
                    )
                    """
                )
            )
        return

    offline_order_columns_info = inspector.get_columns("offline_orders")
    offline_order_columns = {col["name"] for col in offline_order_columns_info}
    with engine.begin() as conn:
        if "business_id" not in offline_order_columns:
            conn.execute(text("ALTER TABLE offline_orders ADD COLUMN business_id VARCHAR(32) NULL"))
        if "user_id" not in offline_order_columns:
            conn.execute(text("ALTER TABLE offline_orders ADD COLUMN user_id INTEGER NULL"))
        if "order_type" not in offline_order_columns:
            conn.execute(text("ALTER TABLE offline_orders ADD COLUMN order_type VARCHAR(20) NOT NULL DEFAULT 'purchase'"))
        if "credit_amount" not in offline_order_columns:
            conn.execute(text("ALTER TABLE offline_orders ADD COLUMN credit_amount INTEGER NOT NULL DEFAULT 0"))
        if "amount_fen" not in offline_order_columns:
            conn.execute(text("ALTER TABLE offline_orders ADD COLUMN amount_fen INTEGER NOT NULL DEFAULT 0"))
        if "remark" not in offline_order_columns:
            conn.execute(text("ALTER TABLE offline_orders ADD COLUMN remark VARCHAR(500) NOT NULL DEFAULT ''"))
        if "created_by" not in offline_order_columns:
            conn.execute(text("ALTER TABLE offline_orders ADD COLUMN created_by INTEGER NULL"))
        if "created_at" not in offline_order_columns:
            conn.execute(text("ALTER TABLE offline_orders ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "updated_at" not in offline_order_columns:
            conn.execute(text("ALTER TABLE offline_orders ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))

        if "business_id" in {col["name"] for col in inspector.get_columns("offline_orders")}:
            missing_ids = conn.execute(
                text("SELECT id FROM offline_orders WHERE business_id IS NULL OR business_id = ''")
            ).scalars().all()
            for offline_order_id in missing_ids:
                conn.execute(
                    text("UPDATE offline_orders SET business_id = :business_id WHERE id = :id"),
                    {"business_id": generate_business_id(), "id": offline_order_id},
                )

    refreshed_inspector = inspect(engine)
    refreshed_columns_info = refreshed_inspector.get_columns("offline_orders")
    refreshed_columns = {col["name"] for col in refreshed_columns_info}
    offline_order_indexes = {index["name"] for index in refreshed_inspector.get_indexes("offline_orders")}
    offline_order_foreign_keys = {fk.get("name") for fk in refreshed_inspector.get_foreign_keys("offline_orders")}
    with engine.begin() as conn:
        if "uq_offline_orders_business_id" not in offline_order_indexes:
            conn.execute(text("CREATE UNIQUE INDEX uq_offline_orders_business_id ON offline_orders (business_id)"))
        if "ix_offline_orders_user_id" not in offline_order_indexes:
            conn.execute(text("CREATE INDEX ix_offline_orders_user_id ON offline_orders (user_id)"))
        if "ix_offline_orders_order_type" not in offline_order_indexes:
            conn.execute(text("CREATE INDEX ix_offline_orders_order_type ON offline_orders (order_type)"))
        if "ix_offline_orders_created_by" not in offline_order_indexes:
            conn.execute(text("CREATE INDEX ix_offline_orders_created_by ON offline_orders (created_by)"))
        if "ix_offline_orders_created_at" not in offline_order_indexes:
            conn.execute(text("CREATE INDEX ix_offline_orders_created_at ON offline_orders (created_at)"))
        if "fk_offline_orders_user_id" not in offline_order_foreign_keys and "user_id" in refreshed_columns:
            conn.execute(
                text(
                    """
                    ALTER TABLE offline_orders
                    ADD CONSTRAINT fk_offline_orders_user_id
                    FOREIGN KEY (user_id) REFERENCES users (id)
                    """
                )
            )
        if "fk_offline_orders_created_by" not in offline_order_foreign_keys and "created_by" in refreshed_columns:
            conn.execute(
                text(
                    """
                    ALTER TABLE offline_orders
                    ADD CONSTRAINT fk_offline_orders_created_by
                    FOREIGN KEY (created_by) REFERENCES users (id)
                    """
                )
            )
        if "business_id" in refreshed_columns:
            conn.execute(text("ALTER TABLE offline_orders MODIFY COLUMN business_id VARCHAR(32) NOT NULL"))
        if "user_id" in refreshed_columns:
            conn.execute(text("ALTER TABLE offline_orders MODIFY COLUMN user_id INTEGER NOT NULL"))
        if "order_type" in refreshed_columns:
            conn.execute(text("ALTER TABLE offline_orders MODIFY COLUMN order_type VARCHAR(20) NOT NULL DEFAULT 'purchase'"))
        if "created_by" in refreshed_columns:
            conn.execute(text("ALTER TABLE offline_orders MODIFY COLUMN created_by INTEGER NOT NULL"))


def _ensure_user_api_key_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        return

    if "user_api_key" not in table_names:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE user_api_key (
                        id INTEGER NOT NULL AUTO_INCREMENT,
                        user_id INTEGER NOT NULL,
                        subs_type VARCHAR(50) NOT NULL DEFAULT '',
                        expire_time DATETIME NULL,
                        api_key VARCHAR(35) NOT NULL,
                        key_name VARCHAR(100) NOT NULL DEFAULT '',
                        status VARCHAR(20) NOT NULL DEFAULT 'enabled',
                        is_delete BOOLEAN NOT NULL DEFAULT 0,
                        key_prefix VARCHAR(8) NOT NULL DEFAULT '',
                        key_last4 VARCHAR(4) NOT NULL DEFAULT '',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (id),
                        UNIQUE KEY uq_user_api_key_api_key (api_key),
                        INDEX ix_user_api_key_user_id (user_id),
                        INDEX ix_user_api_key_status (status),
                        INDEX ix_user_api_key_is_delete (is_delete),
                        CONSTRAINT fk_user_api_key_user_id FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                    """
                )
            )
        return

    user_api_key_columns = {col["name"] for col in inspector.get_columns("user_api_key")}
    with engine.begin() as conn:
        if "last_used_at" in user_api_key_columns:
            conn.execute(text("ALTER TABLE user_api_key DROP COLUMN last_used_at"))
        if "last_used_ip" in user_api_key_columns:
            conn.execute(text("ALTER TABLE user_api_key DROP COLUMN last_used_ip"))
        if "subs_type" not in user_api_key_columns:
            conn.execute(text("ALTER TABLE user_api_key ADD COLUMN subs_type VARCHAR(50) NOT NULL DEFAULT '' AFTER user_id"))
        if "expire_time" not in user_api_key_columns:
            conn.execute(text("ALTER TABLE user_api_key ADD COLUMN expire_time DATETIME NULL AFTER subs_type"))
        if "api_key" not in user_api_key_columns:
            conn.execute(text("ALTER TABLE user_api_key ADD COLUMN api_key VARCHAR(35) NOT NULL AFTER expire_time"))
        if "key_name" not in user_api_key_columns:
            conn.execute(text("ALTER TABLE user_api_key ADD COLUMN key_name VARCHAR(100) NOT NULL DEFAULT '' AFTER api_key"))
        if "status" not in user_api_key_columns:
            conn.execute(text("ALTER TABLE user_api_key ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'enabled' AFTER key_name"))
        if "is_delete" not in user_api_key_columns:
            conn.execute(text("ALTER TABLE user_api_key ADD COLUMN is_delete BOOLEAN NOT NULL DEFAULT 0 AFTER status"))
        if "key_prefix" not in user_api_key_columns:
            conn.execute(text("ALTER TABLE user_api_key ADD COLUMN key_prefix VARCHAR(8) NOT NULL DEFAULT '' AFTER is_delete"))
        if "key_last4" not in user_api_key_columns:
            conn.execute(text("ALTER TABLE user_api_key ADD COLUMN key_last4 VARCHAR(4) NOT NULL DEFAULT '' AFTER key_prefix"))
        if "created_at" not in user_api_key_columns:
            conn.execute(text("ALTER TABLE user_api_key ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "updated_at" not in user_api_key_columns:
            conn.execute(text("ALTER TABLE user_api_key ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))


def _drop_legacy_user_credits_column():
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    user_columns = {col["name"] for col in inspector.get_columns("users")}
    if "credits" not in user_columns:
        return
    if "user_credits" not in inspector.get_table_names():
        return

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users DROP COLUMN credits"))


def _ensure_user_identity_schema():
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    user_columns = {col["name"] for col in inspector.get_columns("users")}
    with engine.begin() as conn:
        if "email" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(255) NULL"))
        if "email_verified" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0"))

    inspector = inspect(engine)
    unique_username_indexes: set[str] = set()
    has_plain_username_index = False
    has_email_unique_index = False

    for index in inspector.get_indexes("users"):
        columns = index.get("column_names") or []
        if columns == ["username"]:
            if index.get("unique") and index.get("name"):
                unique_username_indexes.add(index["name"])
            else:
                has_plain_username_index = True
        if columns == ["email"] and index.get("unique"):
            has_email_unique_index = True

    for constraint in inspector.get_unique_constraints("users"):
        columns = constraint.get("column_names") or []
        if columns == ["username"] and constraint.get("name"):
            unique_username_indexes.add(constraint["name"])
        if columns == ["email"]:
            has_email_unique_index = True

    with engine.begin() as conn:
        for index_name in sorted(unique_username_indexes):
            safe_index_name = index_name.replace("`", "")
            conn.execute(text(f"ALTER TABLE users DROP INDEX `{safe_index_name}`"))

        if not has_email_unique_index:
            conn.execute(text("CREATE UNIQUE INDEX uq_users_email ON users (email)"))

        if not has_plain_username_index:
            conn.execute(text("CREATE INDEX ix_users_username ON users (username)"))


def _has_unique_index(inspector, table_name: str, column_name: str) -> bool:
    for index in inspector.get_indexes(table_name):
        if index.get("unique") and (index.get("column_names") or []) == [column_name]:
            return True
    for constraint in inspector.get_unique_constraints(table_name):
        if (constraint.get("column_names") or []) == [column_name]:
            return True
    return False


def _ensure_business_id_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names and "tasks" not in table_names:
        return

    with engine.begin() as conn:
        if "users" in table_names:
            user_columns = {col["name"] for col in inspector.get_columns("users")}
            if "business_id" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN business_id VARCHAR(32) NULL"))
        if "tasks" in table_names:
            task_columns = {col["name"] for col in inspector.get_columns("tasks")}
            if "business_id" not in task_columns:
                conn.execute(text("ALTER TABLE tasks ADD COLUMN business_id VARCHAR(32) NULL"))
        if "users" in table_names:
            missing_user_ids = conn.execute(
                text("SELECT id FROM users WHERE business_id IS NULL OR business_id = ''")
            ).scalars().all()
            for user_id in missing_user_ids:
                conn.execute(
                    text("UPDATE users SET business_id = :business_id WHERE id = :id"),
                    {"business_id": generate_business_id(), "id": user_id},
                )
        if "tasks" in table_names:
            missing_task_ids = conn.execute(
                text("SELECT id FROM tasks WHERE business_id IS NULL OR business_id = ''")
            ).scalars().all()
            for task_id in missing_task_ids:
                conn.execute(
                    text("UPDATE tasks SET business_id = :business_id WHERE id = :id"),
                    {"business_id": generate_business_id(), "id": task_id},
                )

    inspector = inspect(engine)
    with engine.begin() as conn:
        if "users" in table_names and not _has_unique_index(inspector, "users", "business_id"):
            conn.execute(text("CREATE UNIQUE INDEX uq_users_business_id ON users (business_id)"))
        if "tasks" in table_names and not _has_unique_index(inspector, "tasks", "business_id"):
            conn.execute(text("CREATE UNIQUE INDEX uq_tasks_business_id ON tasks (business_id)"))
        if "users" in table_names:
            conn.execute(text("ALTER TABLE users MODIFY COLUMN business_id VARCHAR(32) NOT NULL"))
        if "tasks" in table_names:
            conn.execute(text("ALTER TABLE tasks MODIFY COLUMN business_id VARCHAR(32) NOT NULL"))


def _ensure_image_required_columns():
    inspector = inspect(engine)
    if "images" not in inspector.get_table_names():
        return

    image_columns = {col["name"] for col in inspector.get_columns("images")}
    with engine.begin() as conn:
        if "is_deleted" not in image_columns:
            conn.execute(text("ALTER TABLE images ADD COLUMN is_deleted BOOLEAN DEFAULT 0"))
        if "deleted_at" not in image_columns:
            conn.execute(text("ALTER TABLE images ADD COLUMN deleted_at DATETIME"))
        if "preview_url" not in image_columns:
            conn.execute(text("ALTER TABLE images ADD COLUMN preview_url VARCHAR(500) DEFAULT ''"))
        if "image_format" not in image_columns:
            conn.execute(text("ALTER TABLE images ADD COLUMN image_format VARCHAR(20) DEFAULT ''"))
        if "image_size_bytes" not in image_columns:
            conn.execute(text("ALTER TABLE images ADD COLUMN image_size_bytes INTEGER DEFAULT 0"))
        if "request_started_at" not in image_columns:
            conn.execute(text("ALTER TABLE images ADD COLUMN request_started_at DATETIME NULL"))
        if "request_finished_at" not in image_columns:
            conn.execute(text("ALTER TABLE images ADD COLUMN request_finished_at DATETIME NULL"))

    image_indexes = {index["name"] for index in inspect(engine).get_indexes("images")}
    with engine.begin() as conn:
        if "idx_images_request_finished_at" not in image_indexes:
            conn.execute(text("CREATE INDEX idx_images_request_finished_at ON images (request_finished_at)"))


def _ensure_prompt_history_columns():
    inspector = inspect(engine)
    if "prompt_history" not in inspector.get_table_names():
        return

    prompt_history_columns_info = inspector.get_columns("prompt_history")
    prompt_history_columns = {col["name"] for col in prompt_history_columns_info}
    prompt_column = next((col for col in prompt_history_columns_info if col["name"] == "prompt"), None)
    with engine.begin() as conn:
        if prompt_column is not None and "VARCHAR(2000)" in str(prompt_column["type"]).upper():
            conn.execute(text("ALTER TABLE prompt_history MODIFY COLUMN prompt VARCHAR(5000) NOT NULL"))
        if "mode" not in prompt_history_columns:
            conn.execute(text("ALTER TABLE prompt_history ADD COLUMN mode VARCHAR(20) DEFAULT 'generate'"))
        if "source_image" not in prompt_history_columns:
            conn.execute(text("ALTER TABLE prompt_history ADD COLUMN source_image VARCHAR(500) DEFAULT ''"))


def _ensure_prompt_optimize_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "prompt_optimize_styles" not in table_names:
        from app.models.prompt_optimize_style import PromptOptimizeStyle

        PromptOptimizeStyle.__table__.create(bind=engine)
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
    if "prompt_optimize_tasks" not in table_names:
        from app.models.prompt_optimize_task import PromptOptimizeTask

        PromptOptimizeTask.__table__.create(bind=engine)
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
    if "prompt_optimize_tasks" not in table_names or "prompt_optimize_styles" not in table_names:
        return

    style_columns = {col["name"] for col in inspector.get_columns("prompt_optimize_styles")}
    style_indexes = {index["name"] for index in inspector.get_indexes("prompt_optimize_styles")}
    task_columns = {col["name"] for col in inspector.get_columns("prompt_optimize_tasks")}
    task_indexes = {index["name"] for index in inspector.get_indexes("prompt_optimize_tasks")}

    with engine.begin() as conn:
        if "description" not in style_columns:
            conn.execute(text("ALTER TABLE prompt_optimize_styles ADD COLUMN description VARCHAR(255) NOT NULL DEFAULT ''"))
        if "sort_order" not in style_columns:
            conn.execute(text("ALTER TABLE prompt_optimize_styles ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 100"))
        if "status" not in style_columns:
            conn.execute(text("ALTER TABLE prompt_optimize_styles ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'enabled'"))
        if "is_default" not in style_columns:
            conn.execute(text("ALTER TABLE prompt_optimize_styles ADD COLUMN is_default BOOLEAN NOT NULL DEFAULT 0"))
        if "is_deleted" not in style_columns:
            conn.execute(text("ALTER TABLE prompt_optimize_styles ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0"))
        if "created_at" not in style_columns:
            conn.execute(text("ALTER TABLE prompt_optimize_styles ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "updated_at" not in style_columns:
            conn.execute(text("ALTER TABLE prompt_optimize_styles ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))

        conn.execute(text("UPDATE prompt_optimize_styles SET description = '' WHERE description IS NULL"))
        conn.execute(text("UPDATE prompt_optimize_styles SET status = 'enabled' WHERE status IS NULL OR status = ''"))
        conn.execute(text("UPDATE prompt_optimize_styles SET sort_order = 100 WHERE sort_order IS NULL"))
        conn.execute(text("UPDATE prompt_optimize_styles SET is_default = 0 WHERE is_default IS NULL"))
        conn.execute(text("UPDATE prompt_optimize_styles SET is_deleted = 0 WHERE is_deleted IS NULL"))

        if "idx_prompt_optimize_styles_sort" not in style_indexes:
            conn.execute(text("CREATE INDEX idx_prompt_optimize_styles_sort ON prompt_optimize_styles (sort_order, id)"))
        if "idx_prompt_optimize_styles_status_default" not in style_indexes:
            conn.execute(text("CREATE INDEX idx_prompt_optimize_styles_status_default ON prompt_optimize_styles (status, is_default, is_deleted)"))

        if "style_id" not in task_columns:
            conn.execute(text("ALTER TABLE prompt_optimize_tasks ADD COLUMN style_id INTEGER NULL"))
        if "style_name_snapshot" not in task_columns:
            conn.execute(text("ALTER TABLE prompt_optimize_tasks ADD COLUMN style_name_snapshot VARCHAR(100) NOT NULL DEFAULT ''"))
        conn.execute(text("UPDATE prompt_optimize_tasks SET style_name_snapshot = '' WHERE style_name_snapshot IS NULL"))
        if "idx_prompt_optimize_tasks_style_id" not in task_indexes:
            conn.execute(text("CREATE INDEX idx_prompt_optimize_tasks_style_id ON prompt_optimize_tasks (style_id)"))

        conn.execute(text(
            """
            INSERT INTO prompt_optimize_styles (name, description, style_prompt, sort_order, status, is_default, is_deleted)
            SELECT '通用优化', '默认风格，适合通用中文生图提示词补全',
                   '在保留用户原始意图前提下，补全构图、镜头、光线、色彩、材质、氛围和画面细节，输出适合直接生图的中文提示词。',
                   10, 'enabled', 1, 0
            WHERE NOT EXISTS (
              SELECT 1 FROM prompt_optimize_styles
              WHERE name = '通用优化' AND is_deleted = 0
            )
            """
        ))


def _ensure_task_credit_cost_column():
    inspector = inspect(engine)
    if "tasks" not in inspector.get_table_names():
        return

    task_columns = {col["name"] for col in inspector.get_columns("tasks")}
    if (
        "credit_cost" in task_columns
        and "custom_size" in task_columns
        and "enqueued_at" in task_columns
        and "request_started_at" in task_columns
        and "request_finished_at" in task_columns
        and "source" in task_columns
        and "provider_api_config_id" in task_columns
        and "provider_task_id" in task_columns
        and "provider_status" in task_columns
        and "provider_error_message" in task_columns
        and "provider_response_preview" in task_columns
        and "poll_count" in task_columns
        and "last_polled_at" in task_columns
        and "next_poll_at" in task_columns
        and "used_fallback_api" in task_columns
        and "provider_started_at" in task_columns
    ):
        return

    with engine.begin() as conn:
        if "credit_cost" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN credit_cost INTEGER DEFAULT 0"))
        if "custom_size" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN custom_size VARCHAR(50) DEFAULT ''"))
        if "enqueued_at" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN enqueued_at DATETIME"))
        if "request_started_at" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN request_started_at DATETIME"))
        if "request_finished_at" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN request_finished_at DATETIME"))
        if "source" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN source VARCHAR(20) DEFAULT 'web'"))
        if "provider_api_config_id" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN provider_api_config_id INTEGER NULL"))
        if "provider_task_id" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN provider_task_id VARCHAR(255) DEFAULT ''"))
        if "provider_status" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN provider_status VARCHAR(50) DEFAULT ''"))
        if "provider_error_message" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN provider_error_message TEXT"))
        if "provider_response_preview" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN provider_response_preview TEXT"))
        if "poll_count" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN poll_count INTEGER NOT NULL DEFAULT 0"))
        if "last_polled_at" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN last_polled_at DATETIME"))
        if "next_poll_at" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN next_poll_at DATETIME"))
        if "used_fallback_api" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN used_fallback_api BOOLEAN NOT NULL DEFAULT 0"))
        if "provider_started_at" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN provider_started_at DATETIME"))
        conn.execute(text("UPDATE tasks SET used_fallback_api = 0 WHERE used_fallback_api IS NULL"))
        if "provider_task_id" in task_columns:
            conn.execute(text("UPDATE tasks SET provider_task_id = '' WHERE provider_task_id IS NULL"))
        if "provider_status" in task_columns:
            conn.execute(text("UPDATE tasks SET provider_status = '' WHERE provider_status IS NULL"))
        if "poll_count" in task_columns:
            conn.execute(text("UPDATE tasks SET poll_count = 0 WHERE poll_count IS NULL"))


def _ensure_task_api_attempt_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "tasks" not in table_names:
        return
    if "task_api_attempts" not in table_names:
        from app.models.task_api_attempt import TaskApiAttempt

        TaskApiAttempt.__table__.create(bind=engine)
        inspector = inspect(engine)

    attempt_columns = {col["name"] for col in inspector.get_columns("task_api_attempts")}
    with engine.begin() as conn:
        if "image_id" not in attempt_columns:
            conn.execute(text("ALTER TABLE task_api_attempts ADD COLUMN image_id INTEGER NULL"))
        if "image_index" not in attempt_columns:
            conn.execute(text("ALTER TABLE task_api_attempts ADD COLUMN image_index INTEGER NULL"))
        if "api_config_id" not in attempt_columns:
            conn.execute(text("ALTER TABLE task_api_attempts ADD COLUMN api_config_id INTEGER NULL"))
        if "api_config_name" not in attempt_columns:
            conn.execute(text("ALTER TABLE task_api_attempts ADD COLUMN api_config_name VARCHAR(100) NOT NULL DEFAULT ''"))
        if "attempt_index" not in attempt_columns:
            conn.execute(text("ALTER TABLE task_api_attempts ADD COLUMN attempt_index INTEGER NOT NULL DEFAULT 1"))
        if "is_fallback" not in attempt_columns:
            conn.execute(text("ALTER TABLE task_api_attempts ADD COLUMN is_fallback BOOLEAN NOT NULL DEFAULT 0"))
        if "status" not in attempt_columns:
            conn.execute(text("ALTER TABLE task_api_attempts ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'failed'"))
        if "http_status" not in attempt_columns:
            conn.execute(text("ALTER TABLE task_api_attempts ADD COLUMN http_status INTEGER NULL"))
        if "error_message" not in attempt_columns:
            conn.execute(text("ALTER TABLE task_api_attempts ADD COLUMN error_message TEXT"))
        if "duration_ms" not in attempt_columns:
            conn.execute(text("ALTER TABLE task_api_attempts ADD COLUMN duration_ms INTEGER NULL"))
        if "external_http_ms" not in attempt_columns:
            conn.execute(text("ALTER TABLE task_api_attempts ADD COLUMN external_http_ms INTEGER NULL"))
        if "result_download_ms" not in attempt_columns:
            conn.execute(text("ALTER TABLE task_api_attempts ADD COLUMN result_download_ms INTEGER NULL"))
        if "cos_upload_ms" not in attempt_columns:
            conn.execute(text("ALTER TABLE task_api_attempts ADD COLUMN cos_upload_ms INTEGER NULL"))
        if "response_preview" not in attempt_columns:
            conn.execute(text("ALTER TABLE task_api_attempts ADD COLUMN response_preview TEXT"))
        if "created_at" not in attempt_columns:
            conn.execute(text("ALTER TABLE task_api_attempts ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))


def _ensure_external_api_config_required_columns():
    inspector = inspect(engine)
    if "external_api_configs" not in inspector.get_table_names():
        return

    external_api_columns = {col["name"] for col in inspector.get_columns("external_api_configs")}
    with engine.begin() as conn:
        if "request_format" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN request_format VARCHAR(20) DEFAULT 'json'"))
        if "call_mode" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN call_mode VARCHAR(20) DEFAULT 'sync'"))
        if "submit_success_statuses_json" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN submit_success_statuses_json TEXT"))
        if "poll_url" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN poll_url VARCHAR(500) DEFAULT ''"))
        if "poll_method" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN poll_method VARCHAR(10) DEFAULT 'GET'"))
        if "poll_headers_json" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN poll_headers_json TEXT"))
        if "poll_payload_json" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN poll_payload_json TEXT"))
        if "task_id_field" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN task_id_field VARCHAR(255) DEFAULT ''"))
        if "result_status_field" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN result_status_field VARCHAR(255) DEFAULT ''"))
        if "result_success_values_json" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN result_success_values_json TEXT"))
        if "result_failed_values_json" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN result_failed_values_json TEXT"))
        if "result_error_field" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN result_error_field VARCHAR(255) DEFAULT ''"))
        if "poll_result_base64_field" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN poll_result_base64_field VARCHAR(255) DEFAULT ''"))
        if "poll_result_url_field" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN poll_result_url_field VARCHAR(255) DEFAULT ''"))
        if "poll_interval_seconds" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN poll_interval_seconds INTEGER DEFAULT 5"))
        if "poll_timeout_seconds" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN poll_timeout_seconds INTEGER DEFAULT 600"))
        if "supports_inpaint" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN supports_inpaint BOOLEAN DEFAULT 0"))
        if "is_active_inpaint" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN is_active_inpaint BOOLEAN DEFAULT 0"))
        if "supports_smart_cutout" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN supports_smart_cutout BOOLEAN DEFAULT 0"))
        if "is_active_smart_cutout" not in external_api_columns:
            conn.execute(text("ALTER TABLE external_api_configs ADD COLUMN is_active_smart_cutout BOOLEAN DEFAULT 0"))
        conn.execute(
            text(
                """
                UPDATE external_api_configs
                SET request_format = 'json'
                WHERE request_format IS NULL OR request_format = ''
                """
            )
        )
        conn.execute(text("UPDATE external_api_configs SET call_mode = 'sync' WHERE call_mode IS NULL OR call_mode = ''"))
        conn.execute(text("UPDATE external_api_configs SET poll_url = '' WHERE poll_url IS NULL"))
        conn.execute(text("UPDATE external_api_configs SET task_id_field = '' WHERE task_id_field IS NULL"))
        conn.execute(text("UPDATE external_api_configs SET result_status_field = '' WHERE result_status_field IS NULL"))
        conn.execute(text("UPDATE external_api_configs SET result_error_field = '' WHERE result_error_field IS NULL"))
        conn.execute(text("UPDATE external_api_configs SET poll_result_base64_field = '' WHERE poll_result_base64_field IS NULL"))
        conn.execute(text("UPDATE external_api_configs SET poll_result_url_field = '' WHERE poll_result_url_field IS NULL"))
        conn.execute(text("UPDATE external_api_configs SET poll_method = 'GET' WHERE poll_method IS NULL OR poll_method = ''"))
        conn.execute(text("UPDATE external_api_configs SET poll_headers_json = '{}' WHERE poll_headers_json IS NULL OR poll_headers_json = ''"))
        conn.execute(text("UPDATE external_api_configs SET poll_payload_json = '{}' WHERE poll_payload_json IS NULL OR poll_payload_json = ''"))
        conn.execute(text("UPDATE external_api_configs SET result_success_values_json = '[\"success\", \"succeeded\", \"completed\"]' WHERE result_success_values_json IS NULL OR result_success_values_json = ''"))
        conn.execute(text("UPDATE external_api_configs SET result_failed_values_json = '[\"failed\", \"error\", \"cancelled\"]' WHERE result_failed_values_json IS NULL OR result_failed_values_json = ''"))
        conn.execute(text("UPDATE external_api_configs SET submit_success_statuses_json = '[200, 201, 202]' WHERE submit_success_statuses_json IS NULL OR submit_success_statuses_json = ''"))
        conn.execute(text("UPDATE external_api_configs SET poll_interval_seconds = 5 WHERE poll_interval_seconds IS NULL OR poll_interval_seconds <= 0"))
        conn.execute(text("UPDATE external_api_configs SET poll_timeout_seconds = 600 WHERE poll_timeout_seconds IS NULL OR poll_timeout_seconds <= 0"))


def _ensure_generation_scene_category_schema():
    inspector = inspect(engine)
    if "generation_scene_categories" not in inspector.get_table_names():
        from app.models.generation_scene_category import GenerationSceneCategory

        GenerationSceneCategory.__table__.create(bind=engine)
        return

    category_columns = {col["name"] for col in inspector.get_columns("generation_scene_categories")}
    category_indexes = {index["name"] for index in inspector.get_indexes("generation_scene_categories")}
    with engine.begin() as conn:
        if "scene_type" not in category_columns:
            conn.execute(
                text(
                    "ALTER TABLE generation_scene_categories "
                    "ADD COLUMN scene_type VARCHAR(20) NOT NULL DEFAULT 'generate'"
                )
            )
        if "idx_generation_scene_categories_scene_type" not in category_indexes:
            conn.execute(
                text(
                    "CREATE INDEX idx_generation_scene_categories_scene_type "
                    "ON generation_scene_categories (scene_type, is_deleted)"
                )
            )


def _ensure_scene_binding_required_columns():
    inspector = inspect(engine)
    if "external_api_scene_bindings" not in inspector.get_table_names():
        return

    scene_binding_columns = {col["name"] for col in inspector.get_columns("external_api_scene_bindings")}
    with engine.begin() as conn:
        if "is_deleted" not in scene_binding_columns:
            conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN is_deleted BOOLEAN DEFAULT 0"))
        if "hide_aspect_ratio" not in scene_binding_columns:
            conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN hide_aspect_ratio BOOLEAN DEFAULT 0"))
        if "hide_resolution" not in scene_binding_columns:
            conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN hide_resolution BOOLEAN DEFAULT 0"))
        if "hide_custom_size" not in scene_binding_columns:
            conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN hide_custom_size BOOLEAN DEFAULT 1"))
        if "custom_size_min" not in scene_binding_columns:
            conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN custom_size_min INTEGER DEFAULT 256"))
        if "custom_size_max" not in scene_binding_columns:
            conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN custom_size_max INTEGER DEFAULT 4096"))
        if "custom_size_step" not in scene_binding_columns:
            conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN custom_size_step INTEGER DEFAULT 8"))
        if "max_reference_images" not in scene_binding_columns:
            conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN max_reference_images INTEGER DEFAULT 0"))
        if "aspect_ratio_options_json" not in scene_binding_columns:
            conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN aspect_ratio_options_json TEXT"))
        if "image_size_options_json" not in scene_binding_columns:
            conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN image_size_options_json TEXT"))
        if "custom_size_options_json" not in scene_binding_columns:
            conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN custom_size_options_json TEXT"))
        if "resolution_mapping_json" not in scene_binding_columns:
            conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN resolution_mapping_json TEXT"))
        if "resolution_credit_costs_json" not in scene_binding_columns:
            conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN resolution_credit_costs_json TEXT"))
        if "backup_api_config_id" not in scene_binding_columns:
            conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN backup_api_config_id INTEGER"))
        conn.execute(
            text(
                """
                UPDATE external_api_scene_bindings
                SET is_deleted = 0
                WHERE is_deleted IS NULL
                """
            )
        )
        conn.execute(
            text(
                """
                UPDATE external_api_scene_bindings
                SET aspect_ratio_options_json = '[]'
                WHERE aspect_ratio_options_json IS NULL
                """
            )
        )
        conn.execute(
            text(
                """
                UPDATE external_api_scene_bindings
                SET image_size_options_json = '[]'
                WHERE image_size_options_json IS NULL
                """
            )
        )
        conn.execute(
            text(
                """
                UPDATE external_api_scene_bindings
                SET custom_size_options_json = '[]'
                WHERE custom_size_options_json IS NULL
                """
            )
        )
        conn.execute(
            text(
                """
                UPDATE external_api_scene_bindings
                SET resolution_mapping_json = '{}'
                WHERE resolution_mapping_json IS NULL
                """
            )
        )
        conn.execute(
            text(
                """
                UPDATE external_api_scene_bindings
                SET resolution_credit_costs_json = '{}'
                WHERE resolution_credit_costs_json IS NULL
                """
            )
        )


def _ensure_chat_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "chat_external_api_configs" not in table_names:
        from app.models.chat_external_api_config import ChatExternalApiConfig

        ChatExternalApiConfig.__table__.create(bind=engine)
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
    if "chat_external_api_scene_bindings" not in table_names:
        from app.models.chat_external_api_scene_binding import ChatExternalApiSceneBinding

        ChatExternalApiSceneBinding.__table__.create(bind=engine)
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
    if "chat_sessions" not in table_names:
        from app.models.chat_session import ChatSession

        ChatSession.__table__.create(bind=engine)
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
    if "chat_messages" not in table_names:
        from app.models.chat_message import ChatMessage

        ChatMessage.__table__.create(bind=engine)
        inspector = inspect(engine)
    if "chat_messages" not in set(inspector.get_table_names()):
        return

    message_columns = {col["name"] for col in inspector.get_columns("chat_messages")}
    message_indexes = {index["name"] for index in inspector.get_indexes("chat_messages")}
    session_columns = {col["name"] for col in inspector.get_columns("chat_sessions")} if "chat_sessions" in set(inspector.get_table_names()) else set()
    session_indexes = {index["name"] for index in inspector.get_indexes("chat_sessions")} if "chat_sessions" in set(inspector.get_table_names()) else set()
    scene_table_names = set(inspector.get_table_names())
    scene_columns = (
        {col["name"] for col in inspector.get_columns("chat_external_api_scene_bindings")}
        if "chat_external_api_scene_bindings" in scene_table_names
        else set()
    )
    with engine.begin() as conn:
        if "chat_external_api_scene_bindings" in scene_table_names and "starter_prompts_json" not in scene_columns:
            # MySQL 部分版本不允许 TEXT 带 DEFAULT，先可空加列再回填
            conn.execute(
                text(
                    "ALTER TABLE chat_external_api_scene_bindings "
                    "ADD COLUMN starter_prompts_json TEXT NULL"
                )
            )
            default_starter_prompts = (
                '[{"tag":"生图","text":"怎么样才能让 AI 生图更准确、更好看？有哪些关键方法和常见坑？"},'
                '{"tag":"生图","text":"我想做电商产品图，白底运动鞋怎么拍出质感和卖点？"},'
                '{"tag":"生图","text":"有一张人像照片，想改成赛博朋克风格，该怎么操作更稳？"},'
                '{"tag":"生视频","text":"怎么样才能让 AI 生视频更稳、更自然？有哪些关键方法和常见坑？"}]'
            )
            conn.execute(
                text(
                    "UPDATE chat_external_api_scene_bindings "
                    "SET starter_prompts_json = :prompts "
                    "WHERE starter_prompts_json IS NULL OR starter_prompts_json = '' OR starter_prompts_json = '[]'"
                ),
                {"prompts": default_starter_prompts},
            )
        if "reply_to_message_id" not in message_columns:
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN reply_to_message_id INTEGER NULL"))
        if "provider_response_preview" not in message_columns:
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN provider_response_preview TEXT NULL"))
        if "images_json" not in message_columns:
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN images_json TEXT NULL"))
            conn.execute(text("UPDATE chat_messages SET images_json = '[]' WHERE images_json IS NULL"))
        if "extra_json" not in message_columns:
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN extra_json TEXT NULL"))
        if "idx_chat_messages_reply_to" not in message_indexes:
            conn.execute(text("CREATE INDEX idx_chat_messages_reply_to ON chat_messages (reply_to_message_id)"))
        if "chat_sessions" in set(inspector.get_table_names()) and "session_id" not in session_columns:
            conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN session_id VARCHAR(16) NULL"))
        if "chat_sessions" in set(inspector.get_table_names()):
            # 兼容历史数据：按创建时间补齐 16 位公开 session_id
            rows = conn.execute(
                text(
                    "SELECT id, created_at FROM chat_sessions "
                    "WHERE session_id IS NULL OR session_id = ''"
                )
            ).fetchall()
            for row in rows:
                row_id = int(row[0])
                created_at = row[1]
                stamp = created_at.strftime("%y%m%d%H%M%S") if created_at is not None else datetime.now().strftime("%y%m%d%H%M%S")
                for _ in range(12):
                    suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
                    candidate = f"{stamp}{suffix}"
                    exists = conn.execute(
                        text("SELECT id FROM chat_sessions WHERE session_id = :sid LIMIT 1"),
                        {"sid": candidate},
                    ).first()
                    if exists:
                        continue
                    conn.execute(
                        text("UPDATE chat_sessions SET session_id = :sid WHERE id = :id"),
                        {"sid": candidate, "id": row_id},
                    )
                    break
            # SQLite / MySQL 兼容：尽量加上唯一索引
            if "uq_chat_sessions_session_id" not in session_indexes:
                try:
                    conn.execute(text("CREATE UNIQUE INDEX uq_chat_sessions_session_id ON chat_sessions (session_id)"))
                except Exception:
                    pass


def _ensure_video_external_api_config_schema():
    inspector = inspect(engine)
    if "video_external_api_configs" in inspector.get_table_names():
        return
    from app.models.video_external_api_config import VideoExternalApiConfig

    VideoExternalApiConfig.__table__.create(bind=engine)


def _ensure_video_scene_binding_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "video_external_api_configs" not in table_names:
        _ensure_video_external_api_config_schema()
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
    if "video_external_api_scene_bindings" in table_names:
        video_scene_columns = {col["name"] for col in inspector.get_columns("video_external_api_scene_bindings")}
        with engine.begin() as conn:
            if "hide_aspect_ratio" not in video_scene_columns:
                conn.execute(
                    text(
                        "ALTER TABLE video_external_api_scene_bindings "
                        "ADD COLUMN hide_aspect_ratio BOOLEAN NOT NULL DEFAULT 0"
                    )
                )
            if "credit_billing_mode" not in video_scene_columns:
                conn.execute(
                    text(
                        "ALTER TABLE video_external_api_scene_bindings "
                        "ADD COLUMN credit_billing_mode VARCHAR(20) NOT NULL DEFAULT 'fixed'"
                    )
                )
            if "per_second_credit_cost" not in video_scene_columns:
                conn.execute(
                    text(
                        "ALTER TABLE video_external_api_scene_bindings "
                        "ADD COLUMN per_second_credit_cost INTEGER NOT NULL DEFAULT 0"
                    )
                )
            if "aspect_ratio_options_json" not in video_scene_columns:
                conn.execute(
                    text(
                        "ALTER TABLE video_external_api_scene_bindings "
                        "ADD COLUMN aspect_ratio_options_json TEXT"
                    )
                )
            if "max_reference_images" not in video_scene_columns:
                conn.execute(
                    text(
                        "ALTER TABLE video_external_api_scene_bindings "
                        "ADD COLUMN max_reference_images INTEGER NOT NULL DEFAULT 1"
                    )
                )
            if "availability_mode" not in video_scene_columns:
                conn.execute(
                    text(
                        "ALTER TABLE video_external_api_scene_bindings "
                        "ADD COLUMN availability_mode VARCHAR(20) NOT NULL DEFAULT 'both'"
                    )
                )
            if "availability_modes_json" not in video_scene_columns:
                conn.execute(
                    text(
                        "ALTER TABLE video_external_api_scene_bindings "
                        "ADD COLUMN availability_modes_json TEXT"
                    )
                )
            conn.execute(
                text(
                    "UPDATE video_external_api_scene_bindings "
                    "SET credit_billing_mode = 'fixed' "
                    "WHERE credit_billing_mode IS NULL OR credit_billing_mode = ''"
                )
            )
            conn.execute(
                text(
                    "UPDATE video_external_api_scene_bindings "
                    "SET per_second_credit_cost = 0 "
                    "WHERE per_second_credit_cost IS NULL"
                )
            )
            conn.execute(
                text(
                    "UPDATE video_external_api_scene_bindings "
                    "SET aspect_ratio_options_json = '[]' "
                    "WHERE aspect_ratio_options_json IS NULL"
                )
            )
            conn.execute(
                text(
                    "UPDATE video_external_api_scene_bindings "
                    "SET max_reference_images = 1 "
                    "WHERE max_reference_images IS NULL"
                )
            )
            conn.execute(
                text(
                    "UPDATE video_external_api_scene_bindings "
                    "SET availability_mode = 'both' "
                    "WHERE availability_mode IS NULL OR availability_mode = ''"
                )
            )
            conn.execute(
                text(
                    "UPDATE video_external_api_scene_bindings "
                    "SET availability_modes_json = CASE "
                    "WHEN availability_mode = 'text_to_video' THEN '[\"text_to_video\"]' "
                    "WHEN availability_mode = 'image_to_video' THEN '[\"image_to_video\"]' "
                    "ELSE '[\"text_to_video\", \"image_to_video\"]' END "
                    "WHERE availability_modes_json IS NULL OR availability_modes_json = ''"
                )
            )
        return
    from app.models.video_external_api_scene_binding import VideoExternalApiSceneBinding

    VideoExternalApiSceneBinding.__table__.create(bind=engine)


def _ensure_video_task_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        return
    if "video_tasks" in table_names:
        video_task_columns = {col["name"] for col in inspector.get_columns("video_tasks")}
        with engine.begin() as conn:
            if "generation_mode" not in video_task_columns:
                conn.execute(text("ALTER TABLE video_tasks ADD COLUMN generation_mode VARCHAR(30) NOT NULL DEFAULT ''"))
            if "aspect_ratio" not in video_task_columns:
                conn.execute(text("ALTER TABLE video_tasks ADD COLUMN aspect_ratio VARCHAR(20) NOT NULL DEFAULT ''"))
            if "reference_images" not in video_task_columns:
                conn.execute(text("ALTER TABLE video_tasks ADD COLUMN reference_images TEXT"))
            conn.execute(
                text(
                    "UPDATE video_tasks "
                    "SET generation_mode = CASE "
                    "WHEN reference_images IS NULL OR reference_images = '' OR reference_images = '[]' THEN 'text_to_video' "
                    "ELSE 'image_to_video' END "
                    "WHERE generation_mode IS NULL OR generation_mode = ''"
                )
            )
        return
    from app.models.video_task import VideoTask

    VideoTask.__table__.create(bind=engine)


def _ensure_video_result_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "video_tasks" not in table_names:
        _ensure_video_task_schema()
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
    if "video_results" in table_names:
        return
    from app.models.video_result import VideoResult

    VideoResult.__table__.create(bind=engine)


def _ensure_video_task_api_attempt_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "video_tasks" not in table_names:
        _ensure_video_task_schema()
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
    if "video_results" not in table_names:
        _ensure_video_result_schema()
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
    if "video_external_api_configs" not in table_names:
        _ensure_video_external_api_config_schema()
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
    if "video_task_api_attempts" in table_names:
        return
    from app.models.video_task_api_attempt import VideoTaskApiAttempt

    VideoTaskApiAttempt.__table__.create(bind=engine)


def _ensure_feedback_schema():
    inspector = inspect(engine)
    if "feedback" not in inspector.get_table_names():
        return

    table_names = set(inspector.get_table_names())
    feedback_columns = {col["name"] for col in inspector.get_columns("feedback")}
    feedback_indexes = {index["name"] for index in inspector.get_indexes("feedback")}

    with engine.begin() as conn:
        if "business_id" not in feedback_columns:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN business_id VARCHAR(32) NULL"))
        if "user_id" not in feedback_columns:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN user_id INTEGER"))
        if "task_id" not in feedback_columns:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN task_id INTEGER"))
        elif engine.dialect.name == "mysql":
            conn.execute(text("ALTER TABLE feedback MODIFY COLUMN task_id INTEGER NULL"))
        if "content" not in feedback_columns:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN content TEXT"))
        if "feedback_type" not in feedback_columns:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN feedback_type VARCHAR(32) DEFAULT 'general'"))
        if "attachments_json" not in feedback_columns:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN attachments_json TEXT"))
        if "status" not in feedback_columns:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN status VARCHAR(20) DEFAULT 'pending'"))
        if "is_read" not in feedback_columns:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN is_read TINYINT(1) DEFAULT 0"))
        if "process_note" not in feedback_columns:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN process_note VARCHAR(5000) DEFAULT ''"))
        if "result_note" not in feedback_columns:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN result_note VARCHAR(5000) DEFAULT ''"))
        if "handled_by" not in feedback_columns:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN handled_by INTEGER"))
        if "handled_at" not in feedback_columns:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN handled_at DATETIME"))
        if "last_message_at" not in feedback_columns:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN last_message_at DATETIME"))
        if "user_last_read_at" not in feedback_columns:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN user_last_read_at DATETIME"))
        if "admin_last_read_at" not in feedback_columns:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN admin_last_read_at DATETIME"))
        if "created_at" not in feedback_columns:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "updated_at" not in feedback_columns:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))

        conn.execute(text("UPDATE feedback SET process_note = '' WHERE process_note IS NULL"))
        conn.execute(text("UPDATE feedback SET result_note = '' WHERE result_note IS NULL"))
        conn.execute(text("UPDATE feedback SET feedback_type = 'general' WHERE feedback_type IS NULL OR feedback_type = ''"))
        conn.execute(text("UPDATE feedback SET attachments_json = '[]' WHERE attachments_json IS NULL OR attachments_json = ''"))
        conn.execute(text("UPDATE feedback SET status = 'pending' WHERE status IS NULL OR status = ''"))
        conn.execute(text("UPDATE feedback SET is_read = 0 WHERE is_read IS NULL"))
        conn.execute(text("UPDATE feedback SET last_message_at = created_at WHERE last_message_at IS NULL"))

        if "ix_feedback_user_id" not in feedback_indexes:
            conn.execute(text("CREATE INDEX ix_feedback_user_id ON feedback (user_id)"))
        if "ix_feedback_task_id" not in feedback_indexes:
            conn.execute(text("CREATE INDEX ix_feedback_task_id ON feedback (task_id)"))
        if "ix_feedback_status" not in feedback_indexes:
            conn.execute(text("CREATE INDEX ix_feedback_status ON feedback (status)"))
        if "ix_feedback_feedback_type" not in feedback_indexes:
            conn.execute(text("CREATE INDEX ix_feedback_feedback_type ON feedback (feedback_type)"))
        if "ix_feedback_is_read" not in feedback_indexes:
            conn.execute(text("CREATE INDEX ix_feedback_is_read ON feedback (is_read)"))
        if "ix_feedback_handled_by" not in feedback_indexes:
            conn.execute(text("CREATE INDEX ix_feedback_handled_by ON feedback (handled_by)"))
        if "ix_feedback_last_message_at" not in feedback_indexes:
            conn.execute(text("CREATE INDEX ix_feedback_last_message_at ON feedback (last_message_at)"))

    if "feedback_messages" not in table_names:
        from app.models.feedback import FeedbackMessage

        FeedbackMessage.__table__.create(bind=engine)
        inspector = inspect(engine)

    message_indexes = {index["name"] for index in inspector.get_indexes("feedback_messages")}
    with engine.begin() as conn:
        if "ix_feedback_messages_feedback_created" not in message_indexes:
            conn.execute(text("CREATE INDEX ix_feedback_messages_feedback_created ON feedback_messages (feedback_id, created_at)"))

    from app.database import SessionLocal
    from app.models.feedback import Feedback, FeedbackMessage

    db = SessionLocal()
    try:
        changed = False
        rows = db.query(Feedback).filter((Feedback.business_id.is_(None)) | (Feedback.business_id == "")).all()
        for row in rows:
            row.business_id = generate_business_id()
            changed = True

        all_feedback = db.query(Feedback).all()
        for row in all_feedback:
            if row.last_message_at is None:
                row.last_message_at = row.created_at
                changed = True
            existing_message = db.query(FeedbackMessage.id).filter(FeedbackMessage.feedback_id == row.id).first()
            if not existing_message:
                db.add(FeedbackMessage(
                    feedback_id=row.id,
                    sender_role="user",
                    sender_id=row.user_id,
                    content=row.content or "",
                    attachments_json=row.attachments_json or "[]",
                    created_at=row.created_at,
                ))
                if row.user_last_read_at is None:
                    row.user_last_read_at = row.created_at
                changed = True
        if changed:
            db.commit()
    finally:
        db.close()

    refreshed_indexes = {index["name"] for index in inspect(engine).get_indexes("feedback")}
    if "ix_feedback_business_id" not in refreshed_indexes:
        with engine.begin() as conn:
            conn.execute(text("CREATE UNIQUE INDEX ix_feedback_business_id ON feedback (business_id)"))


def _ensure_system_message_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        return
    if "system_messages" not in table_names:
        from app.models.system_message import SystemMessage

        SystemMessage.__table__.create(bind=engine)
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
    if "system_message_recipients" not in table_names:
        from app.models.system_message import SystemMessageRecipient

        SystemMessageRecipient.__table__.create(bind=engine)
        inspector = inspect(engine)

    message_columns = {col["name"] for col in inspector.get_columns("system_messages")}
    recipient_columns = {col["name"] for col in inspector.get_columns("system_message_recipients")}
    message_indexes = {index["name"] for index in inspector.get_indexes("system_messages")}
    recipient_indexes = {index["name"] for index in inspector.get_indexes("system_message_recipients")}

    with engine.begin() as conn:
        if "business_id" not in message_columns:
            conn.execute(text("ALTER TABLE system_messages ADD COLUMN business_id VARCHAR(32) NULL"))
        if "subject" not in message_columns:
            conn.execute(text("ALTER TABLE system_messages ADD COLUMN subject VARCHAR(200) NOT NULL DEFAULT ''"))
        if "content_html" not in message_columns:
            conn.execute(text("ALTER TABLE system_messages ADD COLUMN content_html LONGTEXT"))
        if "content_text" not in message_columns:
            conn.execute(text("ALTER TABLE system_messages ADD COLUMN content_text LONGTEXT"))
        if "sender_id" not in message_columns:
            conn.execute(text("ALTER TABLE system_messages ADD COLUMN sender_id INTEGER"))
        if "recipient_scope" not in message_columns:
            conn.execute(text("ALTER TABLE system_messages ADD COLUMN recipient_scope VARCHAR(20) DEFAULT 'selected'"))
        if "recipient_count" not in message_columns:
            conn.execute(text("ALTER TABLE system_messages ADD COLUMN recipient_count INTEGER DEFAULT 0"))
        if "created_at" not in message_columns:
            conn.execute(text("ALTER TABLE system_messages ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "updated_at" not in message_columns:
            conn.execute(text("ALTER TABLE system_messages ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))

        if "message_id" not in recipient_columns:
            conn.execute(text("ALTER TABLE system_message_recipients ADD COLUMN message_id INTEGER"))
        if "user_id" not in recipient_columns:
            conn.execute(text("ALTER TABLE system_message_recipients ADD COLUMN user_id INTEGER"))
        if "is_read" not in recipient_columns:
            conn.execute(text("ALTER TABLE system_message_recipients ADD COLUMN is_read TINYINT(1) DEFAULT 0"))
        if "read_at" not in recipient_columns:
            conn.execute(text("ALTER TABLE system_message_recipients ADD COLUMN read_at DATETIME"))
        if "created_at" not in recipient_columns:
            conn.execute(text("ALTER TABLE system_message_recipients ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))

        conn.execute(text("UPDATE system_messages SET subject = '' WHERE subject IS NULL"))
        conn.execute(text("UPDATE system_messages SET content_html = '' WHERE content_html IS NULL"))
        conn.execute(text("UPDATE system_messages SET content_text = '' WHERE content_text IS NULL"))
        conn.execute(text("UPDATE system_messages SET recipient_scope = 'selected' WHERE recipient_scope IS NULL OR recipient_scope = ''"))
        conn.execute(text("UPDATE system_messages SET recipient_count = 0 WHERE recipient_count IS NULL"))
        conn.execute(text("UPDATE system_message_recipients SET is_read = 0 WHERE is_read IS NULL"))

        conn.execute(text("ALTER TABLE system_messages MODIFY COLUMN content_html LONGTEXT"))
        conn.execute(text("ALTER TABLE system_messages MODIFY COLUMN content_text LONGTEXT"))

        if "ix_system_messages_subject" not in message_indexes:
            conn.execute(text("CREATE INDEX ix_system_messages_subject ON system_messages (subject)"))
        if "ix_system_messages_sender_id" not in message_indexes:
            conn.execute(text("CREATE INDEX ix_system_messages_sender_id ON system_messages (sender_id)"))
        if "ix_system_messages_recipient_scope" not in message_indexes:
            conn.execute(text("CREATE INDEX ix_system_messages_recipient_scope ON system_messages (recipient_scope)"))
        if "ix_system_message_recipients_message_id" not in recipient_indexes:
            conn.execute(text("CREATE INDEX ix_system_message_recipients_message_id ON system_message_recipients (message_id)"))
        if "ix_system_message_recipients_user_id" not in recipient_indexes:
            conn.execute(text("CREATE INDEX ix_system_message_recipients_user_id ON system_message_recipients (user_id)"))
        if "ix_system_message_recipients_is_read" not in recipient_indexes:
            conn.execute(text("CREATE INDEX ix_system_message_recipients_is_read ON system_message_recipients (is_read)"))

    from app.database import SessionLocal
    from app.models.system_message import SystemMessage

    db = SessionLocal()
    try:
        changed = False
        rows = db.query(SystemMessage).filter((SystemMessage.business_id.is_(None)) | (SystemMessage.business_id == "")).all()
        for row in rows:
            row.business_id = generate_business_id()
            changed = True
        if changed:
            db.commit()
    finally:
        db.close()

    refreshed_indexes = {index["name"] for index in inspect(engine).get_indexes("system_messages")}
    refreshed_unique_constraints = {
        constraint["name"]
        for constraint in inspect(engine).get_unique_constraints("system_message_recipients")
    }
    with engine.begin() as conn:
        if "ix_system_messages_business_id" not in refreshed_indexes:
            conn.execute(text("CREATE UNIQUE INDEX ix_system_messages_business_id ON system_messages (business_id)"))
        if "uq_system_message_recipient_message_user" not in refreshed_unique_constraints:
            conn.execute(
                text(
                    """
                    CREATE UNIQUE INDEX uq_system_message_recipient_message_user
                    ON system_message_recipients (message_id, user_id)
                    """
                )
            )


def _ensure_update_log_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "update_logs" not in table_names:
        from app.models.update_log import UpdateLog

        UpdateLog.__table__.create(bind=engine)
        inspector = inspect(engine)

    update_log_columns = {col["name"] for col in inspector.get_columns("update_logs")}
    update_log_indexes = {index["name"] for index in inspector.get_indexes("update_logs")}

    with engine.begin() as conn:
        if "business_id" not in update_log_columns:
            conn.execute(text("ALTER TABLE update_logs ADD COLUMN business_id VARCHAR(32) NULL"))
        if "title" not in update_log_columns:
            conn.execute(text("ALTER TABLE update_logs ADD COLUMN title VARCHAR(200) NOT NULL DEFAULT ''"))
        if "content" not in update_log_columns:
            conn.execute(text("ALTER TABLE update_logs ADD COLUMN content TEXT"))
        if "tag_type" not in update_log_columns:
            conn.execute(text("ALTER TABLE update_logs ADD COLUMN tag_type VARCHAR(20) NOT NULL DEFAULT 'other'"))
        if "effective_at" not in update_log_columns:
            conn.execute(text("ALTER TABLE update_logs ADD COLUMN effective_at DATETIME NULL"))
        if "created_at" not in update_log_columns:
            conn.execute(text("ALTER TABLE update_logs ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "updated_at" not in update_log_columns:
            conn.execute(text("ALTER TABLE update_logs ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))

        conn.execute(text("UPDATE update_logs SET title = '' WHERE title IS NULL"))
        conn.execute(text("UPDATE update_logs SET content = '' WHERE content IS NULL"))
        conn.execute(text("UPDATE update_logs SET tag_type = 'other' WHERE tag_type IS NULL OR tag_type = ''"))
        conn.execute(text("UPDATE update_logs SET effective_at = COALESCE(created_at, CURRENT_TIMESTAMP) WHERE effective_at IS NULL"))

        if "ix_update_logs_title" not in update_log_indexes:
            conn.execute(text("CREATE INDEX ix_update_logs_title ON update_logs (title)"))
        if "ix_update_logs_tag_type" not in update_log_indexes:
            conn.execute(text("CREATE INDEX ix_update_logs_tag_type ON update_logs (tag_type)"))
        if "ix_update_logs_effective_at" not in update_log_indexes:
            conn.execute(text("CREATE INDEX ix_update_logs_effective_at ON update_logs (effective_at)"))
        if "idx_update_logs_effective_at_id" not in update_log_indexes:
            conn.execute(text("CREATE INDEX idx_update_logs_effective_at_id ON update_logs (effective_at, id)"))

    from app.database import SessionLocal
    from app.models.update_log import UpdateLog

    db = SessionLocal()
    try:
        changed = False
        rows = db.query(UpdateLog).filter((UpdateLog.business_id.is_(None)) | (UpdateLog.business_id == "")).all()
        for row in rows:
            row.business_id = generate_business_id()
            changed = True
        if changed:
            db.commit()
    finally:
        db.close()

    refreshed_indexes = {index["name"] for index in inspect(engine).get_indexes("update_logs")}
    with engine.begin() as conn:
        if "ix_update_logs_business_id" not in refreshed_indexes:
            conn.execute(text("CREATE UNIQUE INDEX ix_update_logs_business_id ON update_logs (business_id)"))


def _ensure_admin_ledger_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        return

    from app.models.admin_ledger import AdminLedger, AdminLedgerExpense, AdminLedgerLog

    if "admin_ledgers" not in table_names:
        AdminLedger.__table__.create(bind=engine)
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
    if "admin_ledger_expenses" not in table_names:
        AdminLedgerExpense.__table__.create(bind=engine)
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
    if "admin_ledger_logs" not in table_names:
        AdminLedgerLog.__table__.create(bind=engine)
        inspector = inspect(engine)

    ledger_columns = {col["name"] for col in inspector.get_columns("admin_ledgers")}
    ledger_indexes = {index["name"] for index in inspector.get_indexes("admin_ledgers")}
    with engine.begin() as conn:
        if "business_id" not in ledger_columns:
            conn.execute(text("ALTER TABLE admin_ledgers ADD COLUMN business_id VARCHAR(32) NULL"))
        if "ledger_month" not in ledger_columns:
            conn.execute(text("ALTER TABLE admin_ledgers ADD COLUMN ledger_month DATE NULL"))
        if "title" not in ledger_columns:
            conn.execute(text("ALTER TABLE admin_ledgers ADD COLUMN title VARCHAR(200) NOT NULL DEFAULT ''"))
        if "content" not in ledger_columns:
            conn.execute(text("ALTER TABLE admin_ledgers ADD COLUMN content TEXT"))
        if "description" not in ledger_columns:
            conn.execute(text("ALTER TABLE admin_ledgers ADD COLUMN description TEXT"))
        if "screenshot_urls_json" not in ledger_columns:
            conn.execute(text("ALTER TABLE admin_ledgers ADD COLUMN screenshot_urls_json TEXT"))
        if "income_snapshot_json" not in ledger_columns:
            conn.execute(text("ALTER TABLE admin_ledgers ADD COLUMN income_snapshot_json TEXT"))
        for column_name in ("online_revenue_fen", "redeem_revenue_fen", "offline_revenue_fen", "total_income_fen", "total_expense_fen", "net_income_fen"):
            if column_name not in ledger_columns:
                conn.execute(text(f"ALTER TABLE admin_ledgers ADD COLUMN {column_name} INTEGER NOT NULL DEFAULT 0"))
        if "created_by" not in ledger_columns:
            conn.execute(text("ALTER TABLE admin_ledgers ADD COLUMN created_by INTEGER NULL"))
        if "updated_by" not in ledger_columns:
            conn.execute(text("ALTER TABLE admin_ledgers ADD COLUMN updated_by INTEGER NULL"))
        if "created_at" not in ledger_columns:
            conn.execute(text("ALTER TABLE admin_ledgers ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "updated_at" not in ledger_columns:
            conn.execute(text("ALTER TABLE admin_ledgers ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        conn.execute(text("UPDATE admin_ledgers SET title = '' WHERE title IS NULL"))
        conn.execute(text("UPDATE admin_ledgers SET content = '' WHERE content IS NULL"))
        conn.execute(text("UPDATE admin_ledgers SET description = '' WHERE description IS NULL"))
        conn.execute(text("UPDATE admin_ledgers SET screenshot_urls_json = '[]' WHERE screenshot_urls_json IS NULL OR screenshot_urls_json = ''"))
        conn.execute(text("UPDATE admin_ledgers SET income_snapshot_json = '{}' WHERE income_snapshot_json IS NULL OR income_snapshot_json = ''"))
        if "ix_admin_ledgers_business_id" not in ledger_indexes:
            conn.execute(text("CREATE UNIQUE INDEX ix_admin_ledgers_business_id ON admin_ledgers (business_id)"))
        if "ix_admin_ledgers_ledger_month" not in ledger_indexes and "uq_admin_ledgers_ledger_month" not in ledger_indexes:
            conn.execute(text("CREATE UNIQUE INDEX ix_admin_ledgers_ledger_month ON admin_ledgers (ledger_month)"))

    expense_columns = {col["name"] for col in inspect(engine).get_columns("admin_ledger_expenses")}
    expense_indexes = {index["name"] for index in inspect(engine).get_indexes("admin_ledger_expenses")}
    with engine.begin() as conn:
        if "business_id" not in expense_columns:
            conn.execute(text("ALTER TABLE admin_ledger_expenses ADD COLUMN business_id VARCHAR(32) NULL"))
        if "ledger_id" not in expense_columns:
            conn.execute(text("ALTER TABLE admin_ledger_expenses ADD COLUMN ledger_id INTEGER NULL"))
        if "expense_type" not in expense_columns:
            conn.execute(text("ALTER TABLE admin_ledger_expenses ADD COLUMN expense_type VARCHAR(30) NOT NULL DEFAULT 'other'"))
        if "title" not in expense_columns:
            conn.execute(text("ALTER TABLE admin_ledger_expenses ADD COLUMN title VARCHAR(200) NOT NULL DEFAULT ''"))
        if "amount_fen" not in expense_columns:
            conn.execute(text("ALTER TABLE admin_ledger_expenses ADD COLUMN amount_fen INTEGER NOT NULL DEFAULT 0"))
        if "content" not in expense_columns:
            conn.execute(text("ALTER TABLE admin_ledger_expenses ADD COLUMN content TEXT"))
        if "description" not in expense_columns:
            conn.execute(text("ALTER TABLE admin_ledger_expenses ADD COLUMN description TEXT"))
        if "screenshot_urls_json" not in expense_columns:
            conn.execute(text("ALTER TABLE admin_ledger_expenses ADD COLUMN screenshot_urls_json TEXT"))
        if "sort_order" not in expense_columns:
            conn.execute(text("ALTER TABLE admin_ledger_expenses ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"))
        if "created_by" not in expense_columns:
            conn.execute(text("ALTER TABLE admin_ledger_expenses ADD COLUMN created_by INTEGER NULL"))
        if "updated_by" not in expense_columns:
            conn.execute(text("ALTER TABLE admin_ledger_expenses ADD COLUMN updated_by INTEGER NULL"))
        if "created_at" not in expense_columns:
            conn.execute(text("ALTER TABLE admin_ledger_expenses ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "updated_at" not in expense_columns:
            conn.execute(text("ALTER TABLE admin_ledger_expenses ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        conn.execute(text("UPDATE admin_ledger_expenses SET title = '' WHERE title IS NULL"))
        conn.execute(text("UPDATE admin_ledger_expenses SET content = '' WHERE content IS NULL"))
        conn.execute(text("UPDATE admin_ledger_expenses SET description = '' WHERE description IS NULL"))
        conn.execute(text("UPDATE admin_ledger_expenses SET screenshot_urls_json = '[]' WHERE screenshot_urls_json IS NULL OR screenshot_urls_json = ''"))
        if "ix_admin_ledger_expenses_business_id" not in expense_indexes:
            conn.execute(text("CREATE UNIQUE INDEX ix_admin_ledger_expenses_business_id ON admin_ledger_expenses (business_id)"))
        if "ix_admin_ledger_expenses_ledger_id" not in expense_indexes:
            conn.execute(text("CREATE INDEX ix_admin_ledger_expenses_ledger_id ON admin_ledger_expenses (ledger_id)"))

    log_columns = {col["name"] for col in inspect(engine).get_columns("admin_ledger_logs")}
    log_indexes = {index["name"] for index in inspect(engine).get_indexes("admin_ledger_logs")}
    with engine.begin() as conn:
        if "ledger_id" not in log_columns:
            conn.execute(text("ALTER TABLE admin_ledger_logs ADD COLUMN ledger_id INTEGER NULL"))
        if "operator_id" not in log_columns:
            conn.execute(text("ALTER TABLE admin_ledger_logs ADD COLUMN operator_id INTEGER NULL"))
        if "action" not in log_columns:
            conn.execute(text("ALTER TABLE admin_ledger_logs ADD COLUMN action VARCHAR(40) NOT NULL DEFAULT 'update'"))
        if "summary" not in log_columns:
            conn.execute(text("ALTER TABLE admin_ledger_logs ADD COLUMN summary VARCHAR(500) NOT NULL DEFAULT ''"))
        if "before_json" not in log_columns:
            conn.execute(text("ALTER TABLE admin_ledger_logs ADD COLUMN before_json TEXT"))
        if "after_json" not in log_columns:
            conn.execute(text("ALTER TABLE admin_ledger_logs ADD COLUMN after_json TEXT"))
        if "created_at" not in log_columns:
            conn.execute(text("ALTER TABLE admin_ledger_logs ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        conn.execute(text("UPDATE admin_ledger_logs SET summary = '' WHERE summary IS NULL"))
        conn.execute(text("UPDATE admin_ledger_logs SET before_json = '{}' WHERE before_json IS NULL OR before_json = ''"))
        conn.execute(text("UPDATE admin_ledger_logs SET after_json = '{}' WHERE after_json IS NULL OR after_json = ''"))
        if "ix_admin_ledger_logs_ledger_id" not in log_indexes:
            conn.execute(text("CREATE INDEX ix_admin_ledger_logs_ledger_id ON admin_ledger_logs (ledger_id)"))
        if "ix_admin_ledger_logs_created_at" not in log_indexes:
            conn.execute(text("CREATE INDEX ix_admin_ledger_logs_created_at ON admin_ledger_logs (created_at)"))

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        changed = False
        for row in db.query(AdminLedger).filter((AdminLedger.business_id.is_(None)) | (AdminLedger.business_id == "")).all():
            row.business_id = generate_business_id()
            changed = True
        for row in db.query(AdminLedgerExpense).filter((AdminLedgerExpense.business_id.is_(None)) | (AdminLedgerExpense.business_id == "")).all():
            row.business_id = generate_business_id()
            changed = True
        if changed:
            db.commit()
    finally:
        db.close()


def _ensure_history_pin_schema():
    inspector = inspect(engine)
    if "history_pins" not in inspector.get_table_names():
        from app.models.history_pin import HistoryPin

        HistoryPin.__table__.create(bind=engine)
        inspector = inspect(engine)

    history_pin_columns = {col["name"] for col in inspector.get_columns("history_pins")}
    history_pin_indexes = {index["name"] for index in inspector.get_indexes("history_pins")}

    with engine.begin() as conn:
        if "item_key" not in history_pin_columns:
            conn.execute(text("ALTER TABLE history_pins ADD COLUMN item_key VARCHAR(64)"))
        if "image_id" not in history_pin_columns:
            conn.execute(text("ALTER TABLE history_pins ADD COLUMN image_id INTEGER"))
        if "history_id" not in history_pin_columns:
            conn.execute(text("ALTER TABLE history_pins ADD COLUMN history_id INTEGER"))
        if "pinned_at" not in history_pin_columns:
            conn.execute(text("ALTER TABLE history_pins ADD COLUMN pinned_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "created_at" not in history_pin_columns:
            conn.execute(text("ALTER TABLE history_pins ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))

    refreshed_indexes = {index["name"] for index in inspect(engine).get_indexes("history_pins")}
    with engine.begin() as conn:
        if "ix_history_pins_user_pinned_at" not in refreshed_indexes:
            conn.execute(text("CREATE INDEX ix_history_pins_user_pinned_at ON history_pins (user_id, pinned_at DESC)"))
        if "ux_history_pins_user_item_key" not in refreshed_indexes:
            conn.execute(text("CREATE UNIQUE INDEX ux_history_pins_user_item_key ON history_pins (user_id, item_key)"))


def _ensure_user_asset_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        return

    if "user_asset_categories" not in table_names:
        from app.models.user_asset_category import UserAssetCategory

        UserAssetCategory.__table__.create(bind=engine)
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())

    if "user_assets" not in table_names:
        from app.models.user_asset import UserAsset

        UserAsset.__table__.create(bind=engine)
        inspector = inspect(engine)

    category_columns = {col["name"] for col in inspector.get_columns("user_asset_categories")}
    category_indexes = {index["name"] for index in inspector.get_indexes("user_asset_categories")}
    category_unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("user_asset_categories")
        if constraint.get("name")
    }

    asset_columns = {col["name"] for col in inspector.get_columns("user_assets")}
    asset_indexes = {index["name"] for index in inspector.get_indexes("user_assets")}

    with engine.begin() as conn:
        if "name" not in category_columns:
            conn.execute(text("ALTER TABLE user_asset_categories ADD COLUMN name VARCHAR(100) NOT NULL DEFAULT ''"))
        if "sort_order" not in category_columns:
            conn.execute(text("ALTER TABLE user_asset_categories ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"))
        if "created_at" not in category_columns:
            conn.execute(text("ALTER TABLE user_asset_categories ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "updated_at" not in category_columns:
            conn.execute(text("ALTER TABLE user_asset_categories ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))

        if "file_name" not in asset_columns:
            conn.execute(text("ALTER TABLE user_assets ADD COLUMN file_name VARCHAR(255) NOT NULL DEFAULT ''"))
        if "object_key" not in asset_columns:
            conn.execute(text("ALTER TABLE user_assets ADD COLUMN object_key VARCHAR(500) NOT NULL DEFAULT ''"))
        if "url" not in asset_columns:
            conn.execute(text("ALTER TABLE user_assets ADD COLUMN url VARCHAR(1000) NOT NULL DEFAULT ''"))
        if "thumbnail_url" not in asset_columns:
            conn.execute(text("ALTER TABLE user_assets ADD COLUMN thumbnail_url VARCHAR(1000) NOT NULL DEFAULT ''"))
        if "mime_type" not in asset_columns:
            conn.execute(text("ALTER TABLE user_assets ADD COLUMN mime_type VARCHAR(100) NOT NULL DEFAULT ''"))
        if "file_size" not in asset_columns:
            conn.execute(text("ALTER TABLE user_assets ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0"))
        if "width" not in asset_columns:
            conn.execute(text("ALTER TABLE user_assets ADD COLUMN width INTEGER NULL"))
        if "height" not in asset_columns:
            conn.execute(text("ALTER TABLE user_assets ADD COLUMN height INTEGER NULL"))
        if "status" not in asset_columns:
            conn.execute(text("ALTER TABLE user_assets ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'pending'"))
        if "is_deleted" not in asset_columns:
            conn.execute(text("ALTER TABLE user_assets ADD COLUMN is_deleted BOOLEAN DEFAULT 0"))
        if "deleted_at" not in asset_columns:
            conn.execute(text("ALTER TABLE user_assets ADD COLUMN deleted_at DATETIME"))
        if "completed_at" not in asset_columns:
            conn.execute(text("ALTER TABLE user_assets ADD COLUMN completed_at DATETIME"))
        if "created_at" not in asset_columns:
            conn.execute(text("ALTER TABLE user_assets ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "updated_at" not in asset_columns:
            conn.execute(text("ALTER TABLE user_assets ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))

        conn.execute(text("UPDATE user_assets SET file_name = '' WHERE file_name IS NULL"))
        conn.execute(text("UPDATE user_assets SET object_key = '' WHERE object_key IS NULL"))
        conn.execute(text("UPDATE user_assets SET url = '' WHERE url IS NULL"))
        conn.execute(text("UPDATE user_assets SET thumbnail_url = '' WHERE thumbnail_url IS NULL"))
        conn.execute(text("UPDATE user_assets SET mime_type = '' WHERE mime_type IS NULL"))
        conn.execute(text("UPDATE user_assets SET file_size = 0 WHERE file_size IS NULL"))
        conn.execute(text("UPDATE user_assets SET status = 'pending' WHERE status IS NULL OR status = ''"))
        conn.execute(text("UPDATE user_assets SET is_deleted = 0 WHERE is_deleted IS NULL"))

    refreshed_inspector = inspect(engine)
    refreshed_category_indexes = {index["name"] for index in refreshed_inspector.get_indexes("user_asset_categories")}
    refreshed_category_unique_constraints = {
        constraint["name"]
        for constraint in refreshed_inspector.get_unique_constraints("user_asset_categories")
        if constraint.get("name")
    }
    refreshed_asset_indexes = {index["name"] for index in refreshed_inspector.get_indexes("user_assets")}

    with engine.begin() as conn:
        if "idx_user_asset_categories_user_sort_order" not in refreshed_category_indexes:
            conn.execute(text("CREATE INDEX idx_user_asset_categories_user_sort_order ON user_asset_categories (user_id, sort_order, updated_at)"))
        if "uq_user_asset_categories_user_name" not in refreshed_category_unique_constraints:
            conn.execute(text("CREATE UNIQUE INDEX uq_user_asset_categories_user_name ON user_asset_categories (user_id, name)"))
        if "idx_user_assets_user_created" not in refreshed_asset_indexes:
            conn.execute(text("CREATE INDEX idx_user_assets_user_created ON user_assets (user_id, created_at)"))
        if "idx_user_assets_category_id" not in refreshed_asset_indexes:
            conn.execute(text("CREATE INDEX idx_user_assets_category_id ON user_assets (category_id)"))
        if "idx_user_assets_user_deleted_status" not in refreshed_asset_indexes:
            conn.execute(text("CREATE INDEX idx_user_assets_user_deleted_status ON user_assets (user_id, is_deleted, status, completed_at)"))


def _ensure_user_board_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        return
    if "user_boards" not in table_names:
        from app.models.user_board import UserBoard

        UserBoard.__table__.create(bind=engine)
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())

    board_columns = {col["name"] for col in inspector.get_columns("user_boards")}
    board_indexes = {index["name"] for index in inspector.get_indexes("user_boards")}
    with engine.begin() as conn:
        if "name" not in board_columns:
            conn.execute(text("ALTER TABLE user_boards ADD COLUMN name VARCHAR(100) NOT NULL DEFAULT ''"))
        if "created_at" not in board_columns:
            conn.execute(text("ALTER TABLE user_boards ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "updated_at" not in board_columns:
            conn.execute(text("ALTER TABLE user_boards ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "idx_user_boards_user_updated_at" not in board_indexes:
            conn.execute(text("CREATE INDEX idx_user_boards_user_updated_at ON user_boards (user_id, updated_at)"))

    if "tasks" not in table_names:
        return
    task_columns = {col["name"] for col in inspect(engine).get_columns("tasks")}
    task_indexes = {index["name"] for index in inspect(engine).get_indexes("tasks")}
    with engine.begin() as conn:
        if "board_id" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN board_id INTEGER NULL"))
        if "idx_tasks_board_id" not in task_indexes:
            conn.execute(text("CREATE INDEX idx_tasks_board_id ON tasks (board_id)"))
        if "idx_tasks_user_board_deleted_created" not in task_indexes:
            conn.execute(text("CREATE INDEX idx_tasks_user_board_deleted_created ON tasks (user_id, board_id, is_deleted, created_at)"))


def _ensure_user_canvas_schema():
    from app.models.user_canvas import generate_canvas_project_id

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        return
    if "user_canvas" not in table_names:
        from app.models.user_canvas import UserCanvas

        UserCanvas.__table__.create(bind=engine)
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())

    canvas_columns = {col["name"] for col in inspector.get_columns("user_canvas")}
    canvas_index_defs = inspector.get_indexes("user_canvas")
    canvas_indexes = {index["name"] for index in canvas_index_defs}
    has_canvas_project_id_index = any(index.get("column_names") == ["project_id"] for index in canvas_index_defs)
    with engine.begin() as conn:
        if "project_id" not in canvas_columns:
            conn.execute(text("ALTER TABLE user_canvas ADD COLUMN project_id VARCHAR(16) NULL"))
        if "source_example_id" not in canvas_columns:
            conn.execute(text("ALTER TABLE user_canvas ADD COLUMN source_example_id INTEGER NULL"))
        if "name" not in canvas_columns:
            conn.execute(text("ALTER TABLE user_canvas ADD COLUMN name VARCHAR(100) NOT NULL DEFAULT ''"))
        if "viewport_x" not in canvas_columns:
            conn.execute(text("ALTER TABLE user_canvas ADD COLUMN viewport_x DOUBLE NOT NULL DEFAULT 0"))
        if "viewport_y" not in canvas_columns:
            conn.execute(text("ALTER TABLE user_canvas ADD COLUMN viewport_y DOUBLE NOT NULL DEFAULT 0"))
        if "zoom" not in canvas_columns:
            conn.execute(text("ALTER TABLE user_canvas ADD COLUMN zoom DOUBLE NOT NULL DEFAULT 0.5"))
        if "is_deleted" not in canvas_columns:
            conn.execute(text("ALTER TABLE user_canvas ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0"))
        if "deleted_at" not in canvas_columns:
            conn.execute(text("ALTER TABLE user_canvas ADD COLUMN deleted_at DATETIME NULL"))
        if "created_at" not in canvas_columns:
            conn.execute(text("ALTER TABLE user_canvas ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "updated_at" not in canvas_columns:
            conn.execute(text("ALTER TABLE user_canvas ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        existing_project_ids = {
            str(row[0])
            for row in conn.execute(text("SELECT project_id FROM user_canvas WHERE project_id IS NOT NULL AND project_id != ''")).fetchall()
        }
        rows_missing_project_id = conn.execute(text("SELECT id FROM user_canvas WHERE project_id IS NULL OR project_id = ''")).fetchall()
        for row in rows_missing_project_id:
            project_id = generate_canvas_project_id()
            while project_id in existing_project_ids:
                project_id = generate_canvas_project_id()
            existing_project_ids.add(project_id)
            conn.execute(text("UPDATE user_canvas SET project_id = :project_id WHERE id = :id"), {"project_id": project_id, "id": row[0]})
        if not has_canvas_project_id_index and "idx_user_canvas_project_id" not in canvas_indexes:
            conn.execute(text("CREATE UNIQUE INDEX idx_user_canvas_project_id ON user_canvas (project_id)"))
        if "idx_user_canvas_user_updated_at" not in canvas_indexes:
            conn.execute(text("CREATE INDEX idx_user_canvas_user_updated_at ON user_canvas (user_id, updated_at)"))
        if "idx_user_canvas_user_deleted_updated" not in canvas_indexes:
            conn.execute(text("CREATE INDEX idx_user_canvas_user_deleted_updated ON user_canvas (user_id, is_deleted, updated_at)"))
        if "idx_user_canvas_source_example_id" not in canvas_indexes:
            conn.execute(text("CREATE INDEX idx_user_canvas_source_example_id ON user_canvas (source_example_id)"))

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "tasks" in table_names:
        task_columns = {col["name"] for col in inspector.get_columns("tasks")}
        task_indexes = {index["name"] for index in inspector.get_indexes("tasks")}
        with engine.begin() as conn:
            if "canvas_id" not in task_columns:
                conn.execute(text("ALTER TABLE tasks ADD COLUMN canvas_id INTEGER NULL"))
            if "is_example_template_seed" not in task_columns:
                conn.execute(text("ALTER TABLE tasks ADD COLUMN is_example_template_seed BOOLEAN NOT NULL DEFAULT 0"))
            conn.execute(text(
                "UPDATE tasks t "
                "JOIN user_canvas c ON c.id = t.canvas_id "
                "SET t.is_example_template_seed = 1 "
                "WHERE c.source_example_id IS NOT NULL "
                "AND COALESCE(t.credit_cost, 0) = 0 "
                "AND COALESCE(t.provider_task_id, '') = '' "
                "AND t.enqueued_at IS NULL "
                "AND t.request_started_at IS NULL "
                "AND t.request_finished_at IS NULL"
            ))
            if "idx_tasks_canvas_id" not in task_indexes:
                conn.execute(text("CREATE INDEX idx_tasks_canvas_id ON tasks (canvas_id)"))
            if "idx_tasks_user_canvas_deleted_created" not in task_indexes:
                conn.execute(text("CREATE INDEX idx_tasks_user_canvas_deleted_created ON tasks (user_id, canvas_id, is_deleted, created_at)"))

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "canvas_groups" not in table_names:
        from app.models.canvas_group import CanvasGroup

        CanvasGroup.__table__.create(bind=engine)
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())

    group_columns = {col["name"] for col in inspector.get_columns("canvas_groups")}
    group_indexes = {index["name"] for index in inspector.get_indexes("canvas_groups")}
    with engine.begin() as conn:
        if "canvas_id" not in group_columns:
            conn.execute(text("ALTER TABLE canvas_groups ADD COLUMN canvas_id INTEGER NOT NULL"))
        if "name" not in group_columns:
            conn.execute(text("ALTER TABLE canvas_groups ADD COLUMN name VARCHAR(100) NOT NULL DEFAULT ''"))
        if "color" not in group_columns:
            conn.execute(text("ALTER TABLE canvas_groups ADD COLUMN color VARCHAR(32) NOT NULL DEFAULT '#ffab27'"))
        if "x" not in group_columns:
            conn.execute(text("ALTER TABLE canvas_groups ADD COLUMN x DOUBLE NOT NULL DEFAULT 0"))
        if "y" not in group_columns:
            conn.execute(text("ALTER TABLE canvas_groups ADD COLUMN y DOUBLE NOT NULL DEFAULT 0"))
        if "width" not in group_columns:
            conn.execute(text("ALTER TABLE canvas_groups ADD COLUMN width DOUBLE NOT NULL DEFAULT 320"))
        if "height" not in group_columns:
            conn.execute(text("ALTER TABLE canvas_groups ADD COLUMN height DOUBLE NOT NULL DEFAULT 220"))
        if "z_index" not in group_columns:
            conn.execute(text("ALTER TABLE canvas_groups ADD COLUMN z_index INTEGER NOT NULL DEFAULT 1"))
        if "created_at" not in group_columns:
            conn.execute(text("ALTER TABLE canvas_groups ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "updated_at" not in group_columns:
            conn.execute(text("ALTER TABLE canvas_groups ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "idx_canvas_groups_canvas_id" not in group_indexes:
            conn.execute(text("CREATE INDEX idx_canvas_groups_canvas_id ON canvas_groups (canvas_id)"))
        if "idx_canvas_groups_canvas_z" not in group_indexes:
            conn.execute(text("CREATE INDEX idx_canvas_groups_canvas_z ON canvas_groups (canvas_id, z_index)"))

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "canvas_nodes" not in table_names:
        from app.models.canvas_node import CanvasNode

        CanvasNode.__table__.create(bind=engine)
        inspector = inspect(engine)

    node_columns = {col["name"] for col in inspector.get_columns("canvas_nodes")}
    node_indexes = {index["name"] for index in inspector.get_indexes("canvas_nodes")}
    with engine.begin() as conn:
        if "canvas_id" not in node_columns:
            conn.execute(text("ALTER TABLE canvas_nodes ADD COLUMN canvas_id INTEGER NOT NULL"))
        if "group_id" not in node_columns:
            conn.execute(text("ALTER TABLE canvas_nodes ADD COLUMN group_id INTEGER NULL"))
        if "task_id" not in node_columns:
            conn.execute(text("ALTER TABLE canvas_nodes ADD COLUMN task_id INTEGER NULL"))
        else:
            try:
                conn.execute(text("ALTER TABLE canvas_nodes MODIFY task_id INTEGER NULL"))
            except Exception:
                pass
        if "video_task_id" not in node_columns:
            conn.execute(text("ALTER TABLE canvas_nodes ADD COLUMN video_task_id INTEGER NULL"))
        if "node_type" not in node_columns:
            conn.execute(text("ALTER TABLE canvas_nodes ADD COLUMN node_type VARCHAR(20) NOT NULL DEFAULT 'task'"))
        if "content" not in node_columns:
            conn.execute(text("ALTER TABLE canvas_nodes ADD COLUMN content VARCHAR(5000) NOT NULL DEFAULT ''"))
        if "image_url" not in node_columns:
            conn.execute(text("ALTER TABLE canvas_nodes ADD COLUMN image_url VARCHAR(1000) NOT NULL DEFAULT ''"))
        if "x" not in node_columns:
            conn.execute(text("ALTER TABLE canvas_nodes ADD COLUMN x DOUBLE NOT NULL DEFAULT 0"))
        if "y" not in node_columns:
            conn.execute(text("ALTER TABLE canvas_nodes ADD COLUMN y DOUBLE NOT NULL DEFAULT 0"))
        if "width" not in node_columns:
            conn.execute(text("ALTER TABLE canvas_nodes ADD COLUMN width DOUBLE NOT NULL DEFAULT 320"))
        if "height" not in node_columns:
            conn.execute(text("ALTER TABLE canvas_nodes ADD COLUMN height DOUBLE NOT NULL DEFAULT 420"))
        if "z_index" not in node_columns:
            conn.execute(text("ALTER TABLE canvas_nodes ADD COLUMN z_index INTEGER NOT NULL DEFAULT 1"))
        if "created_at" not in node_columns:
            conn.execute(text("ALTER TABLE canvas_nodes ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "updated_at" not in node_columns:
            conn.execute(text("ALTER TABLE canvas_nodes ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "idx_canvas_nodes_canvas_z" not in node_indexes:
            conn.execute(text("CREATE INDEX idx_canvas_nodes_canvas_z ON canvas_nodes (canvas_id, z_index)"))
        if "idx_canvas_nodes_group_id" not in node_indexes:
            conn.execute(text("CREATE INDEX idx_canvas_nodes_group_id ON canvas_nodes (group_id)"))
        if "idx_canvas_nodes_task_id" not in node_indexes:
            conn.execute(text("CREATE INDEX idx_canvas_nodes_task_id ON canvas_nodes (task_id)"))
        if "idx_canvas_nodes_video_task_id" not in node_indexes:
            conn.execute(text("CREATE INDEX idx_canvas_nodes_video_task_id ON canvas_nodes (video_task_id)"))

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "canvas_edges" not in table_names:
        from app.models.canvas_edge import CanvasEdge

        CanvasEdge.__table__.create(bind=engine)
        return

    edge_columns = {col["name"] for col in inspector.get_columns("canvas_edges")}
    edge_indexes = {index["name"] for index in inspector.get_indexes("canvas_edges")}
    with engine.begin() as conn:
        if "canvas_id" not in edge_columns:
            conn.execute(text("ALTER TABLE canvas_edges ADD COLUMN canvas_id INTEGER NOT NULL"))
        if "source_node_id" not in edge_columns:
            conn.execute(text("ALTER TABLE canvas_edges ADD COLUMN source_node_id INTEGER NOT NULL"))
        if "target_node_id" not in edge_columns:
            conn.execute(text("ALTER TABLE canvas_edges ADD COLUMN target_node_id INTEGER NOT NULL"))
        if "edge_type" not in edge_columns:
            conn.execute(text("ALTER TABLE canvas_edges ADD COLUMN edge_type VARCHAR(20) NOT NULL DEFAULT 'reference'"))
        if "source_anchor" not in edge_columns:
            conn.execute(text("ALTER TABLE canvas_edges ADD COLUMN source_anchor VARCHAR(10) NOT NULL DEFAULT 'auto'"))
        if "target_anchor" not in edge_columns:
            conn.execute(text("ALTER TABLE canvas_edges ADD COLUMN target_anchor VARCHAR(10) NOT NULL DEFAULT 'auto'"))
        if "is_collapsed" not in edge_columns:
            conn.execute(text("ALTER TABLE canvas_edges ADD COLUMN is_collapsed BOOLEAN NOT NULL DEFAULT 0"))
        if "created_at" not in edge_columns:
            conn.execute(text("ALTER TABLE canvas_edges ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "updated_at" not in edge_columns:
            conn.execute(text("ALTER TABLE canvas_edges ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "idx_canvas_edges_canvas_id" not in edge_indexes:
            conn.execute(text("CREATE INDEX idx_canvas_edges_canvas_id ON canvas_edges (canvas_id)"))
        if "idx_canvas_edges_source_node_id" not in edge_indexes:
            conn.execute(text("CREATE INDEX idx_canvas_edges_source_node_id ON canvas_edges (source_node_id)"))
        if "idx_canvas_edges_target_node_id" not in edge_indexes:
            conn.execute(text("CREATE INDEX idx_canvas_edges_target_node_id ON canvas_edges (target_node_id)"))


def _ensure_api_alert_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "tasks" not in table_names:
        return

    if "api_alert_runs" not in inspector.get_table_names():
        from app.models.api_alert_run import ApiAlertRun

        ApiAlertRun.__table__.create(bind=engine)


def _ensure_daily_report_schema():
    inspector = inspect(engine)
    if "daily_report_runs" not in inspector.get_table_names():
        from app.models.daily_report_run import DailyReportRun

        DailyReportRun.__table__.create(bind=engine)


def _ensure_example_canvas_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names or "user_canvas" not in table_names:
        return
    if "example_canvas_projects" not in table_names:
        from app.models.example_canvas_project import ExampleCanvasProject

        ExampleCanvasProject.__table__.create(bind=engine)
        inspector = inspect(engine)

    example_columns = {col["name"] for col in inspector.get_columns("example_canvas_projects")}
    example_index_defs = inspector.get_indexes("example_canvas_projects")
    example_indexes = {index["name"] for index in example_index_defs}
    has_source_canvas_unique = any(index.get("unique") and (index.get("column_names") or []) == ["source_canvas_id"] for index in example_index_defs)
    has_source_project_unique = any(index.get("unique") and (index.get("column_names") or []) == ["source_project_id"] for index in example_index_defs)
    with engine.begin() as conn:
        if "source_canvas_id" not in example_columns:
            conn.execute(text("ALTER TABLE example_canvas_projects ADD COLUMN source_canvas_id INTEGER NOT NULL"))
        if "source_project_id" not in example_columns:
            conn.execute(text("ALTER TABLE example_canvas_projects ADD COLUMN source_project_id VARCHAR(16) NOT NULL DEFAULT ''"))
        if "title" not in example_columns:
            conn.execute(text("ALTER TABLE example_canvas_projects ADD COLUMN title VARCHAR(100) NOT NULL DEFAULT ''"))
        if "subtitle" not in example_columns:
            conn.execute(text("ALTER TABLE example_canvas_projects ADD COLUMN subtitle VARCHAR(255) NOT NULL DEFAULT ''"))
        if "cover_url" not in example_columns:
            conn.execute(text("ALTER TABLE example_canvas_projects ADD COLUMN cover_url VARCHAR(1000) NOT NULL DEFAULT ''"))
        if "status" not in example_columns:
            conn.execute(text("ALTER TABLE example_canvas_projects ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'draft'"))
        if "sort_order" not in example_columns:
            conn.execute(text("ALTER TABLE example_canvas_projects ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"))
        if "preview_urls_json" not in example_columns:
            conn.execute(text("ALTER TABLE example_canvas_projects ADD COLUMN preview_urls_json TEXT"))
        if "snapshot_json" not in example_columns:
            conn.execute(text("ALTER TABLE example_canvas_projects ADD COLUMN snapshot_json TEXT"))
        if "created_by" not in example_columns:
            conn.execute(text("ALTER TABLE example_canvas_projects ADD COLUMN created_by INTEGER NULL"))
        if "updated_by" not in example_columns:
            conn.execute(text("ALTER TABLE example_canvas_projects ADD COLUMN updated_by INTEGER NULL"))
        if "created_at" not in example_columns:
            conn.execute(text("ALTER TABLE example_canvas_projects ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "updated_at" not in example_columns:
            conn.execute(text("ALTER TABLE example_canvas_projects ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        conn.execute(text("UPDATE example_canvas_projects SET status = 'draft' WHERE status IS NULL OR status = ''"))
        conn.execute(text("UPDATE example_canvas_projects SET preview_urls_json = '[]' WHERE preview_urls_json IS NULL OR preview_urls_json = ''"))
        conn.execute(text("UPDATE example_canvas_projects SET snapshot_json = '{}' WHERE snapshot_json IS NULL OR snapshot_json = ''"))
        if not has_source_canvas_unique and "uq_example_canvas_projects_source_canvas_id" not in example_indexes:
            conn.execute(text("CREATE UNIQUE INDEX uq_example_canvas_projects_source_canvas_id ON example_canvas_projects (source_canvas_id)"))
        if not has_source_project_unique and "uq_example_canvas_projects_source_project_id" not in example_indexes:
            conn.execute(text("CREATE UNIQUE INDEX uq_example_canvas_projects_source_project_id ON example_canvas_projects (source_project_id)"))
        if "idx_example_canvas_projects_status_sort" not in example_indexes:
            conn.execute(text("CREATE INDEX idx_example_canvas_projects_status_sort ON example_canvas_projects (status, sort_order, id)"))
        if "idx_example_canvas_projects_created_by" not in example_indexes:
            conn.execute(text("CREATE INDEX idx_example_canvas_projects_created_by ON example_canvas_projects (created_by)"))
        if "idx_example_canvas_projects_updated_by" not in example_indexes:
            conn.execute(text("CREATE INDEX idx_example_canvas_projects_updated_by ON example_canvas_projects (updated_by)"))


def _backfill_task_credit_costs():
    from app.database import SessionLocal
    from app.models.task import Task
    from app.models.credit_log import CreditLog

    # Backfill queries the ORM Task model directly, so ensure async-provider
    # columns exist first on older databases before issuing SELECT tasks.*.
    _ensure_task_credit_cost_column()

    db = SessionLocal()
    try:
        tasks = db.query(Task).order_by(Task.id.asc()).all()
        if not tasks:
            return

        task_log_costs = {
            task_id: cost
            for task_id, cost in (
                db.query(CreditLog.task_id, func.coalesce(func.sum(-CreditLog.amount), 0))
                .filter(CreditLog.type == "consume", CreditLog.task_id.is_not(None))
                .group_by(CreditLog.task_id)
                .all()
            )
        }

        changed = False
        for task in tasks:
            if (task.credit_cost or 0) > 0:
                continue

            logged_cost = int(task_log_costs.get(task.id) or 0)
            if logged_cost <= 0:
                continue

            if int(task.credit_cost or 0) != logged_cost:
                task.credit_cost = logged_cost
                changed = True

        if changed:
            db.commit()
    finally:
        db.close()


def _initialize_template_sort_orders():
    from app.database import SessionLocal
    from app.models.template import Template

    _ensure_template_required_columns()

    db = SessionLocal()
    try:
        templates = (
            db.query(Template)
            .order_by(Template.created_at.asc(), Template.id.asc())
            .all()
        )
        if not templates:
            return

        has_initialized_sort = any((template.sort_order or 0) > 0 for template in templates)
        if has_initialized_sort:
            return

        for index, template in enumerate(templates, start=1):
            template.sort_order = index

        db.commit()
    finally:
        db.close()


def _seed_default_data():
    """Create default superadmin/admin users and seed runtime configs."""
    from app.database import SessionLocal
    from app.services.user_credit_service import create_default_credit_account
    from app.services.external_api_config_service import seed_legacy_configs
    from app.models.user import User
    from app.utils.security import hash_password

    db = SessionLocal()
    try:
        if not db.query(User).filter(User.role == "superadmin").first():
            user = User(
                username="administrator",
                password_hash=hash_password("administrator123"),
                role="superadmin",
            )
            db.add(user)
            db.flush()
            create_default_credit_account(db, user)
            db.commit()

        if not db.query(User).filter(User.role.in_(["admin", "user"])).first():
            user = User(username="admin", password_hash=hash_password("admin123"), role="admin")
            db.add(user)
            db.flush()
            create_default_credit_account(db, user)
            db.commit()

        seed_legacy_configs(
            db,
            ai_api_url=settings.AI_API_URL,
            prompt_reverse_url="https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        )
    finally:
        db.close()


upload_path = Path(settings.UPLOAD_DIR)
upload_path.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(upload_path)), name="uploads")

from app.api import auth, boards, canvases, tasks, video_tasks, images, history, admin, upload, api_key, templates, prompt_reverse, prompt_optimize, prompt_optimize_styles, generation_scene_categories, external_api_config, video_external_api_config, chat_external_api_config, chat, feedback, system_messages, user_api_keys, payment, example_canvases, user_assets, user_prompts, update_logs  # noqa: E402
app.include_router(auth.router)
app.include_router(user_api_keys.router)
app.include_router(templates.router)
app.include_router(boards.router)
app.include_router(user_assets.category_router)
app.include_router(user_assets.router)
app.include_router(user_prompts.category_router)
app.include_router(user_prompts.router)
app.include_router(example_canvases.router)
app.include_router(canvases.router)
app.include_router(tasks.router)
app.include_router(video_tasks.router)
app.include_router(images.router)
app.include_router(history.router)
app.include_router(payment.router)
app.include_router(feedback.router)
app.include_router(system_messages.router)
app.include_router(system_messages.admin_router)
app.include_router(update_logs.router)
app.include_router(update_logs.admin_router)
app.include_router(admin.router)
app.include_router(example_canvases.admin_router)
app.include_router(upload.router)
app.include_router(api_key.router)
app.include_router(api_key.cos_router)
app.include_router(api_key.secret_router)
app.include_router(api_key.public_router)
app.include_router(prompt_reverse.router)
app.include_router(prompt_optimize.router)
app.include_router(prompt_optimize_styles.admin_router)
app.include_router(prompt_optimize_styles.public_router)
app.include_router(generation_scene_categories.admin_router)
app.include_router(external_api_config.router)
app.include_router(external_api_config.scene_router)
app.include_router(external_api_config.public_router)
app.include_router(video_external_api_config.router)
app.include_router(video_external_api_config.scene_router)
app.include_router(video_external_api_config.public_router)
app.include_router(chat_external_api_config.router)
app.include_router(chat_external_api_config.scene_router)
app.include_router(chat_external_api_config.public_router)
app.include_router(chat.router)
