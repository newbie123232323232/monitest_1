import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps_auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.monitor import AlertEvent, CheckRun, Incident, Monitor, MonitorStatus
from app.models.user import User
from app.schemas.monitor import (
    AlertEventItemResponse,
    CheckRunItemResponse,
    IncidentItemResponse,
    MonitorCreateRequest,
    MonitorDetailResponse,
    MonitorListItem,
    MonitorListResponse,
    MonitorUpdateRequest,
    MonitorUptimeResponse,
    RunCheckResponse,
)
from app.services.monitor_service import (
    MonitorValidationError,
    get_monitor_risk_fields,
    get_monitor_by_id,
    enforce_run_check_rate_limit,
    list_monitors,
    validate_monitor_timing,
    validate_monitor_url_host,
)
from app.services.uptime_service import clamp_uptime_range, default_uptime_window, uptime_stats_for_monitor
from app.workers.tasks.checks import check_http_monitor

router = APIRouter(prefix="/monitors", tags=["monitors"])


def to_monitor_item(
    m: Monitor,
    last_failure_at: datetime | None = None,
    consecutive_failures: int = 0,
) -> MonitorListItem:
    return MonitorListItem(
        id=m.id,
        name=m.name,
        url=m.url,
        monitor_type=m.monitor_type,
        current_status=m.current_status,
        interval_seconds=m.interval_seconds,
        timeout_seconds=m.timeout_seconds,
        probe_region=m.probe_region,
        is_paused=m.is_paused,
        last_checked_at=m.last_checked_at,
        last_response_time_ms=m.last_response_time_ms,
        last_failure_at=last_failure_at,
        consecutive_failures=consecutive_failures,
        created_at=m.created_at,
    )


def to_monitor_detail(m: Monitor) -> MonitorDetailResponse:
    return MonitorDetailResponse(
        id=m.id,
        user_id=m.user_id,
        name=m.name,
        url=m.url,
        monitor_type=m.monitor_type,
        interval_seconds=m.interval_seconds,
        timeout_seconds=m.timeout_seconds,
        max_retries=m.max_retries,
        slow_threshold_ms=m.slow_threshold_ms,
        probe_region=m.probe_region,
        detect_content_change=m.detect_content_change,
        is_paused=m.is_paused,
        current_status=m.current_status,
        last_checked_at=m.last_checked_at,
        last_response_time_ms=m.last_response_time_ms,
        last_status_code=m.last_status_code,
        last_error_message=m.last_error_message,
        last_success_at=m.last_success_at,
        created_at=m.created_at,
        updated_at=m.updated_at,
        deleted_at=m.deleted_at,
    )


@router.post("", response_model=MonitorDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_monitor(
    body: MonitorCreateRequest,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MonitorDetailResponse:
    try:
        validate_monitor_timing(body.interval_seconds, body.timeout_seconds)
        validate_monitor_url_host(str(body.url))
    except MonitorValidationError as e:
        raise HTTPException(status_code=400, detail=e.message) from e

    monitor = Monitor(
        user_id=user.id,
        name=body.name.strip(),
        url=str(body.url),
        monitor_type=body.monitor_type,
        interval_seconds=body.interval_seconds,
        timeout_seconds=body.timeout_seconds,
        max_retries=body.max_retries,
        slow_threshold_ms=body.slow_threshold_ms,
        probe_region=body.probe_region.strip(),
        detect_content_change=body.detect_content_change,
        current_status=MonitorStatus.PENDING,
    )
    session.add(monitor)
    await session.commit()
    await session.refresh(monitor)
    check_http_monitor.delay(str(monitor.id))
    return to_monitor_detail(monitor)


@router.get("", response_model=MonitorListResponse)
async def get_monitors(
    status_filter: MonitorStatus | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MonitorListResponse:
    items, total = await list_monitors(
        session=session,
        user_id=user.id,
        status=status_filter,
        search=q,
        page=page,
        page_size=page_size,
    )
    risk_map = await get_monitor_risk_fields(session=session, monitor_ids=[item.id for item in items])
    return MonitorListResponse(
        items=[
            to_monitor_item(
                item,
                last_failure_at=risk_map.get(item.id, (None, 0))[0],
                consecutive_failures=risk_map.get(item.id, (None, 0))[1],
            )
            for item in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{monitor_id}", response_model=MonitorDetailResponse)
async def get_monitor(
    monitor_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MonitorDetailResponse:
    monitor = await get_monitor_by_id(session=session, user_id=user.id, monitor_id=monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return to_monitor_detail(monitor)


@router.patch("/{monitor_id}", response_model=MonitorDetailResponse)
async def update_monitor(
    monitor_id: uuid.UUID,
    body: MonitorUpdateRequest,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MonitorDetailResponse:
    monitor = await get_monitor_by_id(session=session, user_id=user.id, monitor_id=monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")

    data = body.model_dump(exclude_unset=True)
    new_interval = data.get("interval_seconds", monitor.interval_seconds)
    new_timeout = data.get("timeout_seconds", monitor.timeout_seconds)
    try:
        validate_monitor_timing(new_interval, new_timeout)
        if "url" in data and data["url"] is not None:
            validate_monitor_url_host(str(data["url"]))
    except MonitorValidationError as e:
        raise HTTPException(status_code=400, detail=e.message) from e

    if "name" in data and data["name"] is not None:
        monitor.name = data["name"].strip()
    if "url" in data and data["url"] is not None:
        monitor.url = str(data["url"])
    if "interval_seconds" in data and data["interval_seconds"] is not None:
        monitor.interval_seconds = data["interval_seconds"]
    if "timeout_seconds" in data and data["timeout_seconds"] is not None:
        monitor.timeout_seconds = data["timeout_seconds"]
    if "max_retries" in data and data["max_retries"] is not None:
        monitor.max_retries = data["max_retries"]
    if "slow_threshold_ms" in data and data["slow_threshold_ms"] is not None:
        monitor.slow_threshold_ms = data["slow_threshold_ms"]
    if "probe_region" in data and data["probe_region"] is not None:
        monitor.probe_region = data["probe_region"].strip()
    if "detect_content_change" in data and data["detect_content_change"] is not None:
        monitor.detect_content_change = data["detect_content_change"]
    if "is_paused" in data and data["is_paused"] is not None:
        monitor.is_paused = data["is_paused"]
        monitor.current_status = MonitorStatus.PAUSED if monitor.is_paused else MonitorStatus.PENDING

    await session.commit()
    await session.refresh(monitor)
    return to_monitor_detail(monitor)


@router.delete("/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monitor(
    monitor_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    monitor = await get_monitor_by_id(session=session, user_id=user.id, monitor_id=monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")

    monitor.deleted_at = datetime.now(UTC)
    await session.commit()


@router.post("/{monitor_id}/run-check", response_model=RunCheckResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_monitor_check_now(
    monitor_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RunCheckResponse:
    monitor = await get_monitor_by_id(session=session, user_id=user.id, monitor_id=monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    try:
        enforce_run_check_rate_limit(
            monitor=monitor,
            min_interval_seconds=settings.run_check_min_interval_seconds,
        )
    except MonitorValidationError as e:
        detail = e.message
        status_code = 409 if "already checking" in detail else 429
        raise HTTPException(status_code=status_code, detail=detail) from e
    task = check_http_monitor.delay(str(monitor.id))
    return RunCheckResponse(monitor_id=monitor.id, task_id=task.id, status="queued")


@router.get("/{monitor_id}/uptime", response_model=MonitorUptimeResponse)
async def get_monitor_uptime(
    monitor_id: uuid.UUID,
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MonitorUptimeResponse:
    monitor = await get_monitor_by_id(session=session, user_id=user.id, monitor_id=monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    try:
        from_dt, to_dt = clamp_uptime_range(from_ts, to_ts)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    total, success, pct = await uptime_stats_for_monitor(
        session=session,
        user_id=user.id,
        monitor_id=monitor_id,
        from_dt=from_dt,
        to_dt=to_dt,
    )
    return MonitorUptimeResponse(
        window_from=from_dt,
        window_to=to_dt,
        total_checks=total,
        success_checks=success,
        uptime_percent=pct,
    )


@router.get("/{monitor_id}/checks", response_model=list[CheckRunItemResponse])
async def get_monitor_checks(
    monitor_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    from_ts: datetime | None = Query(default=None, alias="from"),
    to_ts: datetime | None = Query(default=None, alias="to"),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CheckRunItemResponse]:
    monitor = await get_monitor_by_id(session=session, user_id=user.id, monitor_id=monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")

    try:
        if from_ts is not None or to_ts is not None:
            uf, ut = clamp_uptime_range(from_ts, to_ts)
        else:
            uf, ut = default_uptime_window()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    cond = and_(
        CheckRun.monitor_id == monitor.id,
        CheckRun.finished_at >= uf,
        CheckRun.finished_at <= ut,
    )

    rows = await session.execute(
        select(CheckRun)
        .where(cond)
        .order_by(CheckRun.created_at.desc())
        .limit(limit)
    )
    return [
        CheckRunItemResponse(
            id=item.id,
            status=item.status,
            started_at=item.started_at,
            finished_at=item.finished_at,
            response_time_ms=item.response_time_ms,
            status_code=item.status_code,
            error_type=item.error_type,
            error_message=item.error_message,
            final_url=item.final_url,
            content_type=item.content_type,
            dns_resolve_ms=item.dns_resolve_ms,
            tcp_connect_ms=item.tcp_connect_ms,
            tls_handshake_ms=item.tls_handshake_ms,
            ttfb_ms=item.ttfb_ms,
            retry_count=item.retry_count,
            created_at=item.created_at,
        )
        for item in rows.scalars().all()
    ]


@router.get("/{monitor_id}/incidents", response_model=list[IncidentItemResponse])
async def get_monitor_incidents(
    monitor_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[IncidentItemResponse]:
    monitor = await get_monitor_by_id(session=session, user_id=user.id, monitor_id=monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    rows = await session.execute(
        select(Incident)
        .where(Incident.monitor_id == monitor.id)
        .order_by(Incident.opened_at.desc())
        .limit(limit)
    )
    return [
        IncidentItemResponse(
            id=i.id,
            monitor_id=i.monitor_id,
            opened_at=i.opened_at,
            closed_at=i.closed_at,
            status=i.status,
            open_reason=i.open_reason,
            close_reason=i.close_reason,
            first_failed_check_id=i.first_failed_check_id,
            last_failed_check_id=i.last_failed_check_id,
            created_at=i.created_at,
            updated_at=i.updated_at,
        )
        for i in rows.scalars().all()
    ]


@router.get("/{monitor_id}/alerts", response_model=list[AlertEventItemResponse])
async def get_monitor_alert_events(
    monitor_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AlertEventItemResponse]:
    monitor = await get_monitor_by_id(session=session, user_id=user.id, monitor_id=monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitor not found")
    rows = await session.execute(
        select(AlertEvent)
        .where(AlertEvent.monitor_id == monitor.id)
        .order_by(AlertEvent.created_at.desc())
        .limit(limit)
    )
    return [
        AlertEventItemResponse(
            id=a.id,
            incident_id=a.incident_id,
            monitor_id=a.monitor_id,
            channel=a.channel,
            event_type=a.event_type,
            sent_to=a.sent_to,
            sent_at=a.sent_at,
            send_status=a.send_status,
            error_message=a.error_message,
            created_at=a.created_at,
        )
        for a in rows.scalars().all()
    ]
