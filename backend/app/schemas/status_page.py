import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.monitor import MonitorStatus


class StatusPageCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9-]+$")
    is_public: bool = True
    maintenance_notes: str | None = Field(default=None, max_length=2000)
    monitor_ids: list[uuid.UUID] = Field(default_factory=list)


class StatusPageUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=3, max_length=80, pattern=r"^[a-z0-9-]+$")
    is_public: bool | None = None
    maintenance_notes: str | None = Field(default=None, max_length=2000)
    monitor_ids: list[uuid.UUID] | None = None


class StatusPageMonitorItem(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    current_status: MonitorStatus
    last_checked_at: datetime | None
    last_response_time_ms: int | None


class StatusPageIncidentItem(BaseModel):
    id: uuid.UUID
    monitor_id: uuid.UUID
    status: str
    opened_at: datetime
    closed_at: datetime | None
    open_reason: str | None
    close_reason: str | None


class StatusPageResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    slug: str
    is_public: bool
    maintenance_notes: str | None
    created_at: datetime
    updated_at: datetime
    monitors: list[StatusPageMonitorItem]


class PublicStatusPageResponse(BaseModel):
    name: str
    slug: str
    maintenance_notes: str | None
    monitors: list[StatusPageMonitorItem]
    incidents: list[StatusPageIncidentItem]
    generated_at: datetime
