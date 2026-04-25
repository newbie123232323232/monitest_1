from fastapi import APIRouter

from app.api.v1.routers import auth, dashboard, health, me, monitors, probe_regions, runtime, status_pages

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(monitors.router)
api_router.include_router(probe_regions.router)
api_router.include_router(dashboard.router)
api_router.include_router(runtime.router)
api_router.include_router(status_pages.router)
api_router.include_router(status_pages.public_router)
