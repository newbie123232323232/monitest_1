from fastapi import APIRouter, Depends

from app.api.v1.deps_auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
async def read_me(user: User = Depends(get_current_user)) -> dict[str, str]:
    return {"id": str(user.id), "email": user.email}
