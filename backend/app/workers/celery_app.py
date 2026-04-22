from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "moni",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks.ping",
        "app.workers.tasks.checks",
        "app.workers.tasks.notify",
        "app.workers.tasks.scheduler",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "enqueue-due-monitor-checks": {
        "task": "app.workers.tasks.scheduler.enqueue_due_monitor_checks",
        "schedule": 30.0,
    },
    "heartbeat-ping": {
        "task": "app.workers.tasks.ping.ping",
        "schedule": crontab(minute="*/5"),
    },
}
