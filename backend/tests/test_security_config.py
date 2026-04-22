import pytest

from app.core.config import Settings


def _base_kwargs() -> dict[str, object]:
    return {
        "app_base_url": "http://localhost:5173",
        "api_public_url": "http://127.0.0.1:8010",
        "database_url": "postgresql+asyncpg://u:p@localhost:5432/moni",
        "redis_url": "redis://localhost:6379/0",
        "celery_broker_url": "redis://localhost:6379/0",
        "celery_result_backend": "redis://localhost:6379/0",
    }


def test_validate_jwt_secret_policy_rejects_weak_secret_in_production() -> None:
    cfg = Settings(
        **_base_kwargs(),
        app_env="production",
        jwt_secret="jwt_secret_123",
    )
    with pytest.raises(RuntimeError, match="Weak JWT_SECRET"):
        cfg.validate_jwt_secret_policy()


def test_validate_jwt_secret_policy_allows_strong_secret_in_production() -> None:
    cfg = Settings(
        **_base_kwargs(),
        app_env="production",
        jwt_secret="x8N#Q2vP!mL5tR9zY4kD7wH1cF6uJ3sA",
    )
    cfg.validate_jwt_secret_policy()

