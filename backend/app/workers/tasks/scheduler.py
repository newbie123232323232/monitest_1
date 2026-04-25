from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.monitor import Monitor, MonitorStatus
from app.workers.celery_app import celery_app
from app.workers.tasks.checks import check_http_monitor


@celery_app.task(name="app.workers.tasks.scheduler.enqueue_due_monitor_checks")
def enqueue_due_monitor_checks() -> int:
    import asyncio

    return asyncio.run(_enqueue_due_monitor_checks_async())


async def _enqueue_due_monitor_checks_async() -> int:
    now = datetime.now(UTC)
    enqueued = 0
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(Monitor).where(
                Monitor.deleted_at.is_(None),
                Monitor.is_paused.is_(False),
                Monitor.current_status != MonitorStatus.CHECKING,
            )
        )
        monitors = rows.scalars().all()
        for monitor in monitors:
            if monitor.last_checked_at is None:
                check_http_monitor.delay(str(monitor.id))
                enqueued += 1
                continue
            due_at = monitor.last_checked_at + timedelta(seconds=monitor.interval_seconds)
            if now >= due_at:
                check_http_monitor.delay(str(monitor.id))
                enqueued += 1
    return enqueued
