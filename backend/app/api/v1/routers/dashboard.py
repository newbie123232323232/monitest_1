from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps_auth import get_current_user
from app.core.database import get_db
from app.models.monitor import CheckRun, CheckRunStatus, Monitor, MonitorStatus
from app.models.monitor_expiry import MonitorExpiryStatus
from app.models.user import User
from app.schemas.monitor import DashboardRegionSummaryItem, DashboardSummaryResponse, MonitorListItem
from app.schemas.monitor_expiry import ExpirySummaryResponse
from app.services.monitor_service import get_monitor_probe_regions_map, get_monitor_risk_fields
from app.services.uptime_service import aggregate_uptime_for_user, clamp_uptime_range, default_uptime_window

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _to_monitor_item(
    m: Monitor,
    probe_regions: list[str],
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
        accepted_status_codes=m.accepted_status_codes,
        probe_regions=probe_regions,
        active_region=m.active_region,
        is_paused=m.is_paused,
        last_checked_at=m.last_checked_at,
        last_response_time_ms=m.last_response_time_ms,
        last_failure_at=last_failure_at,
        consecutive_failures=consecutive_failures,
        created_at=m.created_at,
    )


@router.get("/summary", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    uptime_from: datetime | None = None,
    uptime_to: datetime | None = None,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DashboardSummaryResponse:
    q = await session.execute(
        select(
            func.count(Monitor.id),
            func.sum(case((Monitor.current_status == MonitorStatus.UP, 1), else_=0)),
            func.sum(case((Monitor.current_status == MonitorStatus.DOWN, 1), else_=0)),
            func.sum(case((Monitor.current_status == MonitorStatus.PENDING, 1), else_=0)),
            func.sum(case((Monitor.current_status == MonitorStatus.CHECKING, 1), else_=0)),
            func.sum(case((Monitor.current_status == MonitorStatus.SLOW, 1), else_=0)),
            func.sum(case((Monitor.current_status == MonitorStatus.PAUSED, 1), else_=0)),
            func.avg(Monitor.last_response_time_ms),
        ).where(Monitor.user_id == user.id, Monitor.deleted_at.is_(None))
    )
    row = q.one()

    try:
        if uptime_from is not None or uptime_to is not None:
            uf, ut = clamp_uptime_range(uptime_from, uptime_to)
        else:
            uf, ut = default_uptime_window(datetime.now(UTC))
        total_chk, succ_chk, pct = await aggregate_uptime_for_user(session, user.id, uf, ut)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return DashboardSummaryResponse(
        total_monitors=int(row[0] or 0),
        up=int(row[1] or 0),
        down=int(row[2] or 0),
        pending=int(row[3] or 0),
        checking=int(row[4] or 0),
        slow=int(row[5] or 0),
        paused=int(row[6] or 0),
        avg_response_time_ms=float(row[7]) if row[7] is not None else None,
        uptime_window_from=uf,
        uptime_window_to=ut,
        uptime_total_checks=total_chk,
        uptime_success_checks=succ_chk,
        average_uptime_percent=pct,
    )


@router.get("/recent-monitors", response_model=list[MonitorListItem])
async def get_recent_monitors(
    limit: int = 10,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MonitorListItem]:
    rows = await session.execute(
        select(Monitor)
        .where(Monitor.user_id == user.id, Monitor.deleted_at.is_(None))
        .order_by(Monitor.updated_at.desc())
        .limit(max(1, min(limit, 50)))
    )
    items = rows.scalars().all()
    risk_map = await get_monitor_risk_fields(session=session, monitor_ids=[m.id for m in items])
    region_map = await get_monitor_probe_regions_map(session=session, monitor_ids=[m.id for m in items])
    return [
        _to_monitor_item(
            m,
            probe_regions=region_map.get(m.id, []),
            last_failure_at=risk_map.get(m.id, (None, 0))[0],
            consecutive_failures=risk_map.get(m.id, (None, 0))[1],
        )
        for m in items
    ]


@router.get("/recent-failures", response_model=list[MonitorListItem])
async def get_recent_failures(
    limit: int = 10,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MonitorListItem]:
    rows = await session.execute(
        select(Monitor)
        .where(
            Monitor.user_id == user.id,
            Monitor.deleted_at.is_(None),
            Monitor.current_status == MonitorStatus.DOWN,
        )
        .order_by(Monitor.last_checked_at.desc().nullslast())
        .limit(max(1, min(limit, 50)))
    )
    items = rows.scalars().all()
    risk_map = await get_monitor_risk_fields(session=session, monitor_ids=[m.id for m in items])
    region_map = await get_monitor_probe_regions_map(session=session, monitor_ids=[m.id for m in items])
    return [
        _to_monitor_item(
            m,
            probe_regions=region_map.get(m.id, []),
            last_failure_at=risk_map.get(m.id, (None, 0))[0],
            consecutive_failures=risk_map.get(m.id, (None, 0))[1],
        )
        for m in items
    ]


@router.get("/expiry-summary", response_model=ExpirySummaryResponse)
async def get_expiry_summary(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExpirySummaryResponse:
    rows = await session.execute(
        select(MonitorExpiryStatus.ssl_state)
        .join(Monitor, Monitor.id == MonitorExpiryStatus.monitor_id)
        .where(Monitor.user_id == user.id, Monitor.deleted_at.is_(None))
    )
    counts = {
        "ok": 0,
        "warn_30d": 0,
        "warn_14d": 0,
        "warn_7d": 0,
        "warn_1d": 0,
        "expired": 0,
        "unknown": 0,
    }
    for (state,) in rows.all():
        key = state if state in counts else "unknown"
        counts[key] += 1
    total = sum(counts.values())
    return ExpirySummaryResponse(
        total_with_ssl_data=total,
        ok=counts["ok"],
        warn_30d=counts["warn_30d"],
        warn_14d=counts["warn_14d"],
        warn_7d=counts["warn_7d"],
        warn_1d=counts["warn_1d"],
        expired=counts["expired"],
        unknown=counts["unknown"],
    )


@router.get("/region-summary", response_model=list[DashboardRegionSummaryItem])
async def get_region_summary(
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DashboardRegionSummaryItem]:
    try:
        if from_ts is not None or to_ts is not None:
            from_dt, to_dt = clamp_uptime_range(from_ts, to_ts)
        else:
            from_dt, to_dt = default_uptime_window(datetime.now(UTC))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    rows = await session.execute(
        select(
            CheckRun.probe_region,
            func.count(CheckRun.id),
            func.sum(case((CheckRun.status == CheckRunStatus.UP, 1), else_=0)),
            func.sum(case((CheckRun.status == CheckRunStatus.SLOW, 1), else_=0)),
            func.avg(CheckRun.response_time_ms),
            func.max(CheckRun.finished_at),
        )
        .join(Monitor, Monitor.id == CheckRun.monitor_id)
        .where(
            Monitor.user_id == user.id,
            Monitor.deleted_at.is_(None),
            CheckRun.finished_at >= from_dt,
            CheckRun.finished_at <= to_dt,
        )
        .group_by(CheckRun.probe_region)
        .order_by(func.max(CheckRun.finished_at).desc())
    )

    out: list[DashboardRegionSummaryItem] = []
    for probe_region, total, up, slow, avg_ms, last_finished_at in rows.all():
        total_i = int(total or 0)
        up_i = int(up or 0)
        slow_i = int(slow or 0)
        out.append(
            DashboardRegionSummaryItem(
                probe_region=probe_region or "global",
                total_checks=total_i,
                up_checks=up_i,
                slow_checks=slow_i,
                down_error_checks=max(0, total_i - up_i - slow_i),
                avg_response_time_ms=float(avg_ms) if avg_ms is not None else None,
                last_finished_at=last_finished_at,
            )
        )
    return out
