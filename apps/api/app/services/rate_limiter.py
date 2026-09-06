import time
import uuid
from typing import Optional
import redis
from app.core.config import settings

class RateLimiter:
    def __init__(self, redis_url: str = settings.REDIS_URL):
        self.r = redis.from_url(redis_url, decode_responses=True)
        # Load limits dynamically from settings
        self.global_concurrency = settings.GLOBAL_CONCURRENCY_LIMIT
        self.connection_concurrency = settings.CONCURRENT_JOBS_PER_CONNECTION
        self.pause_between_requests = settings.PAUSE_BETWEEN_REQUESTS_SECONDS

    def _get_paused_key(self, connection_id: uuid.UUID) -> str:
        return f"buffer:paused:{connection_id}"

    def _get_active_conn_key(self, connection_id: uuid.UUID) -> str:
        return f"buffer:active:conn:{connection_id}"

    def _get_active_global_key(self) -> str:
        return "buffer:active:global"

    def _get_last_req_key(self, connection_id: uuid.UUID) -> str:
        return f"buffer:last_req:{connection_id}"

    def pause_connection(self, connection_id: uuid.UUID, duration_seconds: int = 60) -> None:
        """
        Pauses a connection, typically triggered after receiving an HTTP 429 response.
        """
        key = self._get_paused_key(connection_id)
        self.r.setex(key, duration_seconds, "1")

    def is_connection_paused(self, connection_id: uuid.UUID) -> bool:
        """
        Checks if the connection is currently locked due to a rate limit pause.
        """
        key = self._get_paused_key(connection_id)
        return self.r.exists(key) > 0

    def get_pause_remaining(self, connection_id: uuid.UUID) -> int:
        """
        Returns the remaining pause time in seconds.
        """
        key = self._get_paused_key(connection_id)
        ttl = self.r.ttl(key)
        return max(0, ttl) if ttl is not None else 0

    def can_process(self, connection_id: uuid.UUID) -> bool:
        """
        Evaluate if a publication job can be immediately processed based on connection status,
        cooldown periods, and global concurrency.
        """
        # 1. Check if connection is paused (e.g. after HTTP 429)
        if self.is_connection_paused(connection_id):
            return False

        # 2. Check connection concurrency limits
        active_conn = int(self.r.get(self._get_active_conn_key(connection_id)) or 0)
        if active_conn >= self.connection_concurrency:
            return False

        # 3. Check global concurrency limits
        active_global = int(self.r.get(self._get_active_global_key()) or 0)
        if active_global >= self.global_concurrency:
            return False

        # 4. Check cooldown time elapsed since last request
        last_req = float(self.r.get(self._get_last_req_key(connection_id)) or 0.0)
        time_since_last = time.time() - last_req
        if time_since_last < self.pause_between_requests:
            return False

        return True

    def acquire_lock(self, connection_id: uuid.UUID) -> bool:
        """
        Atomically checks limits and increments active counters if available.
        Uses Redis pipeline to achieve concurrency checks.
        """
        # We run a check before lock
        if not self.can_process(connection_id):
            return False

        # We atomically increment the counters
        pipeline = self.r.pipeline()
        pipeline.incr(self._get_active_conn_key(connection_id))
        pipeline.incr(self._get_active_global_key())
        pipeline.execute()
        return True

    def release_lock(self, connection_id: uuid.UUID) -> None:
        """
        Decrements active counters and updates the last request timestamp.
        """
        pipeline = self.r.pipeline()
        # Decrement but keep >= 0
        active_conn = int(self.r.get(self._get_active_conn_key(connection_id)) or 0)
        if active_conn > 0:
            pipeline.decr(self._get_active_conn_key(connection_id))
            
        active_global = int(self.r.get(self._get_active_global_key()) or 0)
        if active_global > 0:
            pipeline.decr(self._get_active_global_key())

        # Set last request timestamp
        pipeline.set(self._get_last_req_key(connection_id), str(time.time()))
        pipeline.execute()

    def reset_all_counters(self) -> None:
        """
        Resets all active counters (e.g. on worker restarts).
        """
        keys = self.r.keys("buffer:active:*")
        if keys:
            self.r.delete(*keys)
