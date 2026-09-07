"""
Publication pacing.

The distinction these tests pin down: the provider scope answers "are we
hammering the upstream API?", the channel cooldown answers "is this one profile
posting like a bot?". They are different questions and only the second protects
a promoter's account - what a platform sees is the frequency of ONE profile, not
our aggregate throughput.

The distinction became load-bearing with a shared-quota provider: every
bundle.social channel sits behind a single provider scope, so without a separate
per-channel guard nothing would stop two campaigns from posting twice on the
same profile seconds apart.
"""
import time
import uuid

import pytest

from app.core.config import settings
from app.services.rate_limiter import RateLimiter


@pytest.fixture
def limiter():
    """
    A limiter with no history.

    reset_all_counters clears the in-flight counters but deliberately NOT the
    cooldown timestamps - those must survive a worker restart, or restarting a
    worker would become a way to bypass pacing. Tests therefore clear them
    explicitly rather than relying on that method.
    """
    rl = RateLimiter()
    rl.reset_all_counters()
    stale = rl.r.keys("publish:last_req:*") + rl.r.keys("publish:last_post:*")
    if stale:
        rl.r.delete(*stale)
    return rl


def test_a_channel_is_spaced_after_it_receives_a_post(limiter):
    channel = uuid.uuid4()
    scope = "provider:bundle_social"

    assert limiter.channel_cooldown_remaining(channel) == 0

    limiter.acquire_lock(scope, channel_id=channel)
    limiter.release_lock(scope, channel_id=channel)

    remaining = limiter.channel_cooldown_remaining(channel)
    assert remaining > 0
    assert remaining <= settings.MIN_SECONDS_BETWEEN_POSTS_PER_CHANNEL


def test_the_same_channel_cannot_be_posted_to_again_immediately(limiter):
    """The scenario that would look like a bot on the promoter's own profile."""
    channel = uuid.uuid4()
    scope = "provider:bundle_social"

    limiter.acquire_lock(scope, channel_id=channel)
    limiter.release_lock(scope, channel_id=channel)

    assert limiter.can_process(scope, channel_id=channel) is False


def test_a_different_channel_is_not_blocked_by_another_ones_cooldown(limiter):
    """
    300 promoters each receiving one post is normal behaviour, and must stay
    fast: the per-channel guard must not turn into a global serializer.
    """
    busy = uuid.uuid4()
    other = uuid.uuid4()
    scope = "provider:bundle_social"

    limiter.acquire_lock(scope, channel_id=busy)
    limiter.release_lock(scope, channel_id=busy)

    # Only the provider cooldown stands between them, never the busy channel's.
    assert limiter.channel_cooldown_remaining(other) == 0


def test_cooldown_reports_the_wait_so_the_job_can_requeue_past_it(limiter):
    """
    The task re-queues using this number. Without it a blocked publication would
    retry every 15 seconds for the whole window, burning worker slots that other
    publications need.
    """
    channel = uuid.uuid4()
    limiter.acquire_lock("provider:bundle_social", channel_id=channel)
    limiter.release_lock("provider:bundle_social", channel_id=channel)

    wait = limiter.channel_cooldown_remaining(channel)
    assert wait >= settings.MIN_SECONDS_BETWEEN_POSTS_PER_CHANNEL - 5


def test_pacing_without_a_channel_is_unchanged(limiter):
    """
    Buffer call sites that name no channel must behave exactly as before: the
    per-channel guard is additive, not a change to the existing contract.
    """
    scope = f"conn:{uuid.uuid4()}"
    assert limiter.can_process(scope) is True
    assert limiter.acquire_lock(scope) is True
    limiter.release_lock(scope)


def test_provider_cooldown_still_applies_across_channels(limiter):
    """
    Different channels are still paced against each other by the provider
    cooldown - that is what stops hundreds of accounts publishing the same
    content inside the same few seconds.
    """
    scope = "provider:bundle_social"
    a, b = uuid.uuid4(), uuid.uuid4()

    assert limiter.acquire_lock(scope, channel_id=a) is True
    limiter.release_lock(scope, channel_id=a)

    # b's own cooldown is clear, but the provider just made a request.
    assert limiter.channel_cooldown_remaining(b) == 0
    assert limiter.can_process(scope, channel_id=b) is False
