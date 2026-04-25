import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.v1 import deps_auth
from app.core.database import AsyncSessionLocal
from app.main import app
from app.models.monitor import Monitor, MonitorStatus
from app.models.user import User
from app.workers.tasks import checks


@dataclass
class _DummyTask:
    id: str


@pytest.mark.asyncio
async def test_monitor_ownership_filter_search_and_run_check(monkeypatch):
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    queued: list[str] = []

    def _fake_delay(monitor_id: str):
        queued.append(monitor_id)
        return _DummyTask(id=f"task-{monitor_id}")

    monkeypatch.setattr(checks.check_http_monitor, "delay", _fake_delay)

    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(User).where(User.email.in_(["owner-a@test.local", "owner-b@test.local"]))
        )
        session.add(
            User(
                id=user_a_id,
                email="owner-a@test.local",
                hashed_password=None,
                is_verified=True,
            )
        )
        session.add(
            User(
                id=user_b_id,
                email="owner-b@test.local",
                hashed_password=None,
                is_verified=True,
            )
        )
        await session.commit()

    async def _override_current_user(request: Request) -> User:
        user_header = request.headers.get("x-test-user", "a")
        user_id = user_a_id if user_header == "a" else user_b_id
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one()
            return user

    app.dependency_overrides[deps_auth.get_current_user] = _override_current_user
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")

    try:
        create_a = await client.post(
            "/api/v1/monitors",
            headers={"x-test-user": "a"},
            json={
                "name": "it-owner-a",
                "url": "https://example.com",
                "interval_seconds": 60,
                "timeout_seconds": 10,
                "accepted_status_codes": "200-299,301,302",
            },
        )
        assert create_a.status_code == 201
        monitor_a_id = create_a.json()["id"]
        assert create_a.json()["accepted_status_codes"] == "200-299,301,302"

        create_b = await client.post(
            "/api/v1/monitors",
            headers={"x-test-user": "b"},
            json={
                "name": "it-owner-b",
                "url": "https://example.org",
                "interval_seconds": 60,
                "timeout_seconds": 10,
            },
        )
        assert create_b.status_code == 201
        monitor_b_id = create_b.json()["id"]

        assert str(monitor_a_id) in queued
        assert str(monitor_b_id) in queued

        forbidden = await client.get(f"/api/v1/monitors/{monitor_b_id}", headers={"x-test-user": "a"})
        assert forbidden.status_code == 404

        listed = await client.get("/api/v1/monitors?q=owner-a", headers={"x-test-user": "a"})
        assert listed.status_code == 200
        body = listed.json()
        assert body["total"] >= 1
        names = [item["name"] for item in body["items"]]
        assert "it-owner-a" in names
        assert "it-owner-b" not in names

        status_filtered = await client.get(
            f"/api/v1/monitors?status={MonitorStatus.PENDING.value}",
            headers={"x-test-user": "a"},
        )
        assert status_filtered.status_code == 200
        assert status_filtered.json()["total"] >= 1

        run_check = await client.post(
            f"/api/v1/monitors/{monitor_a_id}/run-check", headers={"x-test-user": "a"}
        )
        assert run_check.status_code == 202
        assert run_check.json()["status"] == "queued"
        assert run_check.json()["monitor_id"] == monitor_a_id

        updated = await client.patch(
            f"/api/v1/monitors/{monitor_a_id}",
            headers={"x-test-user": "a"},
            json={"accepted_status_codes": "200,201,204-299"},
        )
        assert updated.status_code == 200
        assert updated.json()["accepted_status_codes"] == "200,201,204-299"

        invalid_active_region = await client.patch(
            f"/api/v1/monitors/{monitor_a_id}",
            headers={"x-test-user": "a"},
            json={"active_region": "ap-south"},
        )
        assert invalid_active_region.status_code == 400
        assert "active_region must be one of probe_regions" in invalid_active_region.json()["message"]
    finally:
        await client.aclose()
        app.dependency_overrides.clear()
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(Monitor).where(
                    Monitor.user_id.in_([user_a_id, user_b_id]),
                    Monitor.name.in_(["it-owner-a", "it-owner-b"]),
                )
            )
            await session.execute(
                delete(User).where(User.email.in_(["owner-a@test.local", "owner-b@test.local"]))
            )
            await session.commit()


@pytest.mark.asyncio
async def test_monitor_create_rejects_internal_targets() -> None:
    user_id = uuid.uuid4()

    async with AsyncSessionLocal() as session:
        await session.execute(delete(User).where(User.email == "ssrf-user@test.local"))
        session.add(
            User(
                id=user_id,
                email="ssrf-user@test.local",
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
        blocked_localhost = await client.post(
            "/api/v1/monitors",
            json={
                "name": "it-ssrf-localhost",
                "url": "http://localhost:8080",
                "interval_seconds": 60,
                "timeout_seconds": 10,
            },
        )
        assert blocked_localhost.status_code == 400
        assert "local/internal hosts" in blocked_localhost.json()["message"]

        blocked_private_ip = await client.post(
            "/api/v1/monitors",
            json={
                "name": "it-ssrf-private",
                "url": "http://10.0.0.1",
                "interval_seconds": 60,
                "timeout_seconds": 10,
            },
        )
        assert blocked_private_ip.status_code == 400
        assert "private/internal IP" in blocked_private_ip.json()["message"]

        invalid_codes = await client.post(
            "/api/v1/monitors",
            json={
                "name": "it-ssrf-invalid-codes",
                "url": "https://example.com",
                "interval_seconds": 60,
                "timeout_seconds": 10,
                "accepted_status_codes": "200-abc",
            },
        )
        assert invalid_codes.status_code == 400
        assert "invalid status code range" in invalid_codes.json()["message"]
    finally:
        await client.aclose()
        app.dependency_overrides.clear()
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Monitor).where(Monitor.name.like("it-ssrf-%")))
            await session.execute(delete(User).where(User.email == "ssrf-user@test.local"))
            await session.commit()


@pytest.mark.asyncio
async def test_run_check_rate_limit_and_conflict(monkeypatch) -> None:
    user_id = uuid.uuid4()
    queued: list[str] = []

    def _fake_delay(monitor_id: str):
        queued.append(monitor_id)
        return _DummyTask(id=f"task-{monitor_id}")

    monkeypatch.setattr(checks.check_http_monitor, "delay", _fake_delay)

    async with AsyncSessionLocal() as session:
        await session.execute(delete(User).where(User.email == "ratelimit-user@test.local"))
        session.add(
            User(
                id=user_id,
                email="ratelimit-user@test.local",
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
        create = await client.post(
            "/api/v1/monitors",
            json={
                "name": "it-rate-limit",
                "url": "https://example.com",
                "interval_seconds": 60,
                "timeout_seconds": 10,
            },
        )
        assert create.status_code == 201
        monitor_id = create.json()["id"]

        async with AsyncSessionLocal() as session:
            monitor = await session.get(Monitor, monitor_id)
            assert monitor is not None
            monitor.last_checked_at = datetime.now(UTC)
            monitor.current_status = MonitorStatus.UP
            await session.commit()

        throttled = await client.post(f"/api/v1/monitors/{monitor_id}/run-check")
        assert throttled.status_code == 429
        assert "throttled" in throttled.json()["message"]
        queued_before_conflict = len(queued)

        async with AsyncSessionLocal() as session:
            monitor = await session.get(Monitor, monitor_id)
            assert monitor is not None
            monitor.last_checked_at = datetime.now(UTC) - timedelta(minutes=2)
            monitor.current_status = MonitorStatus.CHECKING
            await session.commit()

        conflict = await client.post(f"/api/v1/monitors/{monitor_id}/run-check")
        assert conflict.status_code == 409
        assert "already checking" in conflict.json()["message"]
        assert len(queued) == queued_before_conflict
    finally:
        await client.aclose()
        app.dependency_overrides.clear()
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Monitor).where(Monitor.name == "it-rate-limit"))
            await session.execute(delete(User).where(User.email == "ratelimit-user@test.local"))
            await session.commit()
