from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps_auth import get_current_user
from app.core.database import get_db
from app.models.probe_region import ProbeRegion
from app.models.user import User
from app.schemas.probe_region import ProbeRegionItemResponse

router = APIRouter(prefix="/probe-regions", tags=["probe-regions"])


@router.get("", response_model=list[ProbeRegionItemResponse])
async def list_probe_regions(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # noqa: ARG001 - keep endpoint authenticated
) -> list[ProbeRegionItemResponse]:
    rows = await session.execute(
        select(ProbeRegion)
        .where(ProbeRegion.is_active.is_(True))
        .order_by(ProbeRegion.sort_order.asc(), ProbeRegion.code.asc())
    )
    return [ProbeRegionItemResponse(code=r.code, name=r.name) for r in rows.scalars().all()]
