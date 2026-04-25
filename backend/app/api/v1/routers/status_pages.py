import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps_auth import get_current_user
from app.core.database import get_db
from app.models.monitor import Incident, Monitor
from app.models.status_page import StatusPage, StatusPageMonitor
from app.models.user import User
from app.schemas.status_page import (
    PublicStatusPageResponse,
    StatusPageCreateRequest,
    StatusPageIncidentItem,
    StatusPageMonitorItem,
    StatusPageResponse,
    StatusPageUpdateRequest,
)

router = APIRouter(prefix="/status-pages", tags=["status-pages"])
public_router = APIRouter(prefix="/public/status-pages", tags=["public-status-pages"])


def _monitor_item(m: Monitor) -> StatusPageMonitorItem:
    return StatusPageMonitorItem(
        id=m.id,
        name=m.name,
        url=m.url,
        current_status=m.current_status,
        last_checked_at=m.last_checked_at,
        last_response_time_ms=m.last_response_time_ms,
    )


async def _load_monitors_for_page(session: AsyncSession, page_id: uuid.UUID) -> list[Monitor]:
    rows = await session.execute(
        select(Monitor)
        .join(StatusPageMonitor, StatusPageMonitor.monitor_id == Monitor.id)
        .where(StatusPageMonitor.status_page_id == page_id, Monitor.deleted_at.is_(None))
        .order_by(Monitor.created_at.desc())
    )
    return rows.scalars().all()


async def _require_owned_page(session: AsyncSession, user_id: uuid.UUID, page_id: uuid.UUID) -> StatusPage:
    row = await session.execute(select(StatusPage).where(StatusPage.id == page_id, StatusPage.user_id == user_id))
    page = row.scalar_one_or_none()
    if page is None:
        raise HTTPException(status_code=404, detail="Status page not found")
    return page


async def _validate_monitor_ownership(
    session: AsyncSession,
    user_id: uuid.UUID,
    monitor_ids: list[uuid.UUID],
) -> list[uuid.UUID]:
    if not monitor_ids:
        return []
    rows = await session.execute(
        select(Monitor.id).where(
            Monitor.id.in_(monitor_ids),
            Monitor.user_id == user_id,
            Monitor.deleted_at.is_(None),
        )
    )
    owned = {mid for (mid,) in rows.all()}
    missing = [mid for mid in monitor_ids if mid not in owned]
    if missing:
        raise HTTPException(status_code=400, detail="Some monitor_ids are invalid or not owned by user")
    return monitor_ids


async def _set_page_monitors(session: AsyncSession, page_id: uuid.UUID, monitor_ids: list[uuid.UUID]) -> None:
    await session.execute(delete(StatusPageMonitor).where(StatusPageMonitor.status_page_id == page_id))
    if monitor_ids:
        session.add_all(
            [StatusPageMonitor(status_page_id=page_id, monitor_id=mid) for mid in dict.fromkeys(monitor_ids)]
        )


@router.get("", response_model=list[StatusPageResponse])
async def list_status_pages(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[StatusPageResponse]:
    rows = await session.execute(
        select(StatusPage).where(StatusPage.user_id == user.id).order_by(StatusPage.created_at.desc())
    )
    pages = rows.scalars().all()
    result: list[StatusPageResponse] = []
    for page in pages:
        monitors = await _load_monitors_for_page(session, page.id)
        result.append(
            StatusPageResponse(
                id=page.id,
                user_id=page.user_id,
                name=page.name,
                slug=page.slug,
                is_public=page.is_public,
                maintenance_notes=page.maintenance_notes,
                created_at=page.created_at,
                updated_at=page.updated_at,
                monitors=[_monitor_item(m) for m in monitors],
            )
        )
    return result


@router.post("", response_model=StatusPageResponse, status_code=201)
async def create_status_page(
    body: StatusPageCreateRequest,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StatusPageResponse:
    await _validate_monitor_ownership(session, user.id, body.monitor_ids)
    page = StatusPage(
        user_id=user.id,
        name=body.name.strip(),
        slug=body.slug.strip(),
        is_public=body.is_public,
        maintenance_notes=(body.maintenance_notes.strip() if body.maintenance_notes else None),
    )
    session.add(page)
    try:
        await session.flush()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=409, detail="slug already exists") from exc
    await _set_page_monitors(session, page.id, body.monitor_ids)
    await session.commit()
    await session.refresh(page)
    monitors = await _load_monitors_for_page(session, page.id)
    return StatusPageResponse(
        id=page.id,
        user_id=page.user_id,
        name=page.name,
        slug=page.slug,
        is_public=page.is_public,
        maintenance_notes=page.maintenance_notes,
        created_at=page.created_at,
        updated_at=page.updated_at,
        monitors=[_monitor_item(m) for m in monitors],
    )


@router.patch("/{page_id}", response_model=StatusPageResponse)
async def update_status_page(
    page_id: uuid.UUID,
    body: StatusPageUpdateRequest,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StatusPageResponse:
    page = await _require_owned_page(session, user.id, page_id)
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        page.name = data["name"].strip()
    if "slug" in data and data["slug"] is not None:
        page.slug = data["slug"].strip()
    if "is_public" in data and data["is_public"] is not None:
        page.is_public = data["is_public"]
    if "maintenance_notes" in data:
        raw_notes = data["maintenance_notes"]
        page.maintenance_notes = raw_notes.strip() if isinstance(raw_notes, str) and raw_notes.strip() else None
    if "monitor_ids" in data and data["monitor_ids"] is not None:
        await _validate_monitor_ownership(session, user.id, data["monitor_ids"])
        await _set_page_monitors(session, page.id, data["monitor_ids"])
    try:
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=409, detail="slug already exists") from exc
    await session.refresh(page)
    monitors = await _load_monitors_for_page(session, page.id)
    return StatusPageResponse(
        id=page.id,
        user_id=page.user_id,
        name=page.name,
        slug=page.slug,
        is_public=page.is_public,
        maintenance_notes=page.maintenance_notes,
        created_at=page.created_at,
        updated_at=page.updated_at,
        monitors=[_monitor_item(m) for m in monitors],
    )


@router.delete("/{page_id}", status_code=204)
async def delete_status_page(
    page_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    page = await _require_owned_page(session, user.id, page_id)
    await session.delete(page)
    await session.commit()


@public_router.get("/{slug}", response_model=PublicStatusPageResponse)
async def get_public_status_page(
    slug: str,
    incident_limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> PublicStatusPageResponse:
    row = await session.execute(select(StatusPage).where(StatusPage.slug == slug))
    page = row.scalar_one_or_none()
    if page is None or not page.is_public:
        raise HTTPException(status_code=404, detail="Status page not found")
    monitors = await _load_monitors_for_page(session, page.id)
    monitor_ids = [m.id for m in monitors]
    incidents: list[StatusPageIncidentItem] = []
    if monitor_ids:
        inc_rows = await session.execute(
            select(Incident)
            .where(Incident.monitor_id.in_(monitor_ids))
            .order_by(Incident.opened_at.desc())
            .limit(incident_limit)
        )
        incidents = [
            StatusPageIncidentItem(
                id=i.id,
                monitor_id=i.monitor_id,
                status=i.status.value,
                opened_at=i.opened_at,
                closed_at=i.closed_at,
                open_reason=i.open_reason,
                close_reason=i.close_reason,
            )
            for i in inc_rows.scalars().all()
        ]
    return PublicStatusPageResponse(
        name=page.name,
        slug=page.slug,
        maintenance_notes=page.maintenance_notes,
        monitors=[_monitor_item(m) for m in monitors],
        incidents=incidents,
        generated_at=datetime.now(UTC),
    )
