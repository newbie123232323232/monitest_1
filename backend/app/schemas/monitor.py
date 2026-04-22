import uuid
from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl

from app.models.monitor import (
    AlertChannel,
    AlertEventType,
    AlertSendStatus,
    CheckRunStatus,
    IncidentStatus,
    MonitorStatus,
    MonitorType,
)


class MonitorCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: HttpUrl
    monitor_type: MonitorType = MonitorType.HTTP
    interval_seconds: int = Field(default=60, ge=30, le=86400)
    timeout_seconds: int = Field(default=10, ge=1, le=120)
    max_retries: int = Field(default=2, ge=0, le=5)
    slow_threshold_ms: int = Field(default=1500, ge=100, le=60000)
    probe_region: str = Field(default="global", min_length=2, max_length=64)
    detect_content_change: bool = False


class MonitorUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    url: HttpUrl | None = None
    interval_seconds: int | None = Field(default=None, ge=30, le=86400)
    timeout_seconds: int | None = Field(default=None, ge=1, le=120)
    max_retries: int | None = Field(default=None, ge=0, le=5)
    slow_threshold_ms: int | None = Field(default=None, ge=100, le=60000)
    probe_region: str | None = Field(default=None, min_length=2, max_length=64)
    detect_content_change: bool | None = None
    is_paused: bool | None = None


class MonitorListItem(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    monitor_type: MonitorType
    current_status: MonitorStatus
    interval_seconds: int
    timeout_seconds: int
    probe_region: str
    is_paused: bool
    last_checked_at: datetime | None
    last_response_time_ms: int | None
    last_failure_at: datetime | None = None
    consecutive_failures: int = 0
    created_at: datetime


class MonitorDetailResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    url: str
    monitor_type: MonitorType
    interval_seconds: int
    timeout_seconds: int
    max_retries: int
    slow_threshold_ms: int
    probe_region: str
    detect_content_change: bool
    is_paused: bool
    current_status: MonitorStatus
    last_checked_at: datetime | None
    last_response_time_ms: int | None
    last_status_code: int | None
    last_error_message: str | None
    last_success_at: datetime | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class MonitorListResponse(BaseModel):
    items: list[MonitorListItem]
    total: int
    page: int
    page_size: int


class RunCheckResponse(BaseModel):
    monitor_id: uuid.UUID
    task_id: str
    status: str


class CheckRunItemResponse(BaseModel):
    id: uuid.UUID
    status: CheckRunStatus
    started_at: datetime
    finished_at: datetime
    response_time_ms: int | None
    status_code: int | None
    error_type: str | None
    error_message: str | None
    final_url: str | None
    content_type: str | None
    dns_resolve_ms: int | None
    tcp_connect_ms: int | None
    tls_handshake_ms: int | None
    ttfb_ms: int | None
    retry_count: int
    created_at: datetime


class IncidentItemResponse(BaseModel):
    id: uuid.UUID
    monitor_id: uuid.UUID
    opened_at: datetime
    closed_at: datetime | None
    status: IncidentStatus
    open_reason: str | None
    close_reason: str | None
    first_failed_check_id: uuid.UUID | None
    last_failed_check_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class AlertEventItemResponse(BaseModel):
    id: uuid.UUID
    incident_id: uuid.UUID | None
    monitor_id: uuid.UUID
    channel: AlertChannel
    event_type: AlertEventType
    sent_to: str | None
    sent_at: datetime | None
    send_status: AlertSendStatus
    error_message: str | None
    created_at: datetime


class DashboardSummaryResponse(BaseModel):
    total_monitors: int
    up: int
    down: int
    pending: int
    checking: int
    slow: int
    paused: int
    avg_response_time_ms: float | None
    uptime_window_from: datetime | None = None
    uptime_window_to: datetime | None = None
    uptime_total_checks: int | None = None
    uptime_success_checks: int | None = None
    average_uptime_percent: float | None = None


class MonitorUptimeResponse(BaseModel):
    window_from: datetime
    window_to: datetime
    total_checks: int
    success_checks: int
    uptime_percent: float | None
