from fastapi import APIRouter

from app.api.v1.routers import auth, dashboard, health, me, monitors

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(monitors.router)
api_router.include_router(dashboard.router)
