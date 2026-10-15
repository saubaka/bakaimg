"""Configuration profiles for the independent image-host project."""

from __future__ import annotations

from datetime import timedelta


class BaseConfig:
    APP_VERSION = "0.16.0"
    SYSTEM_NAME = "baka图床"
    SYSTEM_NAME_EN = "bakaimg"
    SITE_NAME = "baka图床"
    # 健康检查service标识为对外固定契约值，不随品牌名称变化。
    HEALTH_SERVICE_NAME = "Cloudnest"
    SITE_TAGLINE = "把照片放好，想看的时候就找得到"
    SITE_URL = "http://127.0.0.1:5200"
    ENV_NAME = "base"

    DEFAULT_SECRET_KEY = "development-only-change-me"
    SECRET_KEY = DEFAULT_SECRET_KEY

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"timeout": 5},
        "pool_pre_ping": True,
    }
    SQLITE_BUSY_TIMEOUT_MS = 5_000

    MAX_CONTENT_LENGTH = 64 * 1024 * 1024
    MAX_FORM_MEMORY_SIZE = 2 * 1024 * 1024
    MAX_FORM_PARTS = 200
    MAX_IMAGE_UPLOAD_BYTES = 20 * 1024 * 1024
    MAX_IMAGE_BATCH = 10
    MAX_IMAGE_PIXELS = 40_000_000
    MAX_IMAGE_DIMENSION = 12_000
    MAX_ANIMATION_FRAMES = 100
    THUMBNAIL_SIZE = 640
    DEFAULT_STORAGE_QUOTA_BYTES = 512 * 1024 * 1024
    DEFAULT_IMAGE_QUOTA_COUNT = 1_000
    TRASH_RETENTION_DAYS = 30
    MAX_API_TOKENS_PER_USER = 20
    API_TOKEN_MAX_AGE_DAYS = 365
    EXPECTED_MIGRATION = "f47a2c9d61e8"
    BACKUP_FORMAT_VERSION = 1
    BACKUP_MAX_MEMBERS = 100_000
    BACKUP_MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024 * 1024
    BACKUP_RETENTION_COUNT = 20
    TRUST_PROXY_HOPS = 0
    ALLOWED_HOST = None
    TRUSTED_HOSTS = None

    SESSION_COOKIE_NAME = "cloudnest_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_REFRESH_EACH_REQUEST = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    LOGIN_RATE_LIMIT = 5
    LOGIN_RATE_WINDOW_SECONDS = 15 * 60
    ACCOUNT_LOCK_SECONDS = 15 * 60
    SESSION_TOUCH_INTERVAL_SECONDS = 5 * 60

    WTF_CSRF_TIME_LIMIT = 2 * 60 * 60
    WTF_CSRF_SSL_STRICT = True
    SEND_FILE_MAX_AGE_DEFAULT = 3600


class DevelopmentConfig(BaseConfig):
    ENV_NAME = "development"
    DEBUG = True
    TEMPLATES_AUTO_RELOAD = True
    SEND_FILE_MAX_AGE_DEFAULT = 0


class TestingConfig(BaseConfig):
    ENV_NAME = "testing"
    TESTING = True
    SECRET_KEY = "testing-secret-key"
    WTF_CSRF_ENABLED = False
    SERVER_NAME = "localhost"


class ProductionConfig(BaseConfig):
    ENV_NAME = "production"
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"
    SEND_FILE_MAX_AGE_DEFAULT = 31_536_000


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
