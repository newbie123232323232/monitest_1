import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MonitorExpiryStatus(Base):
    __tablename__ = "monitor_expiry_status"

    monitor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("monitors.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ssl_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ssl_days_left: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ssl_state: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    ssl_alerted_thresholds: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    domain_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    domain_days_left: Mapped[int | None] = mapped_column(Integer, nullable=True)
    domain_state: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    domain_alerted_thresholds: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
