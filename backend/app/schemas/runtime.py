from datetime import datetime

from pydantic import BaseModel, Field


class RuntimeHealthResponse(BaseModel):
    status: str = Field(description="ok | degraded")
    checked_at: datetime
    redis_ok: bool
    worker_ok: bool
    beat_ok: bool
    beat_last_seen_at: datetime | None
    beat_heartbeat_age_seconds: int | None
    degraded_reasons: list[str]


class RuntimeQueueProfileResponse(BaseModel):
    checked_at: datetime
    window_minutes: int
    active_monitors: int
    expected_checks_in_window: float
    checks_observed: int
    timeout_checks: int
    checks_with_retry: int
    timeout_ratio: float
    retry_ratio: float
    avg_response_time_ms: float | None
    avg_interval_seconds: float | None
    avg_timeout_seconds: float | None
    avg_max_retries: float | None
    recommendations: list[str]
