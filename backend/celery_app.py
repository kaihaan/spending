"""Celery application configuration for asynchronous task processing."""

from celery import Celery
from celery.signals import worker_process_init
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize Celery
celery_app = Celery(
    'spending_tasks',
    broker=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
)


@worker_process_init.connect
def init_worker_db_pool(**kwargs):
    """Reinitialize database connection pool after worker fork.

    PostgreSQL connections cannot be shared across forked processes.
    Each worker process needs its own fresh connection pool.
    """
    import database_postgres
    # Close existing pool if any
    if database_postgres.connection_pool is not None:
        try:
            database_postgres.connection_pool.closeall()
        except Exception:
            pass
        database_postgres.connection_pool = None
    # Initialize fresh pool for this worker
    database_postgres.init_pool()
    print(f"✓ Worker {os.getpid()} initialized fresh DB connection pool")

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1200,  # 20 minutes hard limit (allows long enrichment jobs)
    task_soft_time_limit=1140,  # 19 minutes soft limit (sends warning)
    result_expires=3600,  # Keep results for 1 hour
)

# Tasks are registered via @celery_app.task decorators in their respective modules
# Import tasks to ensure they're registered with Celery
try:
    from tasks import enrichment_tasks  # noqa: F401
except ImportError:
    pass

try:
    from tasks import gmail_tasks  # noqa: F401
except ImportError:
    pass

try:
    from tasks import matching_tasks  # noqa: F401
except ImportError:
    pass
