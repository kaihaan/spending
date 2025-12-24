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
| psycopg2 | 2.9.9 |
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

### Gmail Integration Architecture

**Parsing flow** (`gmail_parser.py`):
1. Pre-filter (reject marketing emails)
2. **Vendor-specific parsers** (highest priority) → `gmail_vendor_parsers.py`
3. Schema.org extraction (fallback)
4. Pattern extraction
5. LLM enrichment (optional)

**Amazon email types** (each has own parser in `gmail_vendor_parsers.py`):
| Type | Detection | Parser Function |
|------|-----------|-----------------|
| `fresh` | Subject contains "Fresh" | `parse_amazon_fresh()` |
| `business` | Subject contains "Business" | `parse_amazon_business()` |
| `ordered` | Subject starts with "Ordered:" | `parse_amazon_ordered()` |

**Development flags** in `gmail_sync.py`:
- `SKIP_DUPLICATE_CHECK_DEV = True` → Re-parse existing emails (set False for production)

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

## Development Commands

### Service Ports (non-standard)
| Service | Port |
|---------|------|
| PostgreSQL | **5433** |
| Redis | **6380** |
| Flask Backend | 5000 |
| Vite Frontend | 5173 |

### Prerequisites
```bash
# Start PostgreSQL and Redis
docker-compose up -d

# Verify running
docker-compose ps
```

### Backend
```bash
source ./backend/venv/bin/activate
cd ./backend
export DB_TYPE=postgres
python app.py
# → http://localhost:5000
```

### Frontend
```bash
cd ./frontend
npm run dev
# → http://localhost:5173
```

### Celery Worker (for background enrichment)
```bash
source ./backend/venv/bin/activate
cd ./backend
celery -A celery_app worker --loglevel=info
```

### Database Admin
```bash
# PostgreSQL shell
docker exec -it spending-postgres psql -U spending_user -d spending_db

# Backup
docker exec spending-postgres pg_dump -U spending_user spending_db > backup.sql
```

---

## Coding Guidance

1. **Python Development**: ALWAYS activate the virtual environment before running Python:
   ```bash
   source ./backend/venv/bin/activate
   ```

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

4. **Context7 Documentation MCP Server**: Always use Context7 for code generation, setup/configuration steps, or library/API documentation. Use Context7 MCP tools to resolve library ID and get library docs automatically.

5. **Docker Services (CRITICAL)**
   All backend services run in Docker containers - `pkill` commands do NOT work:
   | Service | Container | Port |
   |---------|-----------|------|
   | PostgreSQL | `spending-postgres` | 5433 |
   | Redis | `spending-redis` | 6380 |
   | Celery | `spending-celery` | - |
   | MinIO | `spending-minio` | 9000 (API), 9001 (Console) |

   **Celery code changes require REBUILD, not restart:**
   ```bash
   # For backend code changes (tasks, imports, config):
   docker-compose build celery && docker-compose up -d celery

   # Simple restart does NOT pick up code changes:
   docker restart spending-celery  # WRONG for code changes!
   ```

   **Debug logging in Docker containers:**
   - `print()` in Celery tasks is NOT visible in terminal
   - Use `docker logs spending-celery` or write to files inside container
   - Dev pattern: Write to `/tmp/debug.txt`, then `docker exec spending-celery cat /tmp/debug.txt`

6. **PostgreSQL Syntax Notes**
   PostgreSQL does NOT support `DELETE ... LIMIT`. Use subquery:
   ```sql
   DELETE FROM table WHERE id = (SELECT id FROM table WHERE condition LIMIT 1)
   ```

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

```
.claude/docs/
├── database/
│   ├── DATABASE_SCHEMA.md        ← AUTHORITATIVE schema reference
│   ├── SCHEMA_ENFORCEMENT.md     ← Code patterns & rules
│   ├── SCHEMA_CRITICAL_FIXES.md  ← Past bugs to avoid
│   └── POSTGRES_MIGRATION.md
├── api/
│   ├── True Layer API/           ← TrueLayer JSON specs
│   ├── TRUELAYER_CARD_API_GUIDE.md
│   └── BANK_INTEGRATION_TROUBLESHOOTING.md
├── requirements/
│   ├── _TEMPLATE.md              ← Template for new features
│   ├── brief.md                  ← Project brief
│   └── enrichment.md             ← Enrichment feature spec
├── architecture/
│   ├── TRUELAYER_INTEGRATION.md  ← Integration architecture
│   └── TRUELAYER_*.md            ← Other architecture docs
└── development/
    └── setup/
        └── QUICK_START_POSTGRES.md
```

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
  /tasks/          Celery background tasks
  /config/         Configuration modules
  /migrations/     Database migrations
  app.py           Main Flask application
  celery_app.py    Celery worker configuration
  database_postgres.py  PostgreSQL adapter
/frontend/
  /src/
    /components/   Reusable UI components
    /pages/        Main views (Dashboard, Transactions, Settings, Huququllah)
    /contexts/     React context providers
    /utils/        Utility functions
    /charts/       D3 visualisation components
/postgres/
  /init/           Database initialisation scripts
/.claude/
  /docs/           All documentation (AUTHORITATIVE)
  CLAUDE.md        This file
```
