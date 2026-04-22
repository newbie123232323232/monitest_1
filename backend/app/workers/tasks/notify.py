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
        await session.commit()
