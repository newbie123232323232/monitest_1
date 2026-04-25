from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TypeVar

import redis
from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps_auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.monitor import CheckRun, CheckRunStatus, Monitor
from app.models.user import User
from app.schemas.runtime import RuntimeHealthResponse, RuntimeQueueProfileResponse

router = APIRouter(prefix="/runtime", tags=["runtime"])

_BEAT_HEARTBEAT_KEY = "moni:runtime:beat:last_seen_at"
_WORKER_HEARTBEAT_KEY = "moni:runtime:worker:last_seen_at"
T = TypeVar("T")


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1.5,
        socket_timeout=1.5,
    )


def _check_redis_ok() -> bool:
    client = _redis_client()
    try:
        return bool(client.ping())
    finally:
        client.close()


def _get_last_seen(key: str) -> datetime | None:
    client = _redis_client()
    try:
        raw = client.get(key)
    finally:
        client.close()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


async def _safe_to_thread(fn, fallback: T, timeout_seconds: float = 3.0) -> T:
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn), timeout=timeout_seconds)
    except Exception:  # noqa: BLE001
        return fallback


@router.get("/health", response_model=RuntimeHealthResponse)
async def get_runtime_health(
    user: User = Depends(get_current_user),  # noqa: ARG001 - keeps endpoint private/authenticated
) -> RuntimeHealthResponse:
    now = datetime.now(UTC)
    redis_ok, worker_last_seen, beat_last_seen = await asyncio.gather(
        _safe_to_thread(_check_redis_ok, False, timeout_seconds=3.0),
        _safe_to_thread(lambda: _get_last_seen(_WORKER_HEARTBEAT_KEY), None, timeout_seconds=3.0),
        _safe_to_thread(lambda: _get_last_seen(_BEAT_HEARTBEAT_KEY), None, timeout_seconds=3.0),
    )

    worker_ok = False
    if worker_last_seen is not None:
        worker_age = max(0, int((now - worker_last_seen).total_seconds()))
        worker_ok = worker_age <= settings.runtime_beat_stale_seconds

    beat_age: int | None = None
    beat_ok = False
    if beat_last_seen is not None:
        beat_age = max(0, int((now - beat_last_seen).total_seconds()))
        beat_ok = beat_age <= settings.runtime_beat_stale_seconds

    # Backward-compatibility warm-up: right after deploy/restart, beat heartbeat may exist
    # while worker heartbeat key has not been populated yet.
    if not worker_ok and beat_ok and worker_last_seen is None:
        worker_ok = True

    degraded_reasons: list[str] = []
    if not redis_ok:
        degraded_reasons.append("redis_unreachable")
    if not worker_ok:
        degraded_reasons.append("celery_worker_unreachable")
    if not beat_ok:
        degraded_reasons.append("celery_beat_stale_or_missing_heartbeat")

    return RuntimeHealthResponse(
        status="ok" if not degraded_reasons else "degraded",
        checked_at=now,
        redis_ok=redis_ok,
        worker_ok=worker_ok,
        beat_ok=beat_ok,
        beat_last_seen_at=beat_last_seen,
        beat_heartbeat_age_seconds=beat_age,
        degraded_reasons=degraded_reasons,
    )


@router.get("/queue-profile", response_model=RuntimeQueueProfileResponse)
async def get_runtime_queue_profile(
    window_minutes: int = Query(default=60, ge=5, le=1440),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # noqa: ARG001 - private endpoint
) -> RuntimeQueueProfileResponse:
    now = datetime.now(UTC)
    from_dt = now - timedelta(minutes=window_minutes)
    window_seconds = float(window_minutes * 60)

    cfg_row = (
        await session.execute(
            select(
                func.sum(case((Monitor.is_paused.is_(False), 1), else_=0)),
                func.avg(case((Monitor.is_paused.is_(False), Monitor.interval_seconds), else_=None)),
                func.avg(case((Monitor.is_paused.is_(False), Monitor.timeout_seconds), else_=None)),
                func.avg(case((Monitor.is_paused.is_(False), Monitor.max_retries), else_=None)),
                func.sum(case((Monitor.is_paused.is_(False), 1.0 / Monitor.interval_seconds), else_=0.0)),
            ).where(Monitor.user_id == user.id, Monitor.deleted_at.is_(None))
        )
    ).one()

    active_monitors = int(cfg_row[0] or 0)
    avg_interval = float(cfg_row[1]) if cfg_row[1] is not None else None
    avg_timeout = float(cfg_row[2]) if cfg_row[2] is not None else None
    avg_max_retries = float(cfg_row[3]) if cfg_row[3] is not None else None
    checks_per_second = float(cfg_row[4] or 0.0)
    expected_checks = checks_per_second * window_seconds

    stats = (
        await session.execute(
            select(
                func.count(CheckRun.id),
                func.sum(case((CheckRun.status == CheckRunStatus.TIMEOUT, 1), else_=0)),
                func.sum(case((CheckRun.retry_count > 0, 1), else_=0)),
                func.avg(CheckRun.response_time_ms),
            )
            .join(Monitor, Monitor.id == CheckRun.monitor_id)
            .where(
                Monitor.user_id == user.id,
                Monitor.deleted_at.is_(None),
                CheckRun.finished_at >= from_dt,
                CheckRun.finished_at <= now,
            )
        )
    ).one()

    checks_observed = int(stats[0] or 0)
    timeout_checks = int(stats[1] or 0)
    checks_with_retry = int(stats[2] or 0)
    avg_response = float(stats[3]) if stats[3] is not None else None

    timeout_ratio = (timeout_checks / checks_observed) if checks_observed else 0.0
    retry_ratio = (checks_with_retry / checks_observed) if checks_observed else 0.0

    recommendations: list[str] = []
    if avg_interval is not None and avg_timeout is not None and avg_timeout > avg_interval * 0.6:
        recommendations.append("avg_timeout_too_close_to_interval")
    if timeout_ratio >= 0.2:
        recommendations.append("high_timeout_ratio_reduce_timeout_or_retries")
    if retry_ratio >= 0.3:
        recommendations.append("high_retry_ratio_consider_max_retries_1")
    if active_monitors > 0 and checks_observed > 0 and expected_checks > 0 and checks_observed < expected_checks * 0.6:
        recommendations.append("observed_checks_below_expected_possible_queue_lag")

    return RuntimeQueueProfileResponse(
        checked_at=now,
        window_minutes=window_minutes,
        active_monitors=active_monitors,
        expected_checks_in_window=round(expected_checks, 2),
        checks_observed=checks_observed,
        timeout_checks=timeout_checks,
        checks_with_retry=checks_with_retry,
        timeout_ratio=round(timeout_ratio, 4),
        retry_ratio=round(retry_ratio, 4),
        avg_response_time_ms=avg_response,
        avg_interval_seconds=avg_interval,
        avg_timeout_seconds=avg_timeout,
        avg_max_retries=avg_max_retries,
        recommendations=recommendations,
    )
