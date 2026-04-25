import uuid
from dataclasses import dataclass

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.v1 import deps_auth
from app.core.database import AsyncSessionLocal
from app.main import app
from app.models.monitor import Monitor
from app.models.status_page import StatusPage
from app.models.user import User
from app.workers.tasks import checks


@dataclass
class _DummyTask:
    id: str


@pytest.mark.asyncio
async def test_status_page_create_and_public_fetch(monkeypatch) -> None:
    user_id = uuid.uuid4()
    slug = f"it-prod-status-{uuid.uuid4().hex[:8]}"

    def _fake_delay(monitor_id: str):
        return _DummyTask(id=f"task-{monitor_id}")

    monkeypatch.setattr(checks.check_http_monitor, "delay", _fake_delay)

    async with AsyncSessionLocal() as session:
        await session.execute(delete(User).where(User.email == "statuspage-user@test.local"))
        session.add(
            User(
                id=user_id,
                email="statuspage-user@test.local",
                hashed_password=None,
                is_verified=True,
            )
        )
        await session.commit()

    async def _override_current_user(_: Request) -> User:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            return result.scalar_one()

    app.dependency_overrides[deps_auth.get_current_user] = _override_current_user
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")

    try:
        m1 = await client.post(
            "/api/v1/monitors",
            json={
                "name": "it-status-page-1",
                "url": "https://example.com",
                "interval_seconds": 60,
                "timeout_seconds": 10,
            },
        )
        assert m1.status_code == 201
        m2 = await client.post(
            "/api/v1/monitors",
            json={
                "name": "it-status-page-2",
                "url": "https://example.org",
                "interval_seconds": 60,
                "timeout_seconds": 10,
            },
        )
        assert m2.status_code == 201
        m1_id = m1.json()["id"]
        m2_id = m2.json()["id"]

        create_page = await client.post(
            "/api/v1/status-pages",
            json={
                "name": "Production Status",
                "slug": slug,
                "is_public": True,
                "monitor_ids": [m1_id, m2_id],
            },
        )
        assert create_page.status_code == 201
        body = create_page.json()
        assert body["slug"] == slug
        assert len(body["monitors"]) == 2

        listed = await client.get("/api/v1/status-pages")
        assert listed.status_code == 200
        assert len(listed.json()) >= 1

        public_page = await client.get(f"/api/v1/public/status-pages/{slug}")
        assert public_page.status_code == 200
        public_body = public_page.json()
        assert public_body["slug"] == slug
        assert len(public_body["monitors"]) == 2
        assert isinstance(public_body["incidents"], list)
    finally:
        await client.aclose()
        app.dependency_overrides.clear()
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(StatusPage).where(
                    StatusPage.user_id == user_id,
                    StatusPage.slug.like("it-prod-status-%"),
                )
            )
            await session.execute(delete(Monitor).where(Monitor.name.like("it-status-page-%")))
            await session.execute(delete(User).where(User.email == "statuspage-user@test.local"))
            await session.commit()
