# Personal Spending App

## Project Overview

**Problem**:
1. Banks make it difficult to analyse spending patterns
   - Statement transaction descriptions difficult to understand
      - Abbreviations and company-specific codes used
      - Replaced by intermediary payment provider, obscuring item details
      - Represents multiple purchases paid at once
2. Spending management
   - Poor visibility of spending habits
   - Spending management, so that payments & savings can be made affordable
3. Categorisation
   - Traditional text analysis to categorise spending based on transaction descriptions fails
4. Transaction ingestion
   - Uploading from spreadsheets downloaded from a bank is manual, and can easily fail if templates change
5. Enriching transaction data to get more detail on the purchase
   - Information recorded about each transaction by the bank is very limited

**Solution**:
Responsive web and mobile-web personal spending analysis application.
Key features:
- API integration to get bank or card transactions (TrueLayer)
- LLM APIs to categorise transactions
- Categorise essential vs discretionary spend, to calculate Huququllah (for users who are members of the Baha'i Faith)
- Upload or API integrate for additional metadata to categorise transactions, from merchants and payment operators such as Apple, Amazon


## Key Use Cases

1. **Bank Sync**: Connect UK banks via TrueLayer for automatic transaction import
2. **AI Enrichment**: Categorise transactions using LLMs (Claude, GPT, Gemini, DeepSeek, Ollama)
3. **Purchase Matching**: Link transactions to Amazon orders and Apple purchases
4. **Huququllah**: Calculate Islamic wealth obligation (essential vs discretionary spend)
5. **Analytics**: Visualise spending patterns with D3 charts

## Code Generation
When **generating Javascript / Typescript code**:
- Assume ESLint with @typescript-eslint/recommended is enabled
- Avoid unused imports or variables
- Prefer explicit return types for exported functions
- Match existing project formatting

When **generating Python code**:
- Assume Ruff is enabled with default + pyupgrade rules
- Code must be Black-compatible (no manual formatting)
- Do not introduce unused imports, variables, or unreachable code
- Prefer explicit return types for public functions
- Use modern Python syntax (>=3.10):
  - typing | instead of Union
  - list/dict comprehensions where appropriate
  - dataclasses or pydantic models instead of ad-hoc dicts
- Avoid overly clever constructs; prefer readability
- Follow PEP 8 naming and structure
- Write docstrings for public modules, classes, and functions
- Raise specific exceptions; do not use bare `except`
- Do not suppress lint rules unless explicitly requested
- Avoid unnecessary variable assignments before `return` (Ruff RET504):
  ```python
  # Bad - Ruff rejects this
  result = some_function()
  return result

  # Good - return directly
  return some_function()
  ```

**Context7 Documentation MCP Server**: Always use Context7 for code generation, setup/configuration steps, or library/API documentation. Use Context7 MCP tools to resolve library ID and get library docs automatically.

## Tech Stack

### Frontend
| Tech | Version |
|------|---------|
| React | 19.1.1 |
| TypeScript | 5.9.3 |
| Vite | 7.1.7 |
| Tailwind CSS | 4.1.14 |
| daisyUI | 5.3.7 |
| React Router | 7.9.4 |
| D3.js | 7.9.0 |

### Backend
| Tech | Version |
|------|---------|
| Python | 3.12+ |
| Flask | 3.0.0 |
| PostgreSQL | 16 (Docker) |
| Redis | 7 (Docker) |
| Celery | 5.5.3 |
| SQLAlchemy | 2.0+ (ORM) |
| Alembic | 1.15.2 (migrations) |
| psycopg2 | 2.9.9 (legacy adapter) |
| pytest | 9.0.2 |
| pandas | 2.1.4 |

### LLM Providers
Anthropic (Claude), OpenAI, Google (Gemini), DeepSeek, Ollama (local)

### Core Backend Components

| Component | Purpose |
|-----------|---------|
| `truelayer_auth` | OAuth2 authentication and token management |
| `truelayer_client` | API client for accounts and transactions |
| `truelayer_sync` | Synchronisation logic |
| `categorizer` | Rule-based and AI classification |
| `llm_enricher` | Transaction metadata enrichment |
| `merchant_normalizer` | Merchant name normalisation |

### Database Layer (SQLAlchemy + Alembic)

**ORM Architecture:**
- **SQLAlchemy 2.0** for database models and queries (migrating from raw psycopg2)
- **Alembic** for schema migrations
- Models in `backend/database/models/` organized by domain (truelayer, amazon, gmail, etc.)
- Base declarative class: `backend/database/base.py`

**Key Files:**
- `backend/database/base.py` - Engine, session factory, declarative base
- `backend/alembic/` - Migration scripts
- `backend/alembic.ini` - Alembic configuration

**Usage:**
```python
from database.base import get_session
from database.models.truelayer import TrueLayerTransaction

with get_session() as session:
    txns = session.query(TrueLayerTransaction).filter_by(user_id=1).all()
```

**Migrations:**
```bash
cd backend
alembic revision --autogenerate -m "description"  # Generate migration
alembic upgrade head                               # Apply migrations
alembic current                                    # Check current version
```

### Testing

**Test Structure:**
- Location: `backend/tests/`
- Framework: pytest 9.0.2
- Test database: Uses PostgreSQL Docker instance (auto-cleanup fixtures)

**Running Tests:**
```bash
source backend/venv/bin/activate
PYTHONPATH=/home/kaihaan/prj/spending/backend pytest          # All tests
PYTHONPATH=/home/kaihaan/prj/spending/backend pytest -v       # Verbose
PYTHONPATH=/home/kaihaan/prj/spending/backend pytest tests/test_models/  # Specific dir
```

**Test Categories:**
- `tests/test_models/` - SQLAlchemy model tests (User, TrueLayer, Amazon, Gmail, etc.)
- `tests/test_migration_verify.py` - Database migration verification

**Writing Tests:**
- Use fixtures for database session setup/cleanup
- Follow existing patterns in `tests/test_models/test_*.py`
- Test model creation, relationships, and constraints

---

### Spending App MCP Server

**CRITICAL: MCP server enables AI-assisted operations**
- Exposes **32 tools** for autonomous spending app operations
- Connected automatically in Claude Code CLI (via `.mcp.json`)
- Standalone Python process communicating via stdio (MCP protocol)
- Acts as bridge between Claude and Flask backend API

**Architecture:**
```
Claude Code/Desktop
       ↓ (MCP Protocol via stdio)
MCP Server (Python)
       ↓ (HTTP requests)
Flask Backend (http://localhost:5000)
```

**MCP Tools vs Resources:**
- This server exposes **tools** (executable operations), NOT resources
- Empty resources list is expected and normal
- Tools allow Claude to perform operations like sync, match, enrich
- 90% of operations work with no parameters (smart defaults)

**Available Tools (32 total across 8 categories):**

| Category | Tools | Purpose |
|----------|-------|---------|
| **High-Level Workflows (5)** | `sync_all_sources`, `run_full_pipeline`, `run_pre_enrichment`, `check_sync_status`, `get_source_coverage` | Complete workflows for common operations |
| **Sync Operations (6)** | `sync_bank_transactions`, `sync_gmail_receipts`, `poll_job_status`, etc. | Data source synchronization |
| **Matching Operations (4)** | `match_amazon_orders`, `match_apple_purchases`, `match_gmail_receipts`, `run_unified_matching` | Link receipts to bank transactions |
| **Enrichment (2)** | `enrich_transactions`, `get_enrichment_stats` | LLM categorization and stats |
| **Analytics & Monitoring (5)** | `get_endpoint_health`, `get_system_analytics`, `get_error_logs`, etc. | Health checks and monitoring |
| **Status (3)** | `get_connection_status`, `get_data_summary`, `get_recent_activity` | Status and activity tracking |
| **Search & Query (4)** | `search_transactions`, `get_transaction_details`, `get_enrichment_details`, `search_enriched_transactions` | Query and analyze transaction data |
| **Gmail Debugging (3)** | `debug_gmail_receipt`, `search_gmail_receipts`, `analyze_parsing_gaps` | Debug Gmail receipt parsing issues and identify data quality gaps |

**Configuration:**
- MCP config: `.mcp.json` (auto-loaded by Claude Code)
- Server location: `backend/mcp_server/`
- Entry point: `backend/mcp_server/server.py`
- Launch script: `backend/mcp_server/run.sh`

**Environment Variables:**
```bash
FLASK_API_URL=http://localhost:5000      # Flask backend URL (default)
FLASK_API_TIMEOUT=30                      # Request timeout (seconds)
DEFAULT_USER_ID=1                         # Default user ID
DEFAULT_DATE_RANGE_DAYS=30                # Default sync range
LOG_LEVEL=INFO                            # Logging level
ENABLE_AUTO_RETRY=true                    # Enable automatic retries
MAX_RETRY_ATTEMPTS=3                      # Max retry attempts
```

**Usage Examples:**
```python
# Ask Claude in natural language:
"Sync all my data sources from the last month"
"Check if any data sources are stale"
"Run the full pipeline - sync, match, and enrich"
"Get enrichment statistics"

# Claude will use MCP tools internally:
sync_all_sources()                        # No params needed
run_full_pipeline()                       # Complete pipeline
get_source_coverage()                     # Check staleness
enrich_transactions(provider="anthropic") # Custom params
```

**Key Implementation Files:**
- `backend/mcp_server/server.py` - Main MCP server with lifespan management
- `backend/mcp_server/config.py` - Configuration and validation
- `backend/mcp_server/client/flask_client.py` - HTTP client for Flask API
- `backend/mcp_server/tools/` - Tool implementations by category:
  - `workflows.py` - High-level workflows
  - `sync.py` - Sync operations
  - `matching.py` - Matching operations
  - `enrichment.py` - Enrichment operations
  - `analytics.py` - Analytics and monitoring
  - `status.py` - Status checks
  - `search.py` - Transaction search and query
  - `gmail_debug.py` - Gmail receipt debugging and analysis

**Health Check:**
- MCP server checks Flask backend health on startup
- If Flask not running: warning logged but server starts anyway
- Verify health: `curl http://localhost:5000/api/health`

**Development:**
```bash
# Run MCP server standalone (for testing)
source backend/venv/bin/activate
python3 -m backend.mcp_server.server

# View MCP server logs (when running via Claude Code)
# Logs go to stderr by default

# Check MCP connection in Claude Code
# User message: /mcp
# Expected: "Reconnected to spending-app"
```

### Gmail Integration Architecture

**CRITICAL: Gmail sync runs in Celery background workers**
- All Gmail sync operations execute via Celery tasks (not in Flask process)
- Output (print statements, PERFORMANCE SUMMARY) appears in **Celery worker logs**, not Flask terminal
- To view sync output: `docker logs -f spending-celery` or check Celery worker terminal
- Celery code changes require **rebuild**: `docker-compose build celery && docker-compose up -d celery`
- Simple restart does NOT load new code!

**Parsing flow** (`gmail_parser.py`):
1. Pre-filter (reject marketing emails)
2. **Vendor-specific parsers** (highest priority) → `gmail_parsers/` package
3. Schema.org extraction (fallback)
4. Pattern extraction
5. LLM enrichment (optional)

**Gmail Parser Organization** (`backend/mcp/gmail_parsers/`):
- `base.py` - Parser registry, decorator, and shared utilities (parse_amount, parse_date_text)
- `amazon.py` - Amazon orders, Fresh, Business, cancellations, refunds (7 parsers)
- `apple.py` - Apple App Store and iTunes receipts
- `financial.py` - PayPal and payment processors
- `rides.py` - Uber, Lyft, Lime
- `food_delivery.py` - Deliveroo
- `ecommerce.py` - eBay, Etsy, Vinted
- `retail.py` - John Lewis, Uniqlo, CEX, World of Books
- `digital_services.py` - Microsoft, Google, Figma, Atlassian, Anthropic
- `travel.py` - Airbnb, British Airways, DHL
- `specialty.py` - All other specialty vendors

**Amazon email types** (parsers in `gmail_parsers/amazon.py`):
| Type | Detection | Parser Function |
|------|-----------|-----------------|
| `fresh` | Subject contains "Fresh" | `parse_amazon_fresh()` |
| `business` | Subject contains "Business" | `parse_amazon_business()` |
| `ordered` | Subject starts with "Ordered:" | `parse_amazon_ordered()` |

**Development flags** in `gmail_sync.py`:
- `SKIP_DUPLICATE_CHECK_DEV = True` → Re-parse existing emails (set False for production)

**Performance tracking** (Phase 1 optimization):
- `SyncPerformanceTracker` class measures API calls, DB writes, throughput
- PERFORMANCE SUMMARY logged at end of each sync
- Configuration via `.env`: `GMAIL_SYNC_WORKERS`, `GMAIL_PARALLEL_FETCH`

**Data Storage Architecture:**

| Table | Purpose |
|-------|---------|
| `gmail_connections` | OAuth tokens (encrypted) |
| `gmail_receipts` | Parsed receipt metadata (merchant, amount, line_items) |
| `gmail_email_content` | Raw email content (HTML, text, headers) for re-parsing |
| `pdf_attachments` | Links to PDF receipts in MinIO object storage |

**PDF Document Storage (MinIO):**
- S3-compatible object storage for PDF receipt attachments
- Container: `spending-minio` (ports 9000 API, 9001 console)
- Bucket: `receipts`
- Object key format: `{year}/{month}/{day}/{message_id}/{filename}`
- Client module: `backend/mcp/minio_client.py`

**Why separate `gmail_email_content` table?**
- Allows re-parsing emails with updated vendor parsers without re-fetching from Gmail API
- Debugging: examine original email content when parsing fails
- Reduces Gmail API quota usage

---

### Amazon Selling Partner API (SP-API) Integration

**CRITICAL: SP-API is NOT for consumer purchases - it's for Seller accounts**
- SP-API provides access to orders placed **with you as a seller**, not your personal purchases
- This integration works because the user has an Amazon Seller/Business account
- Uses Login with Amazon (LWA) OAuth, NOT standard consumer OAuth

**Authentication Flow** (`amazon_sp_auth.py`):
1. OAuth URL: `https://sellercentral.amazon.com/apps/authorize/consent`
2. **NO scopes** - Uses Application ID instead
3. Restricted Data Tokens (RDT) for personally identifiable information
4. Token encryption at rest using Fernet cipher

**API Client** (`amazon_sp_client.py`):
- Base URL varies by environment and region:
  - Sandbox: `https://sandbox.sellingpartnerapi-na.amazon.com`
  - Production EU: `https://sellingpartnerapi-eu.amazon.com`
  - Production NA: `https://sellingpartnerapi-na.amazon.com`
- **Custom auth header:** `x-amz-access-token` (NOT `Authorization: Bearer`)
- Marketplace-based requests (UK: `A1F83G8C2ARO7P`)

**Endpoints Used** (Orders API v0):
| Endpoint | Purpose | Rate Limit |
|----------|---------|------------|
| `GET /orders/v0/orders` | List orders with filters | 0.0167 req/sec (1 per 6s) |
| `GET /orders/v0/orders/{orderId}/orderItems` | Get line items | 0.5 req/sec (1 per 2s) |

**Rate Limiting CRITICAL:**
- getOrders: **1 request per 6 seconds** (much stricter than other APIs)
- getOrderItems: **1 request per 2 seconds**
- 429 responses trigger automatic retry with Retry-After header

**Data Storage:**
| Table | Purpose |
|-------|---------|
| `amazon_business_connections` | OAuth tokens, marketplace config |
| `amazon_business_orders` | Order summaries (reused from old integration) |
| `amazon_business_line_items` | Individual items (reused) |
| `truelayer_amazon_business_matches` | Links to bank transactions |

**Environment Configuration:**
```bash
AMAZON_SP_ENVIRONMENT=sandbox  # or 'production'
AMAZON_SP_MARKETPLACE_ID=A1F83G8C2ARO7P  # UK
AMAZON_SP_REGION=UK
AMAZON_BUSINESS_CLIENT_ID=amzn1.application-oa2-client.xxx
AMAZON_BUSINESS_CLIENT_SECRET=amzn1.oa2-cs.v1.xxx
```

**Marketplace IDs:**
- UK: `A1F83G8C2ARO7P`
- US: `ATVPDKIKX0DER`
- Germany: `A1PA6795UKMFR9`

**Sandbox vs Production:**
- Sandbox provides test data for development
- Different base URL: `sandbox.sellingpartnerapi-na.amazon.com`
- Connection table tracks `is_sandbox` boolean
- Must disconnect and re-authorize to switch modes

**Key Differences from Other Integrations:**
1. **No OAuth scopes** - Application ID-based authorization
2. **Marketplace-specific** - Each request needs marketplace ID
3. **Strict rate limits** - 6-second intervals for order fetching
4. **Custom header** - `x-amz-access-token` instead of standard `Authorization`
5. **Seller-centric** - API designed for business operations, not consumer use

**Implementation Files:**
- `backend/mcp/amazon_sp_auth.py` - OAuth and token management
- `backend/mcp/amazon_sp_client.py` - API client with rate limiting
- `backend/mcp/amazon_business_matcher.py` - Transaction matching (unchanged)
- `postgres/init/08_amazon_sp_api_migration.sql` - Database schema updates

---

## Development Commands

### Service Ports (non-standard)
| Service | Port |
|---------|------|
| PostgreSQL | **5433** |
| Redis | **6380** |
| MinIO API | **9000** |
| MinIO Console | **9001** |
| Flask Backend | 5000 |
| Vite Frontend | 5173 |

### Quick Start (All Services in Docker)
```bash
# Start all services (backend, frontend, postgres, redis, celery, minio)
docker-compose up -d

# View logs for all services
docker-compose logs -f

# View logs for specific service
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f celery

# Rebuild after code changes (automatic with volume mounts)
docker-compose restart backend
docker-compose restart frontend

# Rebuild Celery after code changes (requires full rebuild)
docker-compose build celery && docker-compose up -d celery

# Stop all services
docker-compose down

# Access the application
# Frontend: http://localhost:5173
# Backend API: http://localhost:5000
# MinIO Console: http://localhost:9001
```

### Alternative: Local Development (Legacy)
If you prefer running backend/frontend locally outside Docker:

**Backend:**
```bash
source ./backend/venv/bin/activate
cd ./backend
export DB_TYPE=postgres
python3 app.py
# → http://localhost:5000
```

**Frontend:**
```bash
cd ./frontend
npm run dev
# → http://localhost:5173
```

**Note:** You still need to run `docker-compose up -d postgres redis minio` for infrastructure services.

### Database Admin
```bash
# PostgreSQL shell
docker exec -it spending-postgres psql -U spending_user -d spending_db

# Backup
docker exec spending-postgres pg_dump -U spending_user spending_db > backup.sql
```

---

## Testing Infrastructure

**CRITICAL: Always use test database when testing**

### ⛔ MANDATORY: Test Database Safety (DO NOT SKIP)

**THIS IS NON-NEGOTIABLE. Tests MUST NEVER touch the production database (`spending_db`).**

The codebase has multiple safety layers to prevent this, but understanding them is essential:

**Safety Layer 1: Environment Variable (`TESTING=true`)**
- pytest's `conftest.py` sets `TESTING=true` before any database operations
- This environment variable triggers automatic database routing

**Safety Layer 2: Automatic Database Routing (`database/base.py`)**
```python
# If TESTING=true, the system FORCES connection to spending_db_test
# Even if POSTGRES_DB is set to spending_db, it will be overridden
IS_TESTING = os.getenv("TESTING", "").lower() in ("true", "1", "yes")
if IS_TESTING and db_name == "spending_db":
    db_name = "spending_db_test"  # FORCE test database
```

**Safety Layer 3: Runtime Verification (`conftest.py`)**
```python
# Every test fixture verifies the connected database
def verify_test_database_connection(session):
    current_db = session.execute(text("SELECT current_database()")).scalar()
    if current_db == "spending_db":
        raise RuntimeError("CRITICAL: Connected to production database!")
```

**What Happens If Safety Fails:**
- Tests will FAIL IMMEDIATELY with a big visual error box
- No data operations will proceed
- The error message explicitly states the violation

**When Writing New Tests:**
1. ALWAYS use fixtures from `conftest.py` (`client`, `db_session`, `app`)
2. NEVER create your own database connections
3. NEVER hardcode database names or connection strings
4. NEVER bypass the fixture system

**When Modifying Database Code:**
1. NEVER remove or weaken the `IS_TESTING` check in `database/base.py`
2. NEVER remove verification calls in `conftest.py`
3. If adding new database modules, copy the safety pattern from `base.py`

### Test vs Production Databases

| Database | Purpose | Port | Persistence | Usage |
|----------|---------|------|-------------|-------|
| `spending_db` | **Production/Development** | 5433 | Permanent | Live data, manual testing ONLY |
| `spending_db_test` | **Testing** | 5433 | **Persistent** | Automated tests, safe to modify |

**Note:** Both databases run on the same PostgreSQL server (port 5433). Differentiation is by database NAME, not port.

**Golden Rule:** If you're testing → use pytest with `spending_db_test`

**Database Persistence:**
- Test database persists between test runs (NOT recreated each time)
- Speeds up test iterations and allows data inspection
- To reset: `DROP DATABASE spending_db_test;` then run pytest again
- First test run creates database from production template

### Running Tests

**ALWAYS use pytest for testing:**

```bash
# Run all tests
PYTHONPATH=/home/kaihaan/prj/spending/backend pytest

# Run specific test file
PYTHONPATH=/home/kaihaan/prj/spending/backend pytest backend/tests/test_auth.py

# Run specific test function
PYTHONPATH=/home/kaihaan/prj/spending/backend pytest backend/tests/test_auth.py::test_user_registration

# Run with verbose output
PYTHONPATH=/home/kaihaan/prj/spending/backend pytest -v

# Run with output capture disabled (see print statements)
PYTHONPATH=/home/kaihaan/prj/spending/backend pytest -s

# Run and stop on first failure
PYTHONPATH=/home/kaihaan/prj/spending/backend pytest -x
```

**Test Database Reset:**

```bash
# Reset test database to fresh state (recreate from production)
PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -p 5433 -U spending_user -d postgres -c "DROP DATABASE IF EXISTS spending_db_test;"

# Next pytest run will recreate from production template
PYTHONPATH=/home/kaihaan/prj/spending/backend pytest
```

**Test Database Setup (Automatic):**
- `conftest.py` creates `spending_db_test` only if it doesn't exist
- Cloned from `spending_db` template for identical schema
- All fixtures use test database connection
- Safety checks prevent production database modification
- Database persists between test runs for faster iteration

### When to Use Testing Framework

**✅ ALWAYS use pytest when:**
- User says "test" or "run tests"
- Implementing new features (test after code changes)
- Fixing bugs (verify fix with tests)
- Modifying database schema (test migrations)
- Making API changes (test endpoints)
- Testing multi-user scenarios

**❌ NEVER use manual curl/psql testing when:**
- Testing multi-user data isolation (use pytest fixtures)
- Testing database operations (use test database)
- Verifying authentication flow (use pytest client)
- Running automated tests (use pytest)

**✓ Manual testing is OK for:**
- Quick smoke tests in development
- Debugging specific API issues with real data
- OAuth callback flows requiring browser
- One-off exploratory testing

### Test Safety Checklist

**⚠️ BEFORE any database operation during testing:**
- [ ] Running via `pytest` command (NOT manual scripts)
- [ ] `TESTING=true` is set (automatic when using pytest)
- [ ] Using fixtures from `conftest.py` (`client`, `db_session`, `app`)
- [ ] NOT creating manual database connections
- [ ] Test data uses unique identifiers (NOT hardcoded `user_id=1`)
- [ ] Verified connection to `spending_db_test` (safety checks do this automatically)

**🚨 IF SAFETY IS VIOLATED:**
Production data could be corrupted, deleted, or exposed. This is UNRECOVERABLE without backups.
The safety mechanisms exist precisely because this mistake is easy to make and catastrophic.

### Common Testing Patterns

**1. API Endpoint Testing:**
```python
def test_register_user(client):
    """Test user registration endpoint."""
    response = client.post('/api/auth/register', json={
        'email': 'test@example.com',
        'password': 'testpass123',
        'username': 'testuser'
    })
    assert response.status_code == 201
    assert 'user' in response.json
```

**2. Multi-User Data Isolation:**
```python
def test_data_isolation(client, db):
    """Verify users only see their own data."""
    # Create user1
    user1_resp = client.post('/api/auth/register', json={
        'email': 'user1@test.com',
        'password': 'password123',
        'username': 'user1'
    })

    # Add transactions for user1 (via API or direct DB)
    # ...

    # Logout
    client.post('/api/auth/logout')

    # Create user2
    user2_resp = client.post('/api/auth/register', json={
        'email': 'user2@test.com',
        'password': 'password123',
        'username': 'user2'
    })

    # Login as user2 (auto-login after registration)
    # Verify user2 sees ZERO data from user1
    response = client.get('/api/transactions')
    assert len(response.json['transactions']) == 0
```

**3. Database Operations:**
```python
def test_create_user(db):
    """Test user creation in database."""
    from backend.database import create_user

    user_id = create_user(
        db=db,
        email='test@example.com',
        password='testpass123',
        username='testuser'
    )
    assert user_id is not None

    # Verify user was created
    from sqlalchemy import text
    result = db.execute(text("SELECT * FROM users WHERE id = :user_id"),
                        {"user_id": user_id})
    user = result.fetchone()
    assert user is not None
    assert user.email == 'test@example.com'
```

**4. Persistent Test Data Pattern:**
```python
def test_with_persistent_data(client, db):
    """Test using persistent test database data.

    Since test database persists between runs, we can:
    1. Check if test data already exists
    2. Create it if needed
    3. Use it for testing
    """
    from sqlalchemy import text

    # Check if test user exists
    result = db.execute(text("SELECT id FROM users WHERE email = 'testuser@test.com'"))
    user = result.fetchone()

    if user is None:
        # Create test user (only first run)
        user_resp = client.post('/api/auth/register', json={
            'email': 'testuser@test.com',
            'password': 'testpass123',
            'username': 'testuser'
        })
        user_id = user_resp.json['user']['id']
    else:
        user_id = user.id

    # Use test user for testing
    # ...
```

### Test Coverage

Current test coverage:
- Authentication: `backend/tests/test_auth.py` (to be created)
- TrueLayer: `backend/tests/test_truelayer_*.py`
- Gmail: `backend/tests/test_gmail.py`
- Amazon: `backend/tests/test_amazon.py`
- Database: `backend/tests/test_database.py`

After implementing new features, add corresponding tests following existing patterns.

### Test Data Management

**Persistent Database Advantages:**
- Faster test iterations (no DB recreation)
- Can inspect test data between runs
- Reuse test data across runs (e.g., test users)

**Persistent Database Considerations:**
- Test data accumulates over time
- May need periodic cleanup
- Reset database if tests become inconsistent

**When to Reset Test Database:**
- Production schema changed (migrations run)
- Test data became inconsistent or corrupted
- Need fresh baseline from production
- Tests failing due to data pollution

---

## Coding Guidance

1. **Python Development**: ALWAYS activate the virtual environment before running Python:
   ```bash
   source ./backend/venv/bin/activate
   ```
   **IMPORTANT**: Shells use `python3` NOT `python`. Always use `python3` in bash commands.

2. **Database Configuration**:
   - **Primary DB:** PostgreSQL (via Docker, port **5433**)
   - **Schema Reference:** `.claude/docs/database/DATABASE_SCHEMA.md` ← **AUTHORITATIVE SOURCE**
   - **Enforcement Rules:** `.claude/docs/database/SCHEMA_ENFORCEMENT.md`
   - **DO NOT use local postgres**
   - **password:** default passwords are not used.  ALWAYS check .env for password.

3. **TrueLayer API**:
   - External docs: https://docs.truelayer.com/reference/welcome-api-reference
   - Local specs: `.claude/docs/api/True Layer API/` ← **USE THESE FOR IMPLEMENTATION**
   - Architecture: `.claude/docs/architecture/TRUELAYER_INTEGRATION.md`

   **Rate Limits:**
   - **No hard numerical limits published** - TrueLayer uses flexible, case-by-case approach
   - Monitors API call volume; will contact if usage becomes unreasonable
   - Persistent high-volume accounts may face throttling/blocking
   - **Provider-level rate limits:** EU banks limit unattended API requests (returns `429` error)

   **Avoiding Rate Limits:**
   - Include end-user's IP address in requests via `X-PSU-IP` header (for user-initiated requests)
   - This signals attended access vs. unattended polling
   - Our implementation: Currently **no** `X-PSU-IP` header (all requests treated as unattended)
   - Our implementation: **No rate limit handling** in `truelayer_client.py` (unlike Amazon SP client)

   **Error Responses:**
   - HTTP 429: `provider_too_many_requests` - Provider rate limit exceeded
   - HTTP 429: `unattended_calls_limit_exceeded` - TrueLayer limit for unattended calls
   - No `Retry-After` header documented (unlike Amazon SP API)

   **Best Practices for Implementation:**
   - Add retry logic with exponential backoff for `429` errors (see `amazon_sp_client.py` lines 168-171)
   - Consider adding `X-PSU-IP` header for user-triggered sync operations
   - Implement parallel account sync carefully (see Gmail's `ThreadPoolExecutor` pattern)
   - Monitor for `429` responses and adjust concurrency dynamically

   **References:**
   - [TrueLayer Rate Limits Support Article](https://support.truelayer.com/hc/en-us/articles/360003994498-What-rate-limits-apply-to-the-Data-API)
   - Data API spec: `.claude/docs/api/True Layer API/Data API V1.json` (429 response definitions)

4. **Docker Services (CRITICAL)**
   All services run in Docker containers - `pkill` commands do NOT work:
   | Service | Container | Port |
   |---------|-----------|------|
   | PostgreSQL | `spending-postgres` | 5433 |
   | Redis | `spending-redis` | 6380 |
   | Backend | `spending-backend` | 5000 |
   | Frontend | `spending-frontend` | 5173 |
   | Celery | `spending-celery` | - |
   | MinIO | `spending-minio` | 9000 (API), 9001 (Console) |

   **Code changes and hot-reloading:**
   - **Backend & Frontend:** Code changes auto-reload via mounted volumes (no rebuild needed)
   - **Celery:** Code changes require REBUILD: `docker-compose build celery && docker-compose up -d celery`

   ```bash
   # Backend/Frontend changes (hot-reload automatic):
   # Just save your file - Flask and Vite will detect changes

   # Force restart if needed:
   docker-compose restart backend
   docker-compose restart frontend

   # Celery changes (requires rebuild):
   docker-compose build celery && docker-compose up -d celery
   ```

   **Debug logging in Docker containers:**
   - View logs: `docker-compose logs -f backend` or `docker-compose logs -f celery`
   - `print()` statements in Flask/Celery appear in Docker logs, NOT local terminal
   - Dev pattern: Use `docker-compose logs -f` in a separate terminal window

6. **PostgreSQL Syntax Notes**
   PostgreSQL does NOT support `DELETE ... LIMIT`. Use subquery:
   ```sql
   DELETE FROM table WHERE id = (SELECT id FROM table WHERE condition LIMIT 1)
   ```

7. **File Organization & Length (Python Best Practices)**

   **File Length Guidelines:**
   - **200-500 lines** is the sweet spot for maintainability and context management
   - **Under 1000 lines** is a reasonable upper bound before considering splitting
   - Very short files (< 50 lines) are fine for utilities, constants, or type definitions

   **Why File Length Matters for Claude Code:**
   - **Context window efficiency** — Shorter, focused files mean Claude can hold more relevant codebase in context
   - **Edit precision** — Smaller files reduce unintended side effects
   - **Faster iteration** — Less to re-read and re-process on each interaction

   **Organizational Principles:**
   - **Single responsibility** — Each file/module should do one thing well
   - **Clear module boundaries** — Group related functionality, separate unrelated concerns
   - **Explicit interfaces** — Use `__init__.py` to expose public APIs, keep implementation details in separate files
   - **Flat is better than nested** — Avoid deep directory structures when a flatter layout suffices

   **Python-Specific Structure:**
   ```
   backend/
   ├── mcp/              # MCP components
   │   ├── models/       # Data structures (one file per domain entity)
   │   ├── services/     # Business logic (one file per service)
   │   ├── utils/        # Small, focused utility modules
   │   └── api/          # Endpoints/handlers
   ├── tasks/            # Celery background tasks
   ├── config/           # Configuration modules
   └── tests/            # Mirror the source structure
   ```

   **Practical Tips:**
   - If a file has multiple classes that don't interact much, split them
   - Extract large functions (50+ lines) or complex logic into separate modules
   - Keep configuration, constants, and type definitions in dedicated files
   - Use descriptive filenames that indicate content without needing to open the file
   - Goal: Make it easy for both humans and Claude to understand structure at a glance

---

## UI Design Principles

- Minimal design language with maximum negative space
- Responsive UI for mobile and desktop
- Clear information hierarchy (important = centre, larger, bolder)
- No more than 3 text sizes; consistent corner radii
- CSS animations for page loads and micro-interactions
- Layered backgrounds with gradients for depth
- All daisyUI themes available as user preference
- Avoid modals - use only for urgent actions and alerts
- Optimise page load times
- Use single page application pattern for content with client-side state
- NEVER use loading spinners - use progress bars or animated ellipses instead
- Use expanding drawers in preference to modals
- ONLY EVER use modals for very urgent user wanrnings that require immediate attention

---

## Documentation Structure

**Reference Documentation** (`.claude/docs/`):
```
.claude/docs/
├── database/
│   ├── DATABASE_SCHEMA.md        ← AUTHORITATIVE schema reference
│   ├── SCHEMA_ENFORCEMENT.md     ← Code patterns & rules
│   └── SCHEMA_CRITICAL_FIXES.md  ← Past bugs to avoid
├── api/
│   ├── True Layer API/           ← TrueLayer JSON specs
│   ├── TRUELAYER_CARD_API_GUIDE.md
│   └── BANK_INTEGRATION_TROUBLESHOOTING.md
├── requirements/
│   ├── _TEMPLATE.md              ← Template for new features
│   ├── testing-dashboard-requirements.md
│   ├── gmail.md
│   └── enrichment.md             ← Feature specifications
├── architecture/
│   ├── TRUELAYER_INTEGRATION.md  ← Integration architecture
│   └── TRUELAYER_*.md            ← Component maps, workflows
├── bugs/
│   └── BUG_TRACKER.md            ← Discovered bugs with dates, severity, status
└── deployment/
    └── PRODUCTION_DEPLOYMENT_PLAN.md
```

**Implementation Plans** (`docs/plans/`):
- Active implementation plans with step-by-step execution instructions
- Example: `docs/plans/2025-12-28-sqlalchemy-alembic-migration.md`

**Bug Tracking** (`.claude/docs/bugs/BUG_TRACKER.md`):
- Centralized bug documentation with severity, status, and fix requirements
- All discovered bugs should be documented here with date/time
- Format: BUG-XXX with full reproduction steps and impact analysis

---

## Database Schema

> **ALWAYS consult:** `.claude/docs/database/DATABASE_SCHEMA.md`
>
> The file above contains complete column definitions, data types, constraints, relationships, and a change log.

Quick reference only (may be outdated):
- `transactions` - Santander Excel imports (LEGACY - NO LONGER USED)
- `truelayer_transactions` - TrueLayer API transactions
- `truelayer_accounts` - Connected bank accounts
- `truelayer_connections` - OAuth connections
- `amazon_orders`, `apple_transactions` - Linked data sources

**For actual column names and types → READ THE DOCS**

---

## API Endpoints

> **For implementation details, check actual Flask routes in `backend/app.py`**

Core endpoints:
- `GET /api/transactions` - All transactions
- `GET /api/truelayer/connections` - TrueLayer connections
- `POST /api/truelayer/authorize` - OAuth flow
- `POST /api/truelayer/import/plan` - Plan batch import
- `POST /api/truelayer/import/start` - Start import job
- `GET /api/truelayer/import/status/<job_id>` - Job status
- `GET /api/enrichment/config` - LLM enrichment config
- `GET /api/summary` - Spending summary
- `GET /api/trends` - Timeseries data

---

## Workflow Checklists

### Before ANY Database Work:
- [ ] Read `.claude/docs/database/DATABASE_SCHEMA.md`
- [ ] Check `.claude/docs/database/SCHEMA_ENFORCEMENT.md` for patterns
- [ ] Review `.claude/docs/database/SCHEMA_CRITICAL_FIXES.md` for past bugs
- [ ] Verify column names match documentation exactly

### Before ANY Database Schema Change:
- [ ] Invoke database-migration skill
- [ ] Complete Pre-Migration Checklist (Phase 0)
- [ ] Follow 5-phase workflow (Generate → Rollback → Tests → Docs → Validate)
- [ ] Verify all 6 critical bugs prevented (dict/scalar, JSON, typos, timezone, imports, tokens)

### Before ANY TrueLayer Work:
- [ ] Read `.claude/docs/architecture/TRUELAYER_INTEGRATION.md`
- [ ] Check relevant JSON spec in `.claude/docs/api/True Layer API/`
- [ ] Review troubleshooting guide if debugging

### Before ANY Feature Implementation:
- [ ] Check `.claude/docs/requirements/` for spec
- [ ] If no spec exists, create one and get approval
- [ ] Clarify any ambiguous requirements with user
- [ ] Only then begin implementation

### After Completing Work:
- [ ] Run tests: `PYTHONPATH=/home/kaihaan/prj/spending/backend pytest`
- [ ] Update relevant documentation if schema/API changed
- [ ] Add entry to schema change log if applicable
- [ ] Verify code matches documentation

---

## Frontend Structure

Built with **TypeScript** + React + Vite + Tailwind CSS v4 + daisyUI.

**Pages:**
- Dashboard - Spending overview
- Transactions - List and filtering
- Settings - TrueLayer, LLM enrichment, Huququllah
- Huququllah - Islamic financial categorisation

**IMPORTANT**: Never create components for manual transaction entry.

---

## Privacy & Security

- All operations are **local** - no cloud upload
- Claude MCP interactions use anonymised data only
- Optional offline mode available
- Data folder: `~/FinanceData/` (configurable)

---

## Repository Structure

```
/backend/
  /mcp/            MCP components (TrueLayer, LLM providers, matchers)
  /database/       SQLAlchemy models organized by domain
    /models/       (truelayer, amazon, gmail, apple, category, enrichment, user)
    base.py        Engine, session factory, declarative base
  /alembic/        Alembic migration scripts
  /tests/          pytest test suite
    /test_models/  Model tests by domain
  /tasks/          Celery background tasks
  /mcp_server/     MCP server for Claude Code integration
  app.py           Main Flask application
  celery_app.py    Celery worker configuration
  database_postgres.py  PostgreSQL adapter (legacy, being replaced by SQLAlchemy)
  alembic.ini      Alembic configuration
/frontend/
  /src/
    /components/   Reusable UI components
    /pages/        Main views (Dashboard, Transactions, Settings, Huququllah)
    /contexts/     React context providers
    /utils/        Utility functions
    /charts/       D3 visualisation components
/postgres/
  /init/           Database initialisation SQL scripts
/docs/
  /plans/          Active implementation plans
/.claude/
  /docs/           Reference documentation (AUTHORITATIVE)
  CLAUDE.md        This file
```
