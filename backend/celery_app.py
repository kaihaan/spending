"""Celery application configuration for asynchronous task processing."""

import contextlib
import os

from celery import Celery
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize Celery
celery_app = Celery(
    "spending_tasks",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
)

# Note: SQLAlchemy manages its own connection pool automatically.
# No manual pool initialization needed for Celery workers.

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1200,  # 20 minutes hard limit (allows long enrichment jobs)
    task_soft_time_limit=1140,  # 19 minutes soft limit (sends warning)
    result_expires=3600,  # Keep results for 1 hour
)

# Tasks are registered via @celery_app.task decorators in their respective modules
# Import tasks to ensure they're registered with Celery
with contextlib.suppress(ImportError):
    from tasks import enrichment_tasks  # noqa: F401

with contextlib.suppress(ImportError):
    from tasks import gmail_tasks  # noqa: F401

with contextlib.suppress(ImportError):
    from tasks import matching_tasks  # noqa: F401

with contextlib.suppress(ImportError):
    from tasks import truelayer_tasks  # noqa: F401
