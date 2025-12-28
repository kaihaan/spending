# Integration Architecture - Key Patterns

## TrueLayer API Integration

### Authentication
- OAuth2 flow with refresh tokens
- Token encryption at rest (Fernet)
- Module: `mcp/truelayer_auth.py`

### Rate Limits
- **No hard numerical limits** published
- Flexible, case-by-case approach
- Provider-level limits: EU banks may return `429`
- Add `X-PSU-IP` header for user-initiated requests (currently not implemented)

### Architecture Doc
**MUST READ**: `.claude/docs/architecture/TRUELAYER_INTEGRATION.md`

### API Specs
Local specs: `.claude/docs/api/True Layer API/`
- Data API V1.json
- Cards API.json

## Amazon Selling Partner API (SP-API)

### Critical Understanding
- **NOT for consumer purchases** - for Seller accounts only
- User has Amazon Seller/Business account
- Uses Login with Amazon (LWA) OAuth

### Authentication Differences
- **NO OAuth scopes** - Application ID-based
- Custom header: `x-amz-access-token` (NOT `Authorization: Bearer`)
- Marketplace-specific (UK: `A1F83G8C2ARO7P`)

### Rate Limits (STRICT!)
- getOrders: **1 request per 6 seconds**
- getOrderItems: **1 request per 2 seconds**
- 429 responses trigger automatic retry with `Retry-After` header

### Sandbox vs Production
- Different base URLs
- Connection table tracks `is_sandbox` boolean
- Must disconnect and re-authorize to switch

### Implementation
- `mcp/amazon_sp_auth.py` - OAuth & token management
- `mcp/amazon_sp_client.py` - API client with rate limiting

## Gmail Integration

### Critical: Celery Workers
- **All Gmail sync runs in Celery** (not Flask process)
- Output appears in: `docker logs -f spending-celery`
- Code changes require: `docker-compose build celery && docker-compose up -d celery`

### Parsing Architecture
1. Pre-filter (reject marketing)
2. **Vendor-specific parsers** (highest priority) → `mcp/gmail_parsers/`
3. Schema.org extraction (fallback)
4. Pattern extraction
5. LLM enrichment (optional)

### Vendor Parsers (`mcp/gmail_parsers/`)
- `base.py` - Registry, decorator, utilities
- `amazon.py` - Amazon orders (7 parsers)
- `apple.py` - App Store, iTunes
- `financial.py` - PayPal
- `rides.py` - Uber, Lyft, Lime
- `food_delivery.py` - Deliveroo
- `ecommerce.py` - eBay, Etsy, Vinted
- `retail.py` - John Lewis, Uniqlo, CEX
- `digital_services.py` - Microsoft, Google, Figma
- `travel.py` - Airbnb, British Airways
- `specialty.py` - Other vendors

### Data Storage
- `gmail_receipts` - Parsed metadata
- `gmail_email_content` - Raw content for re-parsing
- `pdf_attachments` - Links to MinIO storage

### Performance Tracking
- `SyncPerformanceTracker` class
- PERFORMANCE SUMMARY logged at end
- Config: `GMAIL_SYNC_WORKERS`, `GMAIL_PARALLEL_FETCH`

## MCP Server Architecture

### Overview
- **32 tools** across 8 categories
- Standalone Python process (stdio communication)
- Bridge between Claude and Flask backend

### Architecture
```
Claude Code/Desktop
    ↓ (MCP Protocol via stdio)
MCP Server (Python)
    ↓ (HTTP requests)
Flask Backend (http://localhost:5000)
```

### Tool Categories
1. High-Level Workflows (5)
2. Sync Operations (6)
3. Matching Operations (4)
4. Enrichment (2)
5. Analytics & Monitoring (5)
6. Status (3)
7. Search & Query (4)
8. Gmail Debugging (3)

### Key Files
- `mcp_server/server.py` - Main server
- `mcp_server/config.py` - Configuration
- `mcp_server/client/flask_client.py` - HTTP client
- `mcp_server/tools/` - Tool implementations

### Configuration
- `.mcp.json` - Auto-loaded by Claude Code
- `FLASK_API_URL=http://localhost:5000`
- `DEFAULT_USER_ID=1`
- `DEFAULT_DATE_RANGE_DAYS=30`

## MinIO Object Storage

### Purpose
- S3-compatible storage for PDF receipts
- Container: `spending-minio`
- Ports: 9000 (API), 9001 (Console)

### Storage Pattern
- Bucket: `receipts`
- Key format: `{year}/{month}/{day}/{message_id}/{filename}`
- Client: `mcp/minio_client.py`

## LLM Enrichment

### Supported Providers
1. Anthropic (Claude)
2. OpenAI (GPT)
3. Google (Gemini)
4. DeepSeek
5. Ollama (local)

### Implementation
- `mcp/llm_enricher.py` - Main enrichment logic
- `enrichment_cache` table - Cached results
- Provider and model columns track which LLM used

## Celery Background Tasks

### When to Use
- Gmail sync (long-running)
- LLM enrichment (batch operations)
- Heavy processing

### Pattern
```python
from celery_app import celery

@celery.task
def my_task():
    # Implementation
    pass
```

### Monitoring
```bash
docker logs -f spending-celery
```

## Common Integration Patterns

### OAuth Flow
1. Generate authorization URL
2. User redirects to provider
3. Callback with authorization code
4. Exchange for access/refresh tokens
5. Encrypt and store tokens
6. Use refresh flow for renewals

### Error Handling
- Specific exceptions for API errors
- Retry logic with exponential backoff
- Rate limit handling (429 responses)
- Token refresh on 401 errors

### Data Sync Pattern
1. Check last sync timestamp
2. Fetch new/updated data
3. Parse and normalize
4. Store in database
5. Update sync timestamp
6. Track performance metrics
