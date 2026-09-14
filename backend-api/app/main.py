import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, inspect, text
from app.database import engine, Base
from app.config import settings
from app.logging_utils import clear_request_context, set_request_context, setup_logging
from app.utils.business_id import generate_business_id
import app.models  # noqa: F401 — ensure all models are registered

setup_logging(level=settings.LOG_LEVEL, json_logs=settings.LOG_JSON)

access_logger = logging.getLogger("app.access")
error_logger = logging.getLogger("app.error")

app = FastAPI(title="Banana Web - AI 绘图系统", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    request.state.user_id = None
    set_request_context(request_id)
    start = time.perf_counter()
    response = None
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        status_code = response.status_code if response else 500
        user_id = getattr(request.state, "user_id", None)
        set_request_context(request_id, user_id)
        access_logger.info(
            "request completed",
            extra={
                "event": "http.request.completed",
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "client_ip": request.client.host if request.client else "",
                "user_agent": request.headers.get("user-agent", ""),
            },
        )
        clear_request_context()


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


def _run_startup_schema_sync():
    _ensure_user_credit_schema()
    _ensure_credit_redeem_key_schema()
    _ensure_user_api_key_schema()
    _drop_legacy_user_credits_column()
    _ensure_user_whitelist_column()
    _ensure_user_identity_schema()
    _ensure_business_id_schema()
    _ensure_prompt_history_columns()
    _ensure_image_required_columns()
    _ensure_task_credit_cost_column()
    _ensure_task_api_attempt_schema()
    _ensure_external_api_config_required_columns()
    _ensure_scene_binding_required_columns()
    _ensure_generation_scene_category_schema()
    _ensure_template_required_columns()
    _ensure_feedback_schema()
    _ensure_system_message_schema()
    _ensure_history_pin_schema()
    _ensure_user_board_schema()
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
        if "used_fallback_api" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN used_fallback_api BOOLEAN NOT NULL DEFAULT 0"))
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


def _ensure_generation_scene_category_schema():
    inspector = inspect(engine)
    if "generation_scene_categories" not in inspector.get_table_names():
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
        if "backup_api_config_id" not in scene_binding_columns:
            conn.execute(text("ALTER TABLE external_api_scene_bindings ADD COLUMN backup_api_config_id INTEGER"))
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


def _ensure_feedback_schema():
    inspector = inspect(engine)
    if "feedback" not in inspector.get_table_names():
        return

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
        if "created_at" not in feedback_columns:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        if "updated_at" not in feedback_columns:
            conn.execute(text("ALTER TABLE feedback ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))

        conn.execute(text("UPDATE feedback SET process_note = '' WHERE process_note IS NULL"))
        conn.execute(text("UPDATE feedback SET result_note = '' WHERE result_note IS NULL"))
        conn.execute(text("UPDATE feedback SET status = 'pending' WHERE status IS NULL OR status = ''"))
        conn.execute(text("UPDATE feedback SET is_read = 0 WHERE is_read IS NULL"))

        if "ix_feedback_user_id" not in feedback_indexes:
            conn.execute(text("CREATE INDEX ix_feedback_user_id ON feedback (user_id)"))
        if "ix_feedback_task_id" not in feedback_indexes:
            conn.execute(text("CREATE INDEX ix_feedback_task_id ON feedback (task_id)"))
        if "ix_feedback_status" not in feedback_indexes:
            conn.execute(text("CREATE INDEX ix_feedback_status ON feedback (status)"))
        if "ix_feedback_is_read" not in feedback_indexes:
            conn.execute(text("CREATE INDEX ix_feedback_is_read ON feedback (is_read)"))
        if "ix_feedback_handled_by" not in feedback_indexes:
            conn.execute(text("CREATE INDEX ix_feedback_handled_by ON feedback (handled_by)"))

    from app.database import SessionLocal
    from app.models.feedback import Feedback

    db = SessionLocal()
    try:
        changed = False
        rows = db.query(Feedback).filter((Feedback.business_id.is_(None)) | (Feedback.business_id == "")).all()
        for row in rows:
            row.business_id = generate_business_id()
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

from app.api import tasks, credits, config  # noqa: E402
app.include_router(tasks.router)
app.include_router(credits.router)
app.include_router(config.router)
