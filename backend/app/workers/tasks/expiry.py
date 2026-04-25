import asyncio
import socket
import ssl
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import select

from app.core.database import AsyncSessionLocal, engine
from app.models.monitor import Monitor
from app.models.monitor_expiry import MonitorExpiryStatus
from app.workers.celery_app import celery_app
from app.workers.tasks.notify import send_incident_email

EXPIRY_ALERT_THRESHOLDS = (30, 14, 7, 1)


def _state_from_days(days_left: int | None) -> str:
    if days_left is None:
        return "unknown"
    if days_left < 0:
        return "expired"
    if days_left <= 1:
        return "warn_1d"
    if days_left <= 7:
        return "warn_7d"
    if days_left <= 14:
        return "warn_14d"
    if days_left <= 30:
        return "warn_30d"
    return "ok"


def _parse_thresholds(raw: str | None) -> set[int]:
    if not raw:
        return set()
    out: set[int] = set()
    for part in raw.split(","):
        p = part.strip()
        if not p:
            continue
        if p.isdigit():
            out.add(int(p))
    return out


def _serialize_thresholds(values: set[int]) -> str:
    if not values:
        return ""
    return ",".join(str(v) for v in sorted(values, reverse=True))


def _next_threshold_to_alert(days_left: int | None, sent: set[int]) -> int | None:
    if days_left is None or days_left < 0:
        return None
    for threshold in reversed(EXPIRY_ALERT_THRESHOLDS):
        if days_left <= threshold and threshold not in sent:
            return threshold
    return None


def _fetch_ssl_expiry(url: str, timeout: int = 10) -> datetime:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if not host:
        raise ValueError("invalid host")
    if parsed.scheme != "https":
        raise ValueError("ssl check requires https")
    port = parsed.port or 443
    ctx = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ssock:
            cert = ssock.getpeercert()
    not_after = cert.get("notAfter")
    if not not_after:
        raise ValueError("missing certificate expiry")
    dt = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
    return dt


def _extract_domain(url: str) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("invalid host")
    return host


def _normalize_whois_expiration(raw: object) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        values = [_normalize_whois_expiration(item) for item in raw]
        values = [v for v in values if v is not None]
        if not values:
            return None
        return max(values)
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=UTC)
        return raw.astimezone(UTC)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        # Common WHOIS date formats.
        for fmt in (
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%d-%b-%Y",
        ):
            try:
                parsed = datetime.strptime(text, fmt)
                return parsed.replace(tzinfo=UTC)
            except ValueError:
                continue
    return None


def _fetch_domain_expiry(url: str) -> datetime:
    try:
        import whois  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("python-whois dependency is not installed") from exc
    domain = _extract_domain(url)
    info = whois.whois(domain)
    expiration_raw = getattr(info, "expiration_date", None)
    expires_at = _normalize_whois_expiration(expiration_raw)
    if expires_at is None:
        raise ValueError("domain expiration not found in WHOIS")
    return expires_at


@celery_app.task(name="app.workers.tasks.expiry.check_monitor_expiry")
def check_monitor_expiry(monitor_id: str) -> str:
    asyncio.run(_check_monitor_expiry_async(monitor_id))
    return monitor_id


@celery_app.task(name="app.workers.tasks.expiry.check_expiry_for_all_http_monitors")
def check_expiry_for_all_http_monitors() -> int:
    return asyncio.run(_check_expiry_for_all_http_monitors_async())


async def _check_expiry_for_all_http_monitors_async() -> int:
    async with AsyncSessionLocal() as session:
        rows = await session.execute(select(Monitor.id).where(Monitor.deleted_at.is_(None), Monitor.is_paused.is_(False)))
        monitor_ids = [str(mid) for (mid,) in rows.all()]
    # Run inline to avoid nested-queue fanout; this keeps periodic expiry checks
    # deterministic even when the main Celery queue is under pressure.
    for mid in monitor_ids:
        await _check_monitor_expiry_async(mid)
    return len(monitor_ids)


async def _check_monitor_expiry_async(monitor_id: str) -> None:
    try:
        async with AsyncSessionLocal() as session:
            row = await session.execute(select(Monitor).where(Monitor.id == monitor_id, Monitor.deleted_at.is_(None)))
            monitor = row.scalar_one_or_none()
            if monitor is None:
                return

            now = datetime.now(UTC)
            ssl_expires_at: datetime | None = None
            ssl_days_left: int | None = None
            ssl_state = "unknown"
            domain_expires_at: datetime | None = None
            domain_days_left: int | None = None
            domain_state = "unknown"
            last_error: str | None = None

            try:
                ssl_expires_at = _fetch_ssl_expiry(monitor.url, timeout=max(1, monitor.timeout_seconds))
                ssl_days_left = (ssl_expires_at.date() - now.date()).days
                ssl_state = _state_from_days(ssl_days_left)
            except Exception as exc:  # noqa: BLE001
                last_error = f"ssl: {exc}"
                ssl_state = "unknown"

            try:
                domain_expires_at = _fetch_domain_expiry(monitor.url)
                domain_days_left = (domain_expires_at.date() - now.date()).days
                domain_state = _state_from_days(domain_days_left)
            except Exception as exc:  # noqa: BLE001
                err = f"domain: {exc}"
                last_error = f"{last_error} | {err}" if last_error else err
                domain_state = "unknown"

            status = await session.get(MonitorExpiryStatus, monitor.id)
            if status is None:
                status = MonitorExpiryStatus(monitor_id=monitor.id)
                session.add(status)
            previous_ssl_expires_at = status.ssl_expires_at
            sent_ssl_thresholds = _parse_thresholds(status.ssl_alerted_thresholds)
            previous_domain_expires_at = status.domain_expires_at
            sent_domain_thresholds = _parse_thresholds(status.domain_alerted_thresholds)

            # If certificate appears renewed to a later expiry date, reset threshold tracking.
            if (
                previous_ssl_expires_at is not None
                and ssl_expires_at is not None
                and ssl_expires_at > previous_ssl_expires_at
            ):
                sent_ssl_thresholds.clear()

            threshold = _next_threshold_to_alert(ssl_days_left, sent_ssl_thresholds)
            if threshold is not None:
                send_incident_email.delay(str(monitor.id), None, "ssl_expiry_warning")
                sent_ssl_thresholds.add(threshold)

            if (
                previous_domain_expires_at is not None
                and domain_expires_at is not None
                and domain_expires_at > previous_domain_expires_at
            ):
                sent_domain_thresholds.clear()
            domain_threshold = _next_threshold_to_alert(domain_days_left, sent_domain_thresholds)
            if domain_threshold is not None:
                send_incident_email.delay(str(monitor.id), None, "domain_expiry_warning")
                sent_domain_thresholds.add(domain_threshold)

            status.ssl_expires_at = ssl_expires_at
            status.ssl_days_left = ssl_days_left
            status.ssl_state = ssl_state
            status.ssl_alerted_thresholds = _serialize_thresholds(sent_ssl_thresholds)
            status.domain_expires_at = domain_expires_at
            status.domain_days_left = domain_days_left
            status.domain_state = domain_state
            status.domain_alerted_thresholds = _serialize_thresholds(sent_domain_thresholds)
            status.last_checked_at = now
            status.last_error = last_error
            await session.commit()
    finally:
        await engine.dispose()
