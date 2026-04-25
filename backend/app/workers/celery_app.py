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
        "app.workers.tasks.expiry",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_pool_limit=settings.celery_broker_pool_limit,
    broker_heartbeat=settings.celery_broker_heartbeat_seconds,
    broker_connection_retry_on_startup=settings.celery_broker_retry_on_startup,
    worker_prefetch_multiplier=settings.celery_worker_prefetch_multiplier,
    broker_transport_options={
        "health_check_interval": settings.celery_broker_health_check_interval_seconds,
    },
)

celery_app.conf.beat_schedule = {
    "enqueue-due-monitor-checks": {
        "task": "app.workers.tasks.scheduler.enqueue_due_monitor_checks",
        "schedule": 30.0,
    },
    "heartbeat-ping": {
        "task": "app.workers.tasks.ping.ping",
        "schedule": 30.0,
    },
    "check-expiry-status": {
        "task": "app.workers.tasks.expiry.check_expiry_for_all_http_monitors",
        "schedule": crontab(minute="*/30"),
    },
}
