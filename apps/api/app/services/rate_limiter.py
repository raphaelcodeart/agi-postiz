import time
import uuid
from typing import Union
import redis
from app.core.config import settings
from app.integrations.providers import PROVIDER_BUNDLE_SOCIAL

# A scope is the key under which concurrency and cooldown are enforced. It used
# to be implicitly the connection id, which was correct while Buffer was the
# only provider: every user carries their own API key, so every connection has
# its own upstream quota.
#
# That assumption breaks with a multi-tenant provider. On bundle.social all
# connections go out under ONE platform key, so they share ONE quota: 3.000
# channels are a single queue, not 3.000 independent ones. Scoping there by
# connection would let the worker fire thousands of concurrent calls that
# upstream counts against the same limit, and the whole campaign would be
# throttled or rejected at once.
#
# So the scope is supplied by the caller (``ProviderContext.rate_limit_scope``,
# built in integrations/providers.py):
#   Buffer         -> "conn:<connection_id>"    one quota per user
#   bundle.social  -> "provider:bundle_social"  one quota shared by everyone
Scope = Union[str, uuid.UUID]


class RateLimiter:
    def __init__(self, redis_url: str = settings.REDIS_URL):
        self.r = redis.from_url(redis_url, decode_responses=True)
        # Load limits dynamically from settings
        self.global_concurrency = settings.GLOBAL_CONCURRENCY_LIMIT
        self.connection_concurrency = settings.CONCURRENT_JOBS_PER_CONNECTION
        self.pause_between_requests = settings.PAUSE_BETWEEN_REQUESTS_SECONDS

    @staticmethod
    def _normalize(scope: Scope) -> str:
        """
        Accept a bare connection id as before, or an explicit scope string.

        Callers that predate the provider split keep working unchanged: a UUID
        is read as the Buffer per-connection scope it always was.
        """
        if isinstance(scope, uuid.UUID):
            return f"conn:{scope}"
        return str(scope)

    def _concurrency_limit_for(self, scope: str) -> int:
        """
        How many jobs may run at once under this scope.

        A shared-quota provider needs its own ceiling: the per-connection limit
        is meant to be multiplied across many users, so reusing it for a scope
        that ALL users share would be far too permissive.
        """
        if scope == f"provider:{PROVIDER_BUNDLE_SOCIAL}":
            return settings.BUNDLE_SOCIAL_CONCURRENCY_LIMIT
        return self.connection_concurrency

    def _get_paused_key(self, scope: str) -> str:
        return f"publish:paused:{scope}"

    def _get_active_scope_key(self, scope: str) -> str:
        return f"publish:active:{scope}"

    def _get_active_global_key(self) -> str:
        return "publish:active:global"

    def _get_last_req_key(self, scope: str) -> str:
        return f"publish:last_req:{scope}"

    def pause_connection(self, scope: Scope, duration_seconds: int = 60) -> None:
        """
        Pauses a scope, typically triggered after receiving an HTTP 429.

        For a shared-quota provider this deliberately pauses EVERY connection of
        that provider: upstream rejected us as a platform, not one user, so
        retrying other users immediately would only collect more 429s.
        """
        key = self._get_paused_key(self._normalize(scope))
        self.r.setex(key, duration_seconds, "1")

    def is_connection_paused(self, scope: Scope) -> bool:
        """Checks if the scope is currently locked due to a rate limit pause."""
        key = self._get_paused_key(self._normalize(scope))
        return self.r.exists(key) > 0

    def get_pause_remaining(self, scope: Scope) -> int:
        """Returns the remaining pause time in seconds."""
        key = self._get_paused_key(self._normalize(scope))
        ttl = self.r.ttl(key)
        return max(0, ttl) if ttl is not None else 0

    def can_process(self, scope: Scope) -> bool:
        """
        Evaluate if a publication job can be immediately processed based on scope
        status, cooldown periods, and global concurrency.
        """
        scope_key = self._normalize(scope)

        # 1. Check if the scope is paused (e.g. after HTTP 429)
        if self.is_connection_paused(scope_key):
            return False

        # 2. Check per-scope concurrency limits
        active_scope = int(self.r.get(self._get_active_scope_key(scope_key)) or 0)
        if active_scope >= self._concurrency_limit_for(scope_key):
            return False

        # 3. Check global concurrency limits
        active_global = int(self.r.get(self._get_active_global_key()) or 0)
        if active_global >= self.global_concurrency:
            return False

        # 4. Check cooldown time elapsed since last request
        last_req = float(self.r.get(self._get_last_req_key(scope_key)) or 0.0)
        time_since_last = time.time() - last_req
        if time_since_last < self.pause_between_requests:
            return False

        return True

    def acquire_lock(self, scope: Scope) -> bool:
        """
        Atomically checks limits and increments active counters if available.
        Uses Redis pipeline to achieve concurrency checks.
        """
        scope_key = self._normalize(scope)

        # We run a check before lock
        if not self.can_process(scope_key):
            return False

        # We atomically increment the counters
        pipeline = self.r.pipeline()
        pipeline.incr(self._get_active_scope_key(scope_key))
        pipeline.incr(self._get_active_global_key())
        pipeline.execute()
        return True

    def release_lock(self, scope: Scope) -> None:
        """
        Decrements active counters and updates the last request timestamp.
        """
        scope_key = self._normalize(scope)

        pipeline = self.r.pipeline()
        # Decrement but keep >= 0
        active_scope = int(self.r.get(self._get_active_scope_key(scope_key)) or 0)
        if active_scope > 0:
            pipeline.decr(self._get_active_scope_key(scope_key))

        active_global = int(self.r.get(self._get_active_global_key()) or 0)
        if active_global > 0:
            pipeline.decr(self._get_active_global_key())

        # Set last request timestamp
        pipeline.set(self._get_last_req_key(scope_key), str(time.time()))
        pipeline.execute()

    def reset_all_counters(self) -> None:
        """
        Resets all active counters (e.g. on worker restarts).

        Clears the legacy ``buffer:active:*`` keys too, so a worker restarting
        across this change does not leave stale counters pinned forever.
        """
        keys = self.r.keys("publish:active:*") + self.r.keys("buffer:active:*")
        if keys:
            self.r.delete(*keys)
