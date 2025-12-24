Start the full development environment for the spending app.
Ports are loaded from .env file.

## Arguments
- No arguments: Start all services
- `restart backend`: Kill and restart the backend server
- `restart frontend`: Kill and restart the frontend dev server
- `restart celery`: Restart the Celery Docker container
- `restart all`: Restart all services

## Restart Commands
To restart a service, first kill it, then start it:

### Restart Backend
```bash
set -a && source .env && set +a && lsof -i :${BACKEND_PORT:-5000} -t 2>/dev/null | xargs -r kill && sleep 1
```
Then run the backend start command with `run_in_background: true`

### Restart Frontend
```bash
set -a && source .env && set +a && lsof -i :${FRONTEND_PORT:-5173} -t 2>/dev/null | xargs -r kill && sleep 1
```
Then run the frontend start command with `run_in_background: true`

### Restart Celery (Docker)
```bash
docker-compose restart celery
```

## Steps to execute:

### 1. Load environment variables
```bash
set -a && source .env && set +a && echo "Ports: Backend=$BACKEND_PORT, Frontend=$FRONTEND_PORT, Postgres=$POSTGRES_PORT, Redis=$REDIS_PORT"
```

### 2. Start Docker services
```bash
docker-compose up -d
```

### 3. Launch Backend (if not running)
Check if running:
```bash
set -a && source .env && set +a && lsof -i :$BACKEND_PORT -t >/dev/null 2>&1 && echo "Backend already running on port $BACKEND_PORT" || echo "NEEDS_START"
```
If NEEDS_START, run with `run_in_background: true`:
```bash
cd backend && source venv/bin/activate && DB_TYPE=postgres python app.py
```

### 4. Launch Frontend (if not running)
**Permission: REQUIRES APPROVAL** (background npm process)
Check if running:
```bash
set -a && source .env && set +a && lsof -i :$FRONTEND_PORT -t >/dev/null 2>&1 && echo "Frontend already running on port $FRONTEND_PORT" || echo "NEEDS_START"
```
If NEEDS_START, run with `run_in_background: true`:
```bash
cd frontend && npm run dev
```

## Service URLs
After starting, access:
- Frontend: http://localhost:$FRONTEND_PORT
- Backend: http://localhost:$BACKEND_PORT
- PostgreSQL: localhost:$POSTGRES_PORT
- Redis: localhost:$REDIS_PORT
