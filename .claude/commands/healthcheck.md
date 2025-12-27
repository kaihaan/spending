Check the health status of all required services for the spending app.
Reports on: Docker containers, PostgreSQL, Redis, Backend API, Frontend, and Celery workers.

## Steps to execute:

### 1. Check Docker containers
```bash
docker-compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
```

### 2. Check PostgreSQL
```bash
docker exec spending-postgres pg_isready -U spending_user -d spending_db && echo "PostgreSQL: OK" || echo "PostgreSQL: FAILED"
```

### 3. Check Redis
```bash
docker exec spending-redis redis-cli ping | grep -q "PONG" && echo "Redis: OK" || echo "Redis: FAILED"
```

### 4. Check Backend API
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/api/health 2>/dev/null | grep -q "200" && echo "Backend API: OK (port 5000)" || echo "Backend API: FAILED"
```

### 5. Check Frontend
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173 2>/dev/null | grep -qE "200|304" && echo "Frontend: OK (port 5173)" || echo "Frontend: FAILED"
```

### 6. Check Celery Worker
```bash
docker exec spending-celery celery -A celery_app inspect ping 2>&1 | grep -q "pong" && echo "Celery Worker: OK" || echo "Celery Worker: FAILED"
```

### 7. Check MinIO
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:9000/minio/health/live 2>/dev/null | grep -q "200" && echo "MinIO: OK (ports 9000, 9001)" || echo "MinIO: FAILED"
```

## Summary
After running all checks, provide a summary table showing:
- Service name
- Status (OK / FAILED)
- Port (if applicable)
- Container name

Example format:
| Service | Status | Port | Container |
|---------|--------|------|-----------|
| PostgreSQL | ✅ OK | 5433 | spending-postgres |
| Redis | ✅ OK | 6380 | spending-redis |
| Backend API | ✅ OK | 5000 | spending-backend |
| Frontend | ✅ OK | 5173 | spending-frontend |
| Celery Worker | ✅ OK | - | spending-celery |
| MinIO | ✅ OK | 9000-9001 | spending-minio |

If any service is not running, suggest:
```bash
# Start all services
docker-compose up -d

# Or restart a specific service
docker-compose restart <service-name>
```
