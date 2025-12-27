Start the full development environment for the spending app.
All services run in Docker containers with hot-reload enabled.

## Arguments
- No arguments: Start all services
- `restart backend`: Restart the backend container
- `restart frontend`: Restart the frontend container
- `restart celery`: Rebuild and restart the Celery container
- `restart all`: Restart all services
- `logs`: Show logs for all services
- `logs backend`: Show backend logs
- `logs frontend`: Show frontend logs
- `logs celery`: Show Celery worker logs

## Steps to execute:

### 1. Check current status
```bash
docker-compose ps
```

### 2. Start all services (if not running)
```bash
docker-compose up -d
```

### 3. Show service URLs
```bash
echo "✓ Services started successfully!"
echo ""
echo "Access URLs:"
echo "- Frontend: http://localhost:5173"
echo "- Backend API: http://localhost:5000"
echo "- MinIO Console: http://localhost:9001"
echo "- PostgreSQL: localhost:5433"
echo "- Redis: localhost:6380"
echo ""
echo "View logs:"
echo "- All services: docker-compose logs -f"
echo "- Backend: docker-compose logs -f backend"
echo "- Frontend: docker-compose logs -f frontend"
echo "- Celery: docker-compose logs -f celery"
```

## Restart Commands

### Restart Backend (hot-reload automatic, restart only if needed)
```bash
docker-compose restart backend
```

### Restart Frontend (hot-reload automatic, restart only if needed)
```bash
docker-compose restart frontend
```

### Restart Celery (requires rebuild for code changes)
```bash
docker-compose build celery && docker-compose up -d celery
```

### Restart All Services
```bash
docker-compose restart
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f celery
```

## Notes
- Backend and Frontend have automatic hot-reload via volume mounts
- Celery requires rebuild for code changes: `docker-compose build celery && docker-compose up -d celery`
- Changes to Python code in backend/ auto-reload Flask
- Changes to React/TypeScript code in frontend/ auto-reload Vite
