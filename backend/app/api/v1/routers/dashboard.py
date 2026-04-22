from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps_auth import get_current_user
from app.core.database import get_db
from app.models.monitor import Monitor, MonitorStatus
from app.models.user import User
from app.schemas.monitor import DashboardSummaryResponse, MonitorListItem
from app.services.monitor_service import get_monitor_risk_fields
from app.services.uptime_service import aggregate_uptime_for_user, clamp_uptime_range, default_uptime_window

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _to_monitor_item(
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
    return [
        _to_monitor_item(
            m,
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
    return [
        _to_monitor_item(
            m,
            last_failure_at=risk_map.get(m.id, (None, 0))[0],
            consecutive_failures=risk_map.get(m.id, (None, 0))[1],
        )
        for m in items
    ]
