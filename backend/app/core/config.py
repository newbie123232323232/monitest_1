from functools import lru_cache
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import AnyUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_base_url: AnyUrl
    api_public_url: AnyUrl

    database_url: str

    redis_url: str
    celery_broker_url: str
    celery_result_backend: str
    celery_broker_pool_limit: int = 2
    celery_broker_heartbeat_seconds: int = 30
    celery_broker_health_check_interval_seconds: int = 30
    celery_worker_prefetch_multiplier: int = 1
    celery_broker_retry_on_startup: bool = True

    jwt_secret: str
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 14

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""

    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = ""

    email_verify_token_expire_hours: int = 48
    run_check_min_interval_seconds: int = 15
    alert_cooldown_minutes: int = 10
    alert_still_down_reminder_minutes: int = 30
    alert_max_reminders_per_incident: int = 24
    runtime_beat_stale_seconds: int = 120
    auth_rate_limit_window_seconds: int = 60
    auth_rate_limit_max_attempts: int = 10
    enforce_https_redirect: bool = False
    expose_docs_in_production: bool = False
    allow_insecure_dev_mode_on_public: bool = False
    enforce_strong_jwt_secret_in_production: bool = True
    jwt_secret_min_length: int = 32

    @property
    def database_url_sync(self) -> str:
        """Alembic / sync tools: psycopg v3."""
        url = self.database_url
        if "+asyncpg" in url:
            return url.replace("postgresql+asyncpg", "postgresql+psycopg", 1)
        return url

    @property
    def cors_origins(self) -> list[str]:
        """SPA dev hay mở bằng localhost hoặc 127.0.0.1 — khác origin → CORS fail nếu chỉ whitelist một."""
        base = str(self.app_base_url).rstrip("/")
        origins: set[str] = {base}
        if self.app_env == "development":
            if "://localhost" in base:
                origins.add(base.replace("://localhost", "://127.0.0.1", 1))
            elif "://127.0.0.1" in base:
                origins.add(base.replace("://127.0.0.1", "://localhost", 1))
        return sorted(origins)

    @property
    def public_api_host(self) -> str:
        return urlsplit(str(self.api_public_url)).hostname or ""

    @property
    def is_public_api_host(self) -> bool:
        host = self.public_api_host.lower()
        if host in {"localhost", "127.0.0.1"}:
            return False
        try:
            ip = ip_address(host)
        except ValueError:
            return True
        return not (ip.is_loopback or ip.is_private or ip.is_link_local)

    def validate_jwt_secret_policy(self) -> None:
        secret = (self.jwt_secret or "").strip()
        if not secret:
            raise RuntimeError("JWT_SECRET must not be empty")

        reasons: list[str] = []
        if len(secret) < self.jwt_secret_min_length:
            reasons.append(f"too short (min {self.jwt_secret_min_length})")

        lowered = secret.lower()
        weak_tokens = ("changeme", "default", "secret", "jwt_secret", "password", "example")
        if any(token in lowered for token in weak_tokens):
            reasons.append("contains weak/common keyword")

        unique_chars = len(set(secret))
        if unique_chars < 12:
            reasons.append("low entropy (too few unique characters)")

        if self.app_env == "production" and self.enforce_strong_jwt_secret_in_production and reasons:
            raise RuntimeError("Weak JWT_SECRET in production: " + ", ".join(reasons))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
