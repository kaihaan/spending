"""Celery application configuration for asynchronous task processing."""

from celery import Celery
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

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes hard limit per task
    task_soft_time_limit=270,  # 4.5 minutes soft limit (sends warning)
    result_expires=3600,  # Keep results for 1 hour
)

# Register tasks
from tasks import enrichment_tasks

# Decorate the task function
celery_app.task(bind=True)(enrichment_tasks.enrich_transactions_task)
