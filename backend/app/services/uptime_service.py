import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitor import CheckRun, CheckRunStatus, Monitor


def successful_check_statuses() -> tuple[CheckRunStatus, ...]:
    return (CheckRunStatus.UP, CheckRunStatus.SLOW)


def is_successful_check(status: CheckRunStatus) -> bool:
    return status in successful_check_statuses()


def default_uptime_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    now_utc = now or datetime.now(UTC)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=UTC)
    end = now_utc
    start = end - timedelta(days=30)
    return start, end


def clamp_uptime_range(
    from_dt: datetime | None,
    to_dt: datetime | None,
    max_days: int = 366,
) -> tuple[datetime, datetime]:
    now_utc = datetime.now(UTC)
    if to_dt is None:
        to_dt = now_utc
    if from_dt is None:
        from_dt = to_dt - timedelta(days=30)
    if from_dt.tzinfo is None:
        from_dt = from_dt.replace(tzinfo=UTC)
    if to_dt.tzinfo is None:
        to_dt = to_dt.replace(tzinfo=UTC)
    if from_dt > to_dt:
        raise ValueError("from must be <= to")
    if (to_dt - from_dt).days > max_days:
        raise ValueError(f"range must be <= {max_days} days")
    return from_dt, to_dt


async def count_checks_for_uptime(
    session: AsyncSession,
    monitor_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
) -> tuple[int, int]:
    success_vals = [CheckRunStatus.UP, CheckRunStatus.SLOW]
    q = await session.execute(
        select(
            func.count(CheckRun.id),
            func.sum(case((CheckRun.status.in_(success_vals), 1), else_=0)),
        ).where(
            and_(
                CheckRun.monitor_id == monitor_id,
                CheckRun.finished_at >= from_dt,
                CheckRun.finished_at <= to_dt,
            )
        )
    )
    row = q.one()
    total = int(row[0] or 0)
    success = int(row[1] or 0)
    return total, success


async def uptime_stats_for_monitor(
    session: AsyncSession,
    user_id: uuid.UUID,
    monitor_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
) -> tuple[int, int, float | None]:
    m = await session.execute(
        select(Monitor.id).where(
            Monitor.id == monitor_id,
            Monitor.user_id == user_id,
            Monitor.deleted_at.is_(None),
        )
    )
    if m.scalar_one_or_none() is None:
        return 0, 0, None
    total, success = await count_checks_for_uptime(session, monitor_id, from_dt, to_dt)
    pct = (100.0 * success / total) if total > 0 else None
    return total, success, pct


async def aggregate_uptime_for_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
) -> tuple[int, int, float | None]:
    success_vals = [CheckRunStatus.UP, CheckRunStatus.SLOW]
    q = await session.execute(
        select(
            func.count(CheckRun.id),
            func.sum(case((CheckRun.status.in_(success_vals), 1), else_=0)),
        )
        .select_from(CheckRun)
        .join(Monitor, Monitor.id == CheckRun.monitor_id)
        .where(
            and_(
                Monitor.user_id == user_id,
                Monitor.deleted_at.is_(None),
                CheckRun.finished_at >= from_dt,
                CheckRun.finished_at <= to_dt,
            )
        )
    )
    row = q.one()
    total = int(row[0] or 0)
    success = int(row[1] or 0)
    pct = (100.0 * success / total) if total > 0 else None
    return total, success, pct
