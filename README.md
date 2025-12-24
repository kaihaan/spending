# Spending Tracker

Transaction management and analysis web application with bank integration and AI-powered categorization.

## Stack

**Frontend:** React 19 + TypeScript + Vite + Tailwind CSS v4 + daisyUI + D3.js
**Backend:** Python 3.12 + Flask + Celery + PostgreSQL + Redis
**Services:** Docker containers for PostgreSQL, Redis, MinIO, Celery

## Prerequisites

- Node.js 18+
- Python 3.12+
- Docker + Docker Compose

## Quick Start

```bash
# Environment
cp .env.example .env
# Edit .env with required credentials

# Services
docker-compose up -d

# Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export DB_TYPE=postgres
python app.py

# Frontend
cd frontend
npm install
npm run dev
```

**Services:**
- Backend: http://localhost:5000
- Frontend: http://localhost:5173
- PostgreSQL: localhost:5433
- Redis: localhost:6380
- MinIO Console: http://localhost:9001

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

**Backend:**
```bash
source backend/venv/bin/activate
cd backend
export DB_TYPE=postgres
python app.py
```

**Frontend:**
```bash
cd frontend
npm run dev
```

**Celery Worker:**
```bash
docker-compose build celery && docker-compose up -d celery
docker logs -f spending-celery
```

**Database:**
```bash
docker exec -it spending-postgres psql -U spending_user -d spending_db
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

| Container | Purpose |
|-----------|---------|
| `spending-postgres` | PostgreSQL 16 |
| `spending-redis` | Redis 7 |
| `spending-celery` | Background worker |
| `spending-minio` | S3-compatible storage |

**Note:** Code changes in Celery tasks require rebuild, not just restart:
```bash
docker-compose build celery && docker-compose up -d celery
```

## License

Private project
