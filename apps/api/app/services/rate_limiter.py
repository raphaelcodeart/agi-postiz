import random
import time
import uuid
from typing import Optional, Union
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

    def _get_channel_last_post_key(self, channel_id: Scope) -> str:
        return f"publish:last_post:channel:{channel_id}"

    def channel_cooldown_remaining(self, channel_id: Scope) -> int:
        """
        Seconds before this specific channel may receive another post.

        This is the guard that protects the promoter's own account, and it is
        separate from the provider quota on purpose. The two answer different
        questions:

          provider scope -> "are we hammering the upstream API?"
          channel        -> "is this one profile posting like a bot?"

        A shared-quota provider makes the distinction essential: every channel
        sits behind one provider scope, so without this nothing at all would stop
        two campaigns from posting twice on the same profile seconds apart. What
        a platform sees is per-account frequency, not our aggregate throughput.
        """
        minimum = settings.MIN_SECONDS_BETWEEN_POSTS_PER_CHANNEL
        if minimum <= 0:
            return 0

        last_post = float(self.r.get(self._get_channel_last_post_key(channel_id)) or 0.0)
        if last_post <= 0:
            return 0

        elapsed = time.time() - last_post
        return max(0, int(minimum - elapsed))

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

    def can_process(self, scope: Scope, channel_id: Optional[Scope] = None) -> bool:
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

        # 4. Check cooldown time elapsed since last request.
        # Jittered: a request landing on exactly the same interval every time is
        # itself a machine signature. A few seconds of randomness costs nothing
        # and makes the cadence irregular, which is what organic traffic is.
        last_req = float(self.r.get(self._get_last_req_key(scope_key)) or 0.0)
        required = self.pause_between_requests + random.uniform(0, settings.PAUSE_JITTER_SECONDS)
        if time.time() - last_req < required:
            return False

        # 5. Per-channel spacing, when a channel was named.
        if channel_id is not None and self.channel_cooldown_remaining(channel_id) > 0:
            return False

        return True

    def acquire_lock(self, scope: Scope, channel_id: Optional[Scope] = None) -> bool:
        """
        Atomically checks limits and increments active counters if available.
        Uses Redis pipeline to achieve concurrency checks.
        """
        scope_key = self._normalize(scope)

        # We run a check before lock
        if not self.can_process(scope_key, channel_id):
            return False

        # We atomically increment the counters
        pipeline = self.r.pipeline()
        pipeline.incr(self._get_active_scope_key(scope_key))
        pipeline.incr(self._get_active_global_key())
        pipeline.execute()
        return True

    def release_lock(self, scope: Scope, channel_id: Optional[Scope] = None) -> None:
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
        now = str(time.time())
        pipeline.set(self._get_last_req_key(scope_key), now)
        if channel_id is not None:
            # Recorded on release, not acquire: what matters is when the post
            # actually went out. Kept a little beyond the window so a stale key
            # cannot pin a channel forever if a worker dies mid-flight.
            pipeline.setex(
                self._get_channel_last_post_key(channel_id),
                max(60, settings.MIN_SECONDS_BETWEEN_POSTS_PER_CHANNEL * 2),
                now,
            )
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
