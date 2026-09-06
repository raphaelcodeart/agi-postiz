from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery = Celery(
    "social_publisher",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

# Celery Configurations
celery.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True, # Ack after execution to prevent lost tasks
    worker_prefetch_multiplier=1, # Prefetch 1 task at a time for fair rate-limited dispatch
)

# Autodiscover tasks
celery.conf.imports = (
    "app.tasks.media",
    "app.tasks.sync",
    "app.tasks.publication",
    "app.tasks.cleanup",
    "app.tasks.blog_writer",
    "app.tasks.omnichannel",
    "app.tasks.statistics",
)

# Celery Beat Periodic Scheduling Config
celery.conf.beat_schedule = {
    "run-stale-publications-recovery-every-5m": {
        "task": "app.tasks.cleanup.recover_stale_publications",
        "schedule": 300.0, # Every 5 minutes
    },
    "run-media-retention-cleanup-daily": {
        "task": "app.tasks.cleanup.media_retention_cleanup",
        "schedule": crontab(hour=2, minute=0), # Daily at 2:00 AM UTC
    },
    "refresh-expired-buffer-tokens-hourly": {
        "task": "app.tasks.sync.refresh_expired_tokens",
        "schedule": crontab(minute=0), # Every hour
    },
    "sync-all-buffer-connections-every-4h": {
        "task": "app.tasks.sync.sync_all_buffer_connections",
        "schedule": crontab(minute=15, hour="*/4"), # Every 4 hours, offset from the hourly job above
    },
    "poll-scheduled-campaign-launches-every-30s": {
        "task": "app.tasks.publication.poll_and_queue_scheduled_publications",
        "schedule": 30.0, # Every 30 seconds
    },
    "poll-gmail-channels-every-2m": {
        "task": "app.tasks.omnichannel.poll_gmail_channels_task",
        "schedule": 120.0, # Every 2 minutes - Gmail has no inbound webhook, see connectors/gmail.py
    }
}
