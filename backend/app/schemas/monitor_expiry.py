import uuid
from datetime import datetime

from pydantic import BaseModel


class MonitorExpiryStatusResponse(BaseModel):
    monitor_id: uuid.UUID
    ssl_expires_at: datetime | None
    ssl_days_left: int | None
    ssl_state: str
    domain_expires_at: datetime | None
    domain_days_left: int | None
    domain_state: str
    last_checked_at: datetime | None
    last_error: str | None
    updated_at: datetime


class ExpirySummaryResponse(BaseModel):
    total_with_ssl_data: int
    ok: int
    warn_30d: int
    warn_14d: int
    warn_7d: int
    warn_1d: int
    expired: int
    unknown: int
