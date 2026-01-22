"""Celery application configuration."""

from celery import Celery

from app.core.config import settings

# Create Celery app
celery_app = Celery(
    "himalayan_fibers",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,

    # Task routing
    task_routes={
        "app.workers.tasks.send_welcome_email": {"queue": "emails"},
        "app.workers.tasks.send_cart_abandoned_email": {"queue": "emails"},
        "app.workers.tasks.send_shipping_update_email": {"queue": "emails"},
        "app.workers.tasks.send_campaign": {"queue": "campaigns"},
        "app.workers.tasks.generate_content": {"queue": "content"},
    },

    # Rate limiting
    task_annotations={
        "app.workers.tasks.send_welcome_email": {"rate_limit": "20/m"},
        "app.workers.tasks.send_cart_abandoned_email": {"rate_limit": "20/m"},
        "app.workers.tasks.send_campaign": {"rate_limit": "1/m"},
    },

    # Retry settings
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,

    # Result settings
    result_expires=86400,  # 24 hours

    # Beat schedule for periodic tasks
    beat_schedule={
        "process-scheduled-campaigns": {
            "task": "app.workers.tasks.process_scheduled_campaigns",
            "schedule": 60.0,  # Every minute
        },
        "cleanup-old-webhook-events": {
            "task": "app.workers.tasks.cleanup_old_webhook_events",
            "schedule": 86400.0,  # Every 24 hours
        },
    },
)
