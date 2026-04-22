import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [item.value for item in enum_cls]


class MonitorType(str, enum.Enum):
    HTTP = "http"
    TCP = "tcp"
    ICMP = "icmp"


class MonitorStatus(str, enum.Enum):
    PENDING = "pending"
    CHECKING = "checking"
    UP = "up"
    DOWN = "down"
    SLOW = "slow"
    PAUSED = "paused"


class CheckRunStatus(str, enum.Enum):
    UP = "up"
    DOWN = "down"
    SLOW = "slow"
    TIMEOUT = "timeout"
    DNS_ERROR = "dns_error"
    TLS_ERROR = "tls_error"
    HTTP_ERROR = "http_error"


class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"


class AlertChannel(str, enum.Enum):
    EMAIL = "email"


class AlertEventType(str, enum.Enum):
    INCIDENT_OPENED = "incident_opened"
    INCIDENT_RECOVERED = "incident_recovered"
    STILL_DOWN = "still_down"


class AlertSendStatus(str, enum.Enum):
    SENT = "sent"
    FAILED = "failed"


class Monitor(Base):
    __tablename__ = "monitors"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    monitor_type: Mapped[MonitorType] = mapped_column(
        Enum(MonitorType, name="monitor_type", values_callable=_enum_values),
        nullable=False,
        default=MonitorType.HTTP,
    )
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    slow_threshold_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=1500)
    probe_region: Mapped[str] = mapped_column(String(64), nullable=False, default="global")
    detect_content_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_status: Mapped[MonitorStatus] = mapped_column(
        Enum(MonitorStatus, name="monitor_status", values_callable=_enum_values),
        nullable=False,
        default=MonitorStatus.PENDING,
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="monitors")
    check_runs: Mapped[list["CheckRun"]] = relationship(
        "CheckRun", back_populates="monitor", cascade="all, delete-orphan"
    )
    incidents: Mapped[list["Incident"]] = relationship(
        "Incident", back_populates="monitor", cascade="all, delete-orphan"
    )
    alert_events: Mapped[list["AlertEvent"]] = relationship(
        "AlertEvent", back_populates="monitor", cascade="all, delete-orphan"
    )


class CheckRun(Base):
    __tablename__ = "check_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    monitor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[CheckRunStatus] = mapped_column(
        Enum(CheckRunStatus, name="check_run_status", values_callable=_enum_values), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dns_resolve_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tcp_connect_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tls_handshake_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ttfb_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    monitor: Mapped[Monitor] = relationship("Monitor", back_populates="check_runs")


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    monitor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incident_status", values_callable=_enum_values),
        nullable=False,
        default=IncidentStatus.OPEN,
    )
    open_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    close_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_failed_check_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("check_runs.id", ondelete="SET NULL"), nullable=True
    )
    last_failed_check_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("check_runs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    monitor: Mapped[Monitor] = relationship("Monitor", back_populates="incidents")
    first_failed_check: Mapped[CheckRun | None] = relationship(
        "CheckRun", foreign_keys=[first_failed_check_id]
    )
    last_failed_check: Mapped[CheckRun | None] = relationship(
        "CheckRun", foreign_keys=[last_failed_check_id]
    )
    alert_events: Mapped[list["AlertEvent"]] = relationship(
        "AlertEvent", back_populates="incident", cascade="all, delete-orphan"
    )


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    monitor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[AlertChannel] = mapped_column(
        Enum(AlertChannel, name="alert_channel", values_callable=_enum_values),
        nullable=False,
        default=AlertChannel.EMAIL,
    )
    event_type: Mapped[AlertEventType] = mapped_column(
        Enum(AlertEventType, name="alert_event_type", values_callable=_enum_values), nullable=False
    )
    sent_to: Mapped[str | None] = mapped_column(String(320), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    send_status: Mapped[AlertSendStatus] = mapped_column(
        Enum(AlertSendStatus, name="alert_send_status", values_callable=_enum_values),
        nullable=False,
        default=AlertSendStatus.SENT,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    incident: Mapped[Incident | None] = relationship("Incident", back_populates="alert_events")
    monitor: Mapped[Monitor] = relationship("Monitor", back_populates="alert_events")
