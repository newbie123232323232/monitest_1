import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock


@dataclass
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, max_attempts: int, window_seconds: int) -> RateLimitResult:
        now = time.monotonic()
        with self._lock:
            bucket = self._events[key]
            cutoff = now - float(window_seconds)
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= max_attempts:
                retry_after = int(max(1, (bucket[0] + float(window_seconds)) - now))
                return RateLimitResult(allowed=False, retry_after_seconds=retry_after)
            bucket.append(now)
            return RateLimitResult(allowed=True, retry_after_seconds=0)


auth_rate_limiter = InMemoryRateLimiter()
