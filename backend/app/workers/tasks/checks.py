import asyncio
import socket
import ssl
import time
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.models.monitor import (
    CheckRun,
    CheckRunStatus,
    Incident,
    IncidentStatus,
    Monitor,
    MonitorStatus,
)
from app.services.monitor_service import is_status_code_accepted
from app.workers.celery_app import celery_app
from app.workers.tasks.notify import send_incident_email


def _is_probe_failure(status: CheckRunStatus) -> bool:
    return status not in {CheckRunStatus.UP, CheckRunStatus.SLOW}


def _consensus_monitor_status(statuses: list[CheckRunStatus]) -> MonitorStatus:
    if not statuses:
        return MonitorStatus.DOWN
    total = len(statuses)
    down_votes = sum(1 for s in statuses if _is_probe_failure(s))
    required = (total // 2) + 1
    if down_votes >= required:
        return MonitorStatus.DOWN
    if any(s == CheckRunStatus.SLOW for s in statuses):
        return MonitorStatus.SLOW
    return MonitorStatus.UP


def _status_from_http(
    status_code: int,
    response_time_ms: int,
    slow_threshold_ms: int,
    accepted_status_codes: str,
) -> CheckRunStatus:
    if not is_status_code_accepted(status_code, accepted_status_codes):
        return CheckRunStatus.HTTP_ERROR
    if response_time_ms > slow_threshold_ms:
        return CheckRunStatus.SLOW
    return CheckRunStatus.UP


def _is_retryable_status(status: CheckRunStatus) -> bool:
    return status in {
        CheckRunStatus.TIMEOUT,
        CheckRunStatus.DNS_ERROR,
        CheckRunStatus.TLS_ERROR,
        CheckRunStatus.HTTP_ERROR,
        CheckRunStatus.DOWN,
    }


def _map_http_exception(exc: httpx.HTTPError) -> tuple[CheckRunStatus, str]:
    if isinstance(exc, httpx.TimeoutException):
        return CheckRunStatus.TIMEOUT, "timeout"
    if isinstance(exc, httpx.ConnectError):
        msg = str(exc).lower()
        if "certificate" in msg or "ssl" in msg or "tls" in msg:
            return CheckRunStatus.TLS_ERROR, "tls_error"
        return CheckRunStatus.DNS_ERROR, "dns_error"
    return CheckRunStatus.DOWN, "http_error"


def _should_send_still_down_alert(
    incident: Incident,
    now: datetime,
    cooldown_minutes: int,
    reminder_minutes: int,
    max_reminders: int,
) -> bool:
    if reminder_minutes <= 0 or max_reminders <= 0:
        return False
    if (incident.reminder_count or 0) >= max_reminders:
        return False
    if now < incident.opened_at + timedelta(minutes=max(cooldown_minutes, 0)):
        return False
    if incident.last_alert_sent_at is None:
        return False
    return now >= incident.last_alert_sent_at + timedelta(minutes=reminder_minutes)


def _parse_host_and_port(url: str) -> tuple[str, int, bool]:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    is_https = parsed.scheme == "https"
    if not host:
        raise ValueError("invalid host")
    if parsed.port:
        return host, parsed.port, is_https
    return host, (443 if is_https else 80), is_https


def _is_forbidden_ip(raw_ip: str) -> bool:
    try:
        ip = ip_address(raw_ip)
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def _ensure_public_target(url: str) -> None:
    host, port, _ = _parse_host_and_port(url)
    if host.lower() in {"localhost"} or host.lower().endswith(".local"):
        raise ValueError("target host is local/internal")
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not infos:
        raise ValueError("target host does not resolve")
    for info in infos:
        resolved_ip = info[4][0]
        if _is_forbidden_ip(resolved_ip):
            raise ValueError("target resolves to private/internal IP")


async def _collect_network_metrics(url: str, timeout_seconds: int) -> tuple[int | None, int | None, int | None]:
    host, port, is_https = _parse_host_and_port(url)
    loop = asyncio.get_running_loop()
    dns_ms: int | None = None
    tcp_ms: int | None = None
    tls_ms: int | None = None
    resolved_ip: str | None = None

    dns_start = time.perf_counter()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    dns_ms = int((time.perf_counter() - dns_start) * 1000)
    if infos:
        resolved_ip = infos[0][4][0]

    if resolved_ip:
        tcp_start = time.perf_counter()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(resolved_ip, port),
            timeout=timeout_seconds,
        )
        writer.close()
        await writer.wait_closed()
        tcp_ms = int((time.perf_counter() - tcp_start) * 1000)

    if is_https:
        tls_start = time.perf_counter()
        tls_ctx = ssl.create_default_context()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=tls_ctx, server_hostname=host),
            timeout=timeout_seconds,
        )
        writer.close()
        await writer.wait_closed()
        tls_total_ms = int((time.perf_counter() - tls_start) * 1000)
        tls_ms = max(0, tls_total_ms - (tcp_ms or 0))

    return dns_ms, tcp_ms, tls_ms


async def _perform_probe(
    client: httpx.AsyncClient,
    monitor: Monitor,
    probe_region: str,
    max_retries: int,
) -> dict[str, object | None]:
    started_at = datetime.now(UTC)
    finished_at = started_at
    response_time_ms: int | None = None
    dns_resolve_ms: int | None = None
    tcp_connect_ms: int | None = None
    tls_handshake_ms: int | None = None
    ttfb_ms: int | None = None
    status_code: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    final_url: str | None = None
    content_type: str | None = None
    run_status = CheckRunStatus.DOWN
    retry_count = 0

    for attempt in range(max_retries + 1):
        retry_count = attempt
        started_at = datetime.now(UTC)
        try:
            await _ensure_public_target(monitor.url)
            try:
                dns_resolve_ms, tcp_connect_ms, tls_handshake_ms = await _collect_network_metrics(
                    monitor.url, monitor.timeout_seconds
                )
            except Exception:
                dns_resolve_ms, tcp_connect_ms, tls_handshake_ms = None, None, None

            req_start = time.perf_counter()
            async with client.stream("GET", monitor.url, timeout=monitor.timeout_seconds) as response:
                ttfb_ms = int((time.perf_counter() - req_start) * 1000)
                await response.aread()
            finished_at = datetime.now(UTC)
            response_time_ms = int((finished_at - started_at).total_seconds() * 1000)
            status_code = response.status_code
            final_url = str(response.url)
            content_type = response.headers.get("content-type")
            run_status = _status_from_http(
                status_code=response.status_code,
                response_time_ms=response_time_ms,
                slow_threshold_ms=monitor.slow_threshold_ms,
                accepted_status_codes=monitor.accepted_status_codes,
            )
            error_type = None
            error_message = None
        except ValueError as exc:
            finished_at = datetime.now(UTC)
            run_status = CheckRunStatus.DOWN
            error_type = "blocked_target"
            error_message = str(exc)
            status_code = None
            response_time_ms = None
            dns_resolve_ms = None
            tcp_connect_ms = None
            tls_handshake_ms = None
            ttfb_ms = None
            final_url = None
            content_type = None
        except httpx.HTTPError as exc:
            finished_at = datetime.now(UTC)
            run_status, error_type = _map_http_exception(exc)
            error_message = str(exc)
            status_code = None
            response_time_ms = None
            dns_resolve_ms = None
            tcp_connect_ms = None
            tls_handshake_ms = None
            ttfb_ms = None
            final_url = None
            content_type = None

        if not _is_retryable_status(run_status) or attempt >= max_retries:
            break

    return {
        "probe_region": probe_region,
        "status": run_status,
        "started_at": started_at,
        "finished_at": finished_at,
        "response_time_ms": response_time_ms,
        "status_code": status_code,
        "error_type": error_type,
        "error_message": error_message,
        "final_url": final_url,
        "content_type": content_type,
        "dns_resolve_ms": dns_resolve_ms,
        "tcp_connect_ms": tcp_connect_ms,
        "tls_handshake_ms": tls_handshake_ms,
        "ttfb_ms": ttfb_ms,
        "retry_count": retry_count,
    }


@celery_app.task(name="app.workers.tasks.checks.check_http_monitor")
def check_http_monitor(monitor_id: str) -> str:
    asyncio.run(_check_http_monitor_async(monitor_id))
    return monitor_id


async def _check_http_monitor_async(monitor_id: str) -> None:
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Monitor).where(Monitor.id == monitor_id, Monitor.deleted_at.is_(None))
            )
            monitor = result.scalar_one_or_none()
            if monitor is None or monitor.is_paused:
                return

            monitor.current_status = MonitorStatus.CHECKING
            await session.flush()
            active_region = (monitor.active_region or "").strip().lower()
            if not active_region:
                raise RuntimeError(f"monitor {monitor.id} has no active_region configured")

            async with httpx.AsyncClient(follow_redirects=True) as client:
                primary_probe = await _perform_probe(
                    client=client,
                    monitor=monitor,
                    probe_region=active_region,
                    max_retries=monitor.max_retries,
                )

            check_run = CheckRun(
                monitor_id=monitor.id,
                status=primary_probe["status"],
                started_at=primary_probe["started_at"],
                finished_at=primary_probe["finished_at"],
                response_time_ms=primary_probe["response_time_ms"],
                status_code=primary_probe["status_code"],
                error_type=primary_probe["error_type"],
                error_message=primary_probe["error_message"],
                final_url=primary_probe["final_url"],
                content_type=primary_probe["content_type"],
                dns_resolve_ms=primary_probe["dns_resolve_ms"],
                tcp_connect_ms=primary_probe["tcp_connect_ms"],
                tls_handshake_ms=primary_probe["tls_handshake_ms"],
                ttfb_ms=primary_probe["ttfb_ms"],
                retry_count=primary_probe["retry_count"],
                probe_region=active_region,
            )
            session.add(check_run)
            await session.flush()
            status = primary_probe["status"]
            if not isinstance(status, CheckRunStatus):
                raise RuntimeError(f"monitor {monitor.id} check status is invalid")
            monitor.current_status = (
                MonitorStatus.DOWN
                if _is_probe_failure(status)
                else (MonitorStatus.SLOW if status == CheckRunStatus.SLOW else MonitorStatus.UP)
            )

            finished_at = primary_probe["finished_at"]
            response_time_ms = primary_probe["response_time_ms"]
            status_code = primary_probe["status_code"]
            error_type = primary_probe["error_type"]
            error_message = primary_probe["error_message"]
            monitor.last_checked_at = finished_at
            monitor.last_response_time_ms = response_time_ms
            monitor.last_status_code = status_code
            monitor.last_error_message = error_message
            if monitor.current_status in {MonitorStatus.UP, MonitorStatus.SLOW}:
                monitor.last_success_at = finished_at

            open_incident_row = await session.execute(
                select(Incident)
                .where(
                    Incident.monitor_id == monitor.id,
                    Incident.status == IncidentStatus.OPEN,
                )
                .order_by(Incident.opened_at.desc())
                .limit(1)
            )
            open_incident = open_incident_row.scalar_one_or_none()

            if monitor.current_status in {MonitorStatus.UP, MonitorStatus.SLOW}:
                if open_incident is not None:
                    open_incident.status = IncidentStatus.CLOSED
                    open_incident.closed_at = finished_at
                    open_incident.close_reason = "Recovered by successful check"
                    await session.flush()
                    send_incident_email.delay(
                        str(monitor.id),
                        str(open_incident.id),
                        "incident_recovered",
                    )
            else:
                if open_incident is None:
                    incident = Incident(
                        monitor_id=monitor.id,
                        opened_at=finished_at,
                        status=IncidentStatus.OPEN,
                        open_reason=error_message or (error_type or "check_failed"),
                        first_failed_check_id=check_run.id,
                        last_failed_check_id=check_run.id,
                    )
                    session.add(incident)
                    await session.flush()
                    send_incident_email.delay(
                        str(monitor.id),
                        str(incident.id),
                        "incident_opened",
                    )
                else:
                    open_incident.last_failed_check_id = check_run.id
                    if _should_send_still_down_alert(
                        incident=open_incident,
                        now=finished_at,
                        cooldown_minutes=settings.alert_cooldown_minutes,
                        reminder_minutes=settings.alert_still_down_reminder_minutes,
                        max_reminders=settings.alert_max_reminders_per_incident,
                    ):
                        send_incident_email.delay(
                            str(monitor.id),
                            str(open_incident.id),
                            "still_down",
                        )

            await session.commit()
    finally:
        # Celery on Windows can run tasks across short-lived loops; dispose pooled
        # asyncpg connections so we don't reuse transports tied to a closed loop.
        await engine.dispose()
