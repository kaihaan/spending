# Python backend image for Flask app and Celery worker
# Using Python 3.12 as required by the codebase (multiline f-string support)
FROM python:3.12-slim-bookworm

WORKDIR /app

# Install system dependencies including explicit OpenSSL for Gmail API compatibility
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    ca-certificates \
    openssl \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Ensure unbuffered Python output for proper logging
ENV PYTHONUNBUFFERED=1

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Default command for Celery worker
CMD ["celery", "-A", "celery_app", "worker", "--loglevel=info"]
