# Suggested Commands - Personal Spending App Backend

## Environment Setup
```bash
# Activate virtual environment (ALWAYS do this first!)
source ./venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Running the Application

### Docker (Recommended)
```bash
# Start all services (backend, frontend, postgres, redis, celery, minio)
docker-compose up -d

# View logs for specific service
docker-compose logs -f backend
docker-compose logs -f celery
docker-compose logs -f frontend

# Restart after code changes
docker-compose restart backend  # Auto-reloads via volume mounts
docker-compose restart frontend  # Auto-reloads via volume mounts

# Rebuild Celery after code changes (CRITICAL - restart alone won't work!)
docker-compose build celery && docker-compose up -d celery

# Stop all services
docker-compose down
```

### Local Development (Legacy)
```bash
# Backend (requires Docker postgres/redis/minio still running)
source ./venv/bin/activate
export DB_TYPE=postgres
python3 app.py  # http://localhost:5000

# Frontend (in separate terminal)
cd ../frontend
npm run dev  # http://localhost:5173
```

## Code Quality

```bash
# Linting with Ruff
ruff check .
ruff check --fix .  # Auto-fix issues

# Type checking with Pyright
pyright

# Format code with Ruff
ruff format .
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_models/test_user.py

# Run MCP server tests
pytest backend/mcp_server/tests/
```

## Database Operations

```bash
# PostgreSQL shell (Docker)
docker exec -it spending-postgres psql -U spending_user -d spending_db

# Backup database
docker exec spending-postgres pg_dump -U spending_user spending_db > backup.sql

# Check database password (NEVER assume defaults!)
grep DB_PASSWORD .env
```

## Git Commands

```bash
# Standard workflow
git status
git add .
git commit -m "message"
git push

# View recent commits
git log --oneline -10
```

## Utility Commands (Linux)

```bash
# IMPORTANT: Use python3 NOT python
python3 --version
python3 script.py

# File operations
ls -la
find . -name "*.py" -type f
grep -r "pattern" --include="*.py"
```

## Service Ports (Non-Standard!)

- PostgreSQL: **5433** (NOT 5432)
- Redis: **6380** (NOT 6379)
- MinIO API: **9000**
- MinIO Console: **9001**
- Flask Backend: **5000**
- Vite Frontend: **5173**
