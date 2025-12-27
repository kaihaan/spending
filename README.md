# Spending Tracker

Transaction management and analysis web application with bank integration and AI-powered categorization.

## Stack

**Frontend:** React 19 + TypeScript + Vite + Tailwind CSS v4 + daisyUI + D3.js
**Backend:** Python 3.12 + Flask + Celery + PostgreSQL + Redis
**Services:** Docker containers for PostgreSQL, Redis, MinIO, Celery

## Prerequisites

- Docker + Docker Compose

**Optional (for local development without Docker):**
- Node.js 18+
- Python 3.12+

## Quick Start

```bash
# Environment setup
cp .env.example .env
# Edit .env with required credentials

# Start all services (backend, frontend, database, cache, workers)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down
```

**Access:**
- Frontend: http://localhost:5173
- Backend API: http://localhost:5000
- MinIO Console: http://localhost:9001
- PostgreSQL: localhost:5433
- Redis: localhost:6380

## Features

- **Bank Integration**: TrueLayer API for automatic transaction sync
- **AI Enrichment**: Multi-provider LLM categorization (Claude, GPT, Gemini, DeepSeek, Ollama)
- **Purchase Matching**: Amazon and Apple transaction linking
- **Email Parsing**: Gmail integration for receipt extraction with PDF storage
- **Analytics**: D3-based spending visualization

## Architecture

```
backend/
  mcp/              # Integration modules (TrueLayer, Gmail, Amazon, Apple)
  tasks/            # Celery background jobs
  config/           # Configuration
  app.py            # Flask API
  celery_app.py     # Worker config

frontend/
  src/
    pages/          # Dashboard, Transactions, Settings
    components/     # UI components
    charts/         # D3 visualizations

postgres/
  init/             # Schema initialization scripts
```

## Development

**All services run in Docker with hot-reloading enabled:**

```bash
# Start all services
docker-compose up -d

# View logs for specific service
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f celery

# Restart after code changes (usually not needed - hot-reload is automatic)
docker-compose restart backend
docker-compose restart frontend

# Celery requires rebuild for code changes
docker-compose build celery && docker-compose up -d celery

# Database access
docker exec -it spending-postgres psql -U spending_user -d spending_db
```

**Alternative: Local Development (without Docker)**
If you prefer running backend/frontend outside Docker:

```bash
# Start infrastructure services only
docker-compose up -d postgres redis minio

# Backend (separate terminal)
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export DB_TYPE=postgres
python3 app.py

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

## Service Ports

| Service | Port |
|---------|------|
| PostgreSQL | 5433 |
| Redis | 6380 |
| Flask | 5000 |
| Vite | 5173 |
| MinIO API | 9000 |
| MinIO Console | 9001 |

## Docker Containers

| Container | Purpose | Hot-Reload |
|-----------|---------|------------|
| `spending-backend` | Flask API | ✅ Yes |
| `spending-frontend` | Vite dev server | ✅ Yes |
| `spending-postgres` | PostgreSQL 16 | N/A |
| `spending-redis` | Redis 7 | N/A |
| `spending-celery` | Background worker | ❌ No (requires rebuild) |
| `spending-minio` | S3-compatible storage | N/A |

**Hot-Reload:**
- Backend & Frontend: Code changes automatically reload (no action needed)
- Celery: Requires rebuild for code changes:
  ```bash
  docker-compose build celery && docker-compose up -d celery
  ```

## License

Private project
