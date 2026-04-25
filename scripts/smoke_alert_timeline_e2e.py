from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import asyncpg
from dotenv import load_dotenv

from app.core.security import create_access_token

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

API_BASE = "http://127.0.0.1:8011/api/v1"
TEST_USER_ID = "6282e141-3021-4f62-ada3-d00c9ddbb1f3"
TEST_PREFIX = f"smoke-alert-timeline-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"


def _request(method: str, path: str, token: str, body: dict[str, Any] | None = None, retries: int = 3) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(
        f"{API_BASE}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=25) as resp:
            payload = resp.read().decode("utf-8")
            return json.loads(payload) if payload else None
    except HTTPError as e:
        payload = e.read().decode("utf-8", "ignore")
        if e.code == 429 and retries > 0:
            retry_after = 2
            try:
                parsed = json.loads(payload)
                msg = str(parsed.get("message", ""))
                if "retry after" in msg:
                    retry_after = int(msg.rsplit("retry after", 1)[1].strip().rstrip("s").strip())
            except Exception:
                pass
            time.sleep(max(1, retry_after))
            return _request(method, path, token, body, retries=retries - 1)
        raise RuntimeError(f"{method} {path} -> {e.code} {payload}") from e


def _wait_for_status(token: str, monitor_id: str, wanted: str, timeout_s: int = 120) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        detail = _request("GET", f"/monitors/{monitor_id}", token)
        if detail.get("current_status") == wanted:
            return detail
        time.sleep(2)
    raise RuntimeError(f"timeout waiting monitor={monitor_id} status={wanted}")


def _run_check_and_wait(token: str, monitor_id: str, timeout_s: int = 120) -> dict[str, Any]:
    before = _request("GET", f"/monitors/{monitor_id}", token)
    before_checked = before.get("last_checked_at")
    _request("POST", f"/monitors/{monitor_id}/run-check", token)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        cur = _request("GET", f"/monitors/{monitor_id}", token)
        if cur.get("last_checked_at") != before_checked and cur.get("current_status") != "checking":
            return cur
        time.sleep(2)
    raise RuntimeError(f"timeout waiting run-check completion monitor={monitor_id}")


def _wait_for_alert_type(token: str, monitor_id: str, event_type: str, timeout_s: int = 90) -> list[dict[str, Any]]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        alerts = _request("GET", f"/monitors/{monitor_id}/alerts?limit=50", token)
        if any(a.get("event_type") == event_type for a in alerts):
            return alerts
        time.sleep(2)
    raise RuntimeError(f"timeout waiting alert event_type={event_type} for monitor={monitor_id}")


async def _cleanup_by_monitor_id(monitor_id: str) -> None:
    db_url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    conn = await asyncpg.connect(db_url, timeout=10)
    try:
        # Scoped cleanup only by exact monitor_id (no broad delete).
        await conn.execute("DELETE FROM alert_events WHERE monitor_id = $1::uuid", monitor_id)
        await conn.execute("DELETE FROM incidents WHERE monitor_id = $1::uuid", monitor_id)
        await conn.execute("DELETE FROM check_runs WHERE monitor_id = $1::uuid", monitor_id)
        await conn.execute("DELETE FROM monitor_regions WHERE monitor_id = $1::uuid", monitor_id)
        await conn.execute("DELETE FROM monitor_expiry_status WHERE monitor_id = $1::uuid", monitor_id)
        await conn.execute("DELETE FROM monitors WHERE id = $1::uuid", monitor_id)
    finally:
        await conn.close()


async def _rewind_incident_for_still_down(incident_id: str) -> None:
    db_url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    conn = await asyncpg.connect(db_url, timeout=10)
    try:
        rewind = datetime.now(UTC) - timedelta(minutes=40)
        await conn.execute(
            """
            UPDATE incidents
            SET opened_at = $2::timestamptz,
                last_alert_sent_at = $2::timestamptz,
                reminder_count = 0
            WHERE id = $1::uuid
            """,
            incident_id,
            rewind,
        )
    finally:
        await conn.close()


def main() -> None:
    global API_BASE
    api_port = os.getenv("MONI_LOCAL_API_PORT", "8011").strip() or "8011"
    API_BASE = f"http://127.0.0.1:{api_port}/api/v1"
    token = create_access_token(TEST_USER_ID)
    monitor_id: str | None = None
    print(f"[smoke] start monitor timeline test prefix={TEST_PREFIX}")
    try:
        created = _request(
            "POST",
            "/monitors",
            token,
            body={
                "name": TEST_PREFIX,
                "url": "https://httpbin.org/status/500",
                "monitor_type": "http",
                "interval_seconds": 60,
                "timeout_seconds": 10,
                "max_retries": 1,
                "slow_threshold_ms": 1500,
                "accepted_status_codes": "200-399",
                "probe_regions": ["global"],
                "active_region": "global",
                "detect_content_change": False,
            },
        )
        monitor_id = created["id"]
        print(f"[smoke] created monitor_id={monitor_id}")

        # 1) DOWN + incident_opened
        cur = _run_check_and_wait(token, monitor_id)
        if cur.get("current_status") != "down":
            raise RuntimeError(f"expected down after fail check, got {cur.get('current_status')}")
        incidents = _request("GET", f"/monitors/{monitor_id}/incidents?limit=20", token)
        open_incident = next((i for i in incidents if i.get("status") == "open"), None)
        if not open_incident:
            raise RuntimeError("expected open incident after down check")
        alerts = _wait_for_alert_type(token, monitor_id, "incident_opened", timeout_s=90)
        print("[smoke] phase1 OK: incident_opened")

        # 2) STILL_DOWN (rewind incident timeline to avoid long wait)
        asyncio.run(_rewind_incident_for_still_down(open_incident["id"]))
        _run_check_and_wait(token, monitor_id)
        alerts2 = _wait_for_alert_type(token, monitor_id, "still_down", timeout_s=90)
        print("[smoke] phase2 OK: still_down")

        # 3) RECOVERED
        _request("PATCH", f"/monitors/{monitor_id}", token, body={"url": "https://httpbin.org/status/200"})
        cur2 = _run_check_and_wait(token, monitor_id)
        if cur2.get("current_status") not in {"up", "slow"}:
            raise RuntimeError(f"expected up/slow after recover check, got {cur2.get('current_status')}")
        incidents2 = _request("GET", f"/monitors/{monitor_id}/incidents?limit=20", token)
        if not any(i.get("status") == "closed" for i in incidents2):
            raise RuntimeError("expected closed incident after recovery")
        alerts3 = _wait_for_alert_type(token, monitor_id, "incident_recovered", timeout_s=90)
        print("[smoke] phase3 OK: incident_recovered")

        event_types = [a.get("event_type") for a in alerts3]
        print("[smoke] done event_types=", event_types)
        print("[smoke] PASS")
    finally:
        if monitor_id:
            print(f"[smoke] cleanup monitor_id={monitor_id}")
            asyncio.run(_cleanup_by_monitor_id(monitor_id))
            print("[smoke] cleanup done (scoped by monitor_id)")


if __name__ == "__main__":
    main()
