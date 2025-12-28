# Project Structure - Personal Spending App Backend

## Overview
Flask backend for personal spending analysis with LLM enrichment, bank API integration, and receipt parsing.

## Directory Structure

```
/backend/
  /mcp/                   # MCP components (integrations)
    /gmail_parsers/       # Vendor-specific email parsers
    truelayer_auth.py     # TrueLayer OAuth & token management
    truelayer_client.py   # TrueLayer API client
    truelayer_sync.py     # Transaction synchronization
    amazon_sp_auth.py     # Amazon Selling Partner API OAuth
    amazon_sp_client.py   # Amazon SP API client
    gmail_auth.py         # Gmail OAuth
    gmail_sync.py         # Gmail receipt sync (Celery)
    gmail_parser.py       # Email parsing logic
    categorizer.py        # Rule-based & AI classification
    llm_enricher.py       # Transaction enrichment
    merchant_normalizer.py # Merchant name normalization

  /mcp_server/            # MCP Server (32 tools for Claude)
    server.py             # Main MCP server
    /tools/               # Tool implementations
      workflows.py        # High-level workflows
      sync.py             # Sync operations
      matching.py         # Matching operations
      enrichment.py       # Enrichment operations
      gmail_debug.py      # Gmail debugging tools

  /models/                # SQLAlchemy ORM models
  /database/              # Database utilities
  /tasks/                 # Celery background tasks
  /routes/                # Flask route handlers
  /services/              # Business logic
  /config/                # Configuration modules
  /auth/                  # Authentication utilities
  /middleware/            # Flask middleware
  /migrations/            # Database migrations
  /scripts/               # Utility scripts
  /tests/                 # Test suite

  app.py                  # Main Flask application
  celery_app.py           # Celery worker configuration
  database_postgres.py    # PostgreSQL adapter
  cache_manager.py        # Redis caching

/.claude/
  /docs/                  # AUTHORITATIVE documentation
    /database/            # Database schema & enforcement
    /api/                 # API specifications
    /architecture/        # Architecture docs
    /requirements/        # Feature specifications

/postgres/
  /init/                  # Database initialization SQL scripts

/docker-compose.yml       # All services orchestration
/Dockerfile              # Backend container
```

## Key Components

### MCP Server (`.mcp.json`)
- **32 tools** across 8 categories
- Enables Claude to perform autonomous operations
- Connected automatically in Claude Code CLI
- Tools: sync, match, enrich, debug, analytics

### Gmail Integration
- **Vendor-specific parsers** in `mcp/gmail_parsers/`
- Runs in **Celery workers** (not Flask process)
- Output appears in Celery logs: `docker logs -f spending-celery`
- Re-parsing support via `gmail_email_content` table

### Amazon Integration
- **SP-API** (Selling Partner API) - NOT consumer API
- Rate limits: 1 req/6s for orders
- Marketplace-specific (UK: A1F83G8C2ARO7P)
- Custom auth header: `x-amz-access-token`

### TrueLayer Integration
- OAuth2 flow for UK banks
- Account and transaction fetching
- Architecture doc: `.claude/docs/architecture/TRUELAYER_INTEGRATION.md`

### Database
- PostgreSQL 16 (Docker, port **5433**)
- Schema: `.claude/docs/database/DATABASE_SCHEMA.md`
- SQLAlchemy ORM (ongoing migration)

## File Organization Principles

1. **200-500 lines** per file (sweet spot)
2. **Under 1000 lines** maximum
3. **Single responsibility** per module
4. **Clear boundaries** between components
5. **Flat structure** where possible

## Environment Variables

Check `.env` for:
- Database credentials (NEVER assume defaults!)
- LLM API keys (Anthropic, OpenAI, Google, DeepSeek, Ollama)
- OAuth credentials (TrueLayer, Amazon, Gmail)
- Service ports (PostgreSQL: 5433, Redis: 6380)

## Docker Services

| Service | Container | Port | Notes |
|---------|-----------|------|-------|
| PostgreSQL | `spending-postgres` | 5433 | Non-standard port! |
| Redis | `spending-redis` | 6380 | Non-standard port! |
| Backend | `spending-backend` | 5000 | Auto-reloads |
| Frontend | `spending-frontend` | 5173 | Auto-reloads |
| Celery | `spending-celery` | - | Requires rebuild! |
| MinIO | `spending-minio` | 9000, 9001 | PDF storage |
