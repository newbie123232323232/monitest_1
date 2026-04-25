from datetime import UTC, datetime

import redis

from app.core.config import settings
from app.workers.celery_app import celery_app

_BEAT_HEARTBEAT_KEY = "moni:runtime:beat:last_seen_at"
_WORKER_HEARTBEAT_KEY = "moni:runtime:worker:last_seen_at"


@celery_app.task(name="app.workers.tasks.ping.ping")
def ping() -> str:
    # Beat schedules this task periodically; worker execution proves both beat enqueue and worker consume path.
    client = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1.5,
        socket_timeout=1.5,
    )
    try:
        now_iso = datetime.now(UTC).isoformat()
        client.set(_BEAT_HEARTBEAT_KEY, now_iso, ex=3600)
        client.set(_WORKER_HEARTBEAT_KEY, now_iso, ex=3600)
    finally:
        client.close()
    return "pong"
