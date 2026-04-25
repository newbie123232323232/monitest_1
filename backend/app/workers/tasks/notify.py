from datetime import UTC, datetime

from app.core.database import AsyncSessionLocal
from app.integrations.mail import send_email_sync
from app.models.monitor import AlertChannel, AlertEvent, AlertEventType, AlertSendStatus, Incident, Monitor
from app.models.user import User
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.notify.send_incident_email")
def send_incident_email(monitor_id: str, incident_id: str | None, event_type: str) -> None:
    import asyncio

    asyncio.run(_send_incident_email_async(monitor_id, incident_id, event_type))


async def _send_incident_email_async(monitor_id: str, incident_id: str | None, event_type: str) -> None:
    async with AsyncSessionLocal() as session:
        monitor = await session.get(Monitor, monitor_id)
        if monitor is None:
            return
        user = await session.get(User, monitor.user_id)
        if user is None:
            return

        incident = await session.get(Incident, incident_id) if incident_id else None
        event_enum = AlertEventType(event_type)
        sent_at = datetime.now(UTC)
        send_status = AlertSendStatus.SENT
        error_message: str | None = None

        if event_enum == AlertEventType.INCIDENT_OPENED:
            subject = f"[MONI] DOWN: {monitor.name}"
            body = (
                f"Monitor: {monitor.name}\n"
                f"URL: {monitor.url}\n"
                f"Status: DOWN\n"
                f"Checked at: {monitor.last_checked_at}\n"
                f"Error: {monitor.last_error_message or 'N/A'}\n"
            )
        elif event_enum == AlertEventType.INCIDENT_RECOVERED:
            subject = f"[MONI] RECOVERED: {monitor.name}"
            body = (
                f"Monitor: {monitor.name}\n"
                f"URL: {monitor.url}\n"
                f"Status: UP\n"
                f"Checked at: {monitor.last_checked_at}\n"
                f"Response time: {monitor.last_response_time_ms} ms\n"
            )
        elif event_enum == AlertEventType.STILL_DOWN:
            subject = f"[MONI] STILL DOWN: {monitor.name}"
            body = (
                f"Monitor: {monitor.name}\n"
                f"URL: {monitor.url}\n"
                f"Status: DOWN (ongoing incident)\n"
                f"Checked at: {monitor.last_checked_at}\n"
                f"Last error: {monitor.last_error_message or 'N/A'}\n"
                f"Reminder count: {(incident.reminder_count if incident else 0) + 1}\n"
            )
        elif event_enum == AlertEventType.SSL_EXPIRY_WARNING:
            subject = f"[MONI] SSL EXPIRY WARNING: {monitor.name}"
            body = (
                f"Monitor: {monitor.name}\n"
                f"URL: {monitor.url}\n"
                f"Event: SSL expiry threshold reached\n"
                f"Checked at: {monitor.last_checked_at}\n"
                f"Please review certificate renewal timeline.\n"
            )
        elif event_enum == AlertEventType.DOMAIN_EXPIRY_WARNING:
            subject = f"[MONI] DOMAIN EXPIRY WARNING: {monitor.name}"
            body = (
                f"Monitor: {monitor.name}\n"
                f"URL: {monitor.url}\n"
                f"Event: Domain expiry threshold reached\n"
                f"Checked at: {monitor.last_checked_at}\n"
                f"Please review domain renewal timeline.\n"
            )
        else:
            subject = f"[MONI] STATUS UPDATE: {monitor.name}"
            body = f"Monitor {monitor.name} event {event_type}"

        try:
            send_email_sync(subject, user.email, body)
        except Exception as exc:  # noqa: BLE001
            send_status = AlertSendStatus.FAILED
            error_message = str(exc)

        session.add(
            AlertEvent(
                incident_id=incident.id if incident else None,
                monitor_id=monitor.id,
                channel=AlertChannel.EMAIL,
                event_type=event_enum,
                sent_to=user.email,
                sent_at=sent_at,
                send_status=send_status,
                error_message=error_message,
            )
        )
        if incident is not None:
            if event_enum == AlertEventType.INCIDENT_OPENED:
                incident.last_alert_sent_at = sent_at
                incident.reminder_count = 0
            elif event_enum == AlertEventType.STILL_DOWN:
                incident.last_alert_sent_at = sent_at
                incident.reminder_count = (incident.reminder_count or 0) + 1
        await session.commit()
