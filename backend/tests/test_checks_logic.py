from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from app.models.monitor import CheckRunStatus
from app.workers.tasks import checks
from app.workers.tasks.checks import (
    _consensus_monitor_status,
    _ensure_public_target,
    _is_retryable_status,
    _map_http_exception,
    _should_send_still_down_alert,
    _status_from_http,
)


def test_status_from_http_marks_slow_and_errors() -> None:
    assert (
        _status_from_http(
            status_code=200,
            response_time_ms=120,
            slow_threshold_ms=500,
            accepted_status_codes="200-399",
        )
        == CheckRunStatus.UP
    )
    assert (
        _status_from_http(
            status_code=200,
            response_time_ms=700,
            slow_threshold_ms=500,
            accepted_status_codes="200-399",
        )
        == CheckRunStatus.SLOW
    )
    assert (
        _status_from_http(
            status_code=503,
            response_time_ms=100,
            slow_threshold_ms=500,
            accepted_status_codes="200-399",
        )
        == CheckRunStatus.HTTP_ERROR
    )
    assert (
        _status_from_http(
            status_code=403,
            response_time_ms=100,
            slow_threshold_ms=500,
            accepted_status_codes="200-403",
        )
        == CheckRunStatus.UP
    )


def test_map_http_exception_types() -> None:
    timeout_status, timeout_error = _map_http_exception(httpx.ReadTimeout("timed out"))
    assert timeout_status == CheckRunStatus.TIMEOUT
    assert timeout_error == "timeout"

    tls_status, tls_error = _map_http_exception(httpx.ConnectError("SSL certificate verify failed"))
    assert tls_status == CheckRunStatus.TLS_ERROR
    assert tls_error == "tls_error"

    dns_status, dns_error = _map_http_exception(httpx.ConnectError("nodename nor servname provided"))
    assert dns_status == CheckRunStatus.DNS_ERROR
    assert dns_error == "dns_error"

    down_status, down_error = _map_http_exception(httpx.HTTPError("other"))
    assert down_status == CheckRunStatus.DOWN
    assert down_error == "http_error"


def test_retryable_statuses() -> None:
    assert _is_retryable_status(CheckRunStatus.TIMEOUT) is True
    assert _is_retryable_status(CheckRunStatus.DNS_ERROR) is True
    assert _is_retryable_status(CheckRunStatus.TLS_ERROR) is True
    assert _is_retryable_status(CheckRunStatus.HTTP_ERROR) is True
    assert _is_retryable_status(CheckRunStatus.UP) is False
    assert _is_retryable_status(CheckRunStatus.SLOW) is False


def test_consensus_monitor_status_majority_down_and_recovery() -> None:
    assert (
        _consensus_monitor_status(
            [CheckRunStatus.UP, CheckRunStatus.HTTP_ERROR, CheckRunStatus.TIMEOUT]
        )
        == checks.MonitorStatus.DOWN
    )
    assert (
        _consensus_monitor_status(
            [CheckRunStatus.HTTP_ERROR, CheckRunStatus.UP, CheckRunStatus.UP]
        )
        == checks.MonitorStatus.UP
    )
    assert (
        _consensus_monitor_status(
            [CheckRunStatus.SLOW, CheckRunStatus.UP, CheckRunStatus.HTTP_ERROR]
        )
        == checks.MonitorStatus.SLOW
    )


@pytest.mark.asyncio
async def test_ensure_public_target_blocks_private_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_getaddrinfo(host: str, port: int, type: int):  # noqa: A002
        return [
            (2, 1, 6, "", ("10.0.0.5", port)),
        ]

    loop = checks.asyncio.get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", _fake_getaddrinfo)

    with pytest.raises(ValueError, match="private/internal"):
        await _ensure_public_target("http://example.com")


def test_should_send_still_down_alert_timeline() -> None:
    now = datetime.now(UTC)
    incident = SimpleNamespace(
        opened_at=now - timedelta(minutes=40),
        reminder_count=0,
        last_alert_sent_at=now - timedelta(minutes=31),
    )
    assert (
        _should_send_still_down_alert(
            incident=incident,
            now=now,
            cooldown_minutes=10,
            reminder_minutes=30,
            max_reminders=24,
        )
        is True
    )

    incident.last_alert_sent_at = now - timedelta(minutes=5)
    assert (
        _should_send_still_down_alert(
            incident=incident,
            now=now,
            cooldown_minutes=10,
            reminder_minutes=30,
            max_reminders=24,
        )
        is False
    )

    incident.reminder_count = 24
    incident.last_alert_sent_at = now - timedelta(minutes=45)
    assert (
        _should_send_still_down_alert(
            incident=incident,
            now=now,
            cooldown_minutes=10,
            reminder_minutes=30,
            max_reminders=24,
        )
        is False
    )
