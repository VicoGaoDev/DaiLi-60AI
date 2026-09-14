from pathlib import Path

from pydantic_settings import BaseSettings
from sqlalchemy.engine import URL

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False
    WEB_CONCURRENCY: int = 2
    ALLOW_SYNC_GENERATION_FALLBACK: bool = False
    SYNC_GENERATION_MAX_WORKERS: int = 2

    DATABASE_URL: str | None = None
    DB_HOST: str = "sh-cynosdbmysql-grp-kmfw4ojg.sql.tencentcdb.com"
    DB_PORT: int = 20396
    DB_USER: str | None = None
    DB_PASSWORD: str | None = None
    DB_NAME: str | None = None
    DB_CHARSET: str = "utf8mb4"
    DB_AUTO_CREATE_TABLES: bool = False
    DB_RUN_STARTUP_SCHEMA_SYNC: bool = False
    DB_RUN_SCHEMA_COMPAT: bool = False
    DB_RUN_SEED: bool = False
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    UPLOAD_DIR: str = str(BASE_DIR / "uploads")

    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_WORKER_CONCURRENCY: int = 2
    CELERY_PREFETCH_MULTIPLIER: int = 1
    MAX_ACTIVE_TASKS_PER_USER: int = 12
    MAX_ACTIVE_TASKS_GLOBAL: int = 500

    AI_API_URL: str = "https://nanoapi.poloai.top/v1beta/models/gemini-2.5-flash-image-preview:generateContent"
    AI_TIMEOUT: int = 600
    PROCESSING_TASK_TIMEOUT_SECONDS: int = 600
    COS_STS_DURATION_SECONDS: int = 1800
    IMAGE_FETCH_TIMEOUT: int = 30
    COS_IMAGE_THUMBNAIL_RULE: str = ""
    COS_IMAGE_STYLE_SEPARATOR: str = "!"
    USER_ASSET_PENDING_TTL_MINUTES: int = 10
    USER_ASSET_PENDING_CLEANUP_INTERVAL_MINUTES: int = 10
    USER_ASSET_PENDING_CLEANUP_BATCH_SIZE: int = 500
    GENERATED_PREVIEW_TTL_SECONDS: int = 3600
    GENERATED_IMAGE_CACHE_CONTROL: str = "public, max-age=31536000, immutable"
    CLOUDBASE_ENV_ID: str = ""
    CLOUDBASE_REGION: str = "ap-shanghai"
    CLOUDBASE_AUTH_TIMEOUT: int = 15
    WECOM_NOTIFY_ENABLED: bool = False
    WECOM_WEBHOOK_URL: str = ""
    WECOM_ALERT_WEBHOOK_URL: str = ""
    WECOM_NOTIFY_TIMEOUT_SECONDS: int = 10
    API_ALERT_ENABLED: bool = False
    API_ALERT_INTERVAL_MINUTES: int = 60
    API_ALERT_WINDOW_MINUTES: int = 60
    API_ALERT_MIN_CALL_COUNT: int = 10
    API_ALERT_OVERALL_MIN_CALL_COUNT: int = 10
    API_ALERT_SUCCESS_RATE_THRESHOLD: float = 80
    API_ALERT_AVG_DURATION_SECONDS: int = 150
    PROMO_REBATE_START_AT: str = "2026-08-19T00:00:00"
    ALIPAY_APP_ID: str = ""
    ALIPAY_PRIVATE_KEY: str = ""
    ALIPAY_PUBLIC_KEY: str = ""
    ALIPAY_GATEWAY: str = "https://openapi.alipay.com/gateway.do"
    ALIPAY_NOTIFY_URL: str = ""
    ALIPAY_RETURN_URL: str = ""
    ALIPAY_SIGN_TYPE: str = "RSA2"
    ALIPAY_TIMEOUT_EXPRESS: str = "15m"

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def database_url(self) -> str:
        database_url = (self.DATABASE_URL or "").strip()
        if database_url:
            if not database_url.startswith("mysql"):
                raise ValueError("DATABASE_URL must start with a MySQL driver prefix.")
            return database_url

        missing_fields = [
            field_name
            for field_name, field_value in {
                "DB_USER": self.DB_USER,
                "DB_PASSWORD": self.DB_PASSWORD,
                "DB_NAME": self.DB_NAME,
            }.items()
            if not (field_value or "").strip()
        ]
        if missing_fields:
            joined = ", ".join(missing_fields)
            raise ValueError(f"Set DATABASE_URL or provide MySQL fields: {joined}.")

        return URL.create(
            drivername="mysql+pymysql",
            username=self.DB_USER,
            password=self.DB_PASSWORD,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
            query={"charset": self.DB_CHARSET},
        ).render_as_string(hide_password=False)

    @property
    def should_run_schema_compat(self) -> bool:
        return self.DB_RUN_SCHEMA_COMPAT

    @property
    def should_run_startup_schema_sync(self) -> bool:
        return self.DB_RUN_STARTUP_SCHEMA_SYNC

    @property
    def should_run_seed(self) -> bool:
        return self.DB_RUN_SEED

    @property
    def allow_sync_generation_fallback(self) -> bool:
        return self.DEBUG or self.ALLOW_SYNC_GENERATION_FALLBACK


settings = Settings()
