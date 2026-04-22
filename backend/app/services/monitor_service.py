import uuid
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitor import CheckRun, CheckRunStatus, Monitor, MonitorStatus


class MonitorValidationError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def validate_monitor_timing(interval_seconds: int, timeout_seconds: int) -> None:
    if timeout_seconds > interval_seconds:
        raise MonitorValidationError("timeout_seconds must be <= interval_seconds")


def validate_monitor_url_host(url: str) -> None:
    host = url.split("://", 1)[-1].split("/", 1)[0].split("@")[-1].split(":")[0].strip().lower()
    if not host:
        raise MonitorValidationError("invalid monitor url host")
    if host in {"localhost"} or host.endswith(".local"):
        raise MonitorValidationError("local/internal hosts are not allowed")
    try:
        ip = ip_address(host)
    except ValueError:
        return
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        raise MonitorValidationError("private/internal IP targets are not allowed")


def enforce_run_check_rate_limit(
    monitor: Monitor,
    min_interval_seconds: int,
    now: datetime | None = None,
) -> None:
    now_utc = now or datetime.now(UTC)
    if monitor.current_status == MonitorStatus.CHECKING:
        raise MonitorValidationError("monitor is already checking")
    if monitor.last_checked_at is None:
        return
    next_allowed_at = monitor.last_checked_at + timedelta(seconds=min_interval_seconds)
    if now_utc < next_allowed_at:
        wait_seconds = int((next_allowed_at - now_utc).total_seconds()) + 1
        raise MonitorValidationError(f"run-check throttled; retry after {max(wait_seconds, 1)}s")


def build_monitor_filters(
    query: Select[tuple[Monitor]],
    user_id: uuid.UUID,
    status: MonitorStatus | None,
    search: str | None,
) -> Select[tuple[Monitor]]:
    query = query.where(Monitor.user_id == user_id, Monitor.deleted_at.is_(None))
    if status is not None:
        query = query.where(Monitor.current_status == status)
    if search:
        term = f"%{search.strip()}%"
        query = query.where(or_(Monitor.name.ilike(term), Monitor.url.ilike(term)))
    return query


async def get_monitor_by_id(
    session: AsyncSession,
    user_id: uuid.UUID,
    monitor_id: uuid.UUID,
) -> Monitor | None:
    query = (
        select(Monitor)
        .where(
            Monitor.id == monitor_id,
            Monitor.user_id == user_id,
            Monitor.deleted_at.is_(None),
        )
        .limit(1)
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def list_monitors(
    session: AsyncSession,
    user_id: uuid.UUID,
    status: MonitorStatus | None,
    search: str | None,
    page: int,
    page_size: int,
) -> tuple[list[Monitor], int]:
    base_query = build_monitor_filters(select(Monitor), user_id, status, search)
    total_query = build_monitor_filters(select(func.count(Monitor.id)), user_id, status, search)
    paged_query = (
        base_query.order_by(Monitor.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    rows = await session.execute(paged_query)
    total = await session.scalar(total_query)
    return list(rows.scalars().all()), int(total or 0)


def _is_check_failure(status: CheckRunStatus) -> bool:
    return status not in {CheckRunStatus.UP, CheckRunStatus.SLOW}


async def get_monitor_risk_fields(
    session: AsyncSession,
    monitor_ids: list[uuid.UUID],
    per_monitor_cap: int = 200,
) -> dict[uuid.UUID, tuple[datetime | None, int]]:
    if not monitor_ids:
        return {}
    recent_checks = await session.execute(
        select(CheckRun.monitor_id, CheckRun.status, CheckRun.finished_at)
        .where(CheckRun.monitor_id.in_(monitor_ids))
        .order_by(CheckRun.monitor_id.asc(), CheckRun.finished_at.desc())
    )
    grouped: dict[uuid.UUID, list[tuple[CheckRunStatus, datetime]]] = {mid: [] for mid in monitor_ids}
    for monitor_id, status, finished_at in recent_checks.all():
        bucket = grouped.setdefault(monitor_id, [])
        if len(bucket) >= per_monitor_cap:
            continue
        bucket.append((status, finished_at))

    result: dict[uuid.UUID, tuple[datetime | None, int]] = {}
    for monitor_id, entries in grouped.items():
        last_failure_at: datetime | None = None
        consecutive_failures = 0
        for idx, (status, finished_at) in enumerate(entries):
            if _is_check_failure(status):
                if last_failure_at is None:
                    last_failure_at = finished_at
                if idx == consecutive_failures:
                    consecutive_failures += 1
            elif idx == consecutive_failures:
                break
        result[monitor_id] = (last_failure_at, consecutive_failures)
    return result
