#!/bin/bash
# Start Celery worker for enrichment tasks

# Activate virtual environment
source /mnt/c/dev/spending/backend/venv/bin/activate

# Change to backend directory
cd /mnt/c/dev/spending/backend

# Start Celery worker
# -A: specify app module (celery_app)
# worker: run as worker mode
# --loglevel: set logging level
celery -A celery_app worker --loglevel=info
