Check the health status of all required services for the spending app.
Reports on: Docker containers, PostgreSQL, Redis, Backend API, Frontend, and Celery workers.

## Steps to execute:

### 1. Load environment variables
```bash
set -a && source .env && set +a
```

### 2. Check Docker containers
```bash
docker-compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
```

### 3. Check PostgreSQL
```bash
PGPASSWORD="$POSTGRES_PASSWORD" psql -h localhost -p $POSTGRES_PORT -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT 'PostgreSQL: OK' AS status;" 2>/dev/null || echo "PostgreSQL: FAILED"
```

### 4. Check Redis
```bash
(redis-cli -p $REDIS_PORT ping 2>/dev/null || docker exec spending-redis redis-cli ping 2>/dev/null) | grep -q "PONG" && echo "Redis: OK" || echo "Redis: FAILED"
```

### 5. Check Backend API
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:$BACKEND_PORT/api/health 2>/dev/null | grep -q "200" && echo "Backend API: OK (port $BACKEND_PORT)" || (lsof -i :$BACKEND_PORT -t >/dev/null 2>&1 && echo "Backend: RUNNING but /api/health not responding" || echo "Backend API: NOT RUNNING")
```

### 6. Check Frontend
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:$FRONTEND_PORT 2>/dev/null | grep -qE "200|304" && echo "Frontend: OK (port $FRONTEND_PORT)" || (lsof -i :$FRONTEND_PORT -t >/dev/null 2>&1 && echo "Frontend: RUNNING but not responding to HTTP" || echo "Frontend: NOT RUNNING")
```

### 7. Check Celery Worker
Use celery inspect ping for reliable verification:
```bash
cd backend && source venv/bin/activate && timeout 5 celery -A celery_app inspect ping 2>&1 | grep -q "pong" && echo "Celery Worker: OK" || echo "Celery Worker: NOT RUNNING"
```

## Summary
After running all checks, provide a summary table showing:
- Service name
- Status (OK / FAILED / NOT RUNNING)
- Port (if applicable)

If any service is not running, suggest the command to start it.
