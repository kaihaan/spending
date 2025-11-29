# CLAUDE.md

## ⛔ MANDATORY BEHAVIORS (READ FIRST)

### 1. STOP AND ASK - Never Assume

**Before implementing ANY change, Claude MUST verify requirements are clear.**

If there is ANY ambiguity about what the user wants, **STOP and ask clarifying questions**. Do not guess, infer, or "be helpful" by making assumptions.

**Examples requiring clarification:**

| User Says | Problem | Ask Instead |
|-----------|---------|-------------|
| "Fix the import" | Which import? What's broken? | "Which import is failing? What error are you seeing? What should the expected behavior be?" |
| "Add validation" | What fields? What rules? | "Which fields need validation? What are the validation rules? What error messages should be shown?" |
| "Improve performance" | Where? How measured? | "Which endpoint or component? What's the current performance? What's the target?" |
| "Update the schema" | Which table? What changes? | "Which table needs updating? What columns are being added/changed? What are the data types and constraints?" |
| "Make it work like X" | Undefined behavior | "Can you describe specifically what behavior you want? What should happen when...?" |

**Rule: When in doubt, ASK. A 30-second clarification prevents hours of rework.**

---

### 2. DOCUMENTATION-FIRST - Never Hallucinate

**Before writing ANY code that touches database, API, or features, Claude MUST consult the authoritative documentation.**

#### Required Documentation Checks:

| Working On | MUST Read First | Location |
|------------|-----------------|----------|
| Database schemas, columns, tables | `DATABASE_SCHEMA.md` | `.claude/docs/database/DATABASE_SCHEMA.md` |
| Database code patterns | `SCHEMA_ENFORCEMENT.md` | `.claude/docs/database/SCHEMA_ENFORCEMENT.md` |
| TrueLayer integration | `TRUELAYER_INTEGRATION.md` | `.claude/docs/architecture/TRUELAYER_INTEGRATION.md` |
| TrueLayer API specifics | TrueLayer API JSON specs | `.claude/docs/api/True Layer API/` |
| Feature requirements | Feature spec | `.claude/docs/requirements/[feature].md` |

#### Anti-Hallucination Rules:

1. **Database columns** → MUST match `DATABASE_SCHEMA.md` exactly. Never guess column names, types, or constraints.
2. **API responses** → MUST match documented schemas. Never assume response structure.
3. **TrueLayer fields** → MUST match the JSON specs in `.claude/docs/api/True Layer API/`. Fields like `running_balance` return objects, not scalars.
4. **Function signatures** → Check actual code, not memory.

**If documentation is missing or outdated:**
- STOP and tell the user: "The documentation for [X] appears to be missing/outdated. Should I update it first before proceeding?"
- Update documentation BEFORE writing code that depends on it.

---

### 3. REQUIREMENTS-FIRST - No Spec, No Code

**Before implementing any feature, Claude MUST verify documented requirements exist.**

#### Workflow:

```
User requests feature
        ↓
Check .claude/docs/requirements/ for spec
        ↓
    ┌───┴───┐
    │ Found │ → Read spec → Ask clarifying questions → Get approval → Implement
    └───┬───┘
        │
    Not Found
        ↓
STOP and ask: "I don't have documented requirements for [feature]. 
Please provide specifications, or should I create a requirements 
document for your approval first?"
        ↓
Create requirements doc → Get user approval → THEN implement
```

#### Requirements Template Location:
`.claude/docs/requirements/_TEMPLATE.md`

---

## CRITICAL DEVELOPMENT RULES

### 🔴 ALWAYS Follow These Rules:

1. **Python Development**: ALWAYS activate the Python virtual environment before running any Python commands:
   ```bash
   source /mnt/c/dev/spending/backend/venv/bin/activate
   ```

2. **Database Configuration**:
   - **Primary DB:** PostgreSQL (via Docker)
   - **Schema Reference:** `.claude/docs/database/DATABASE_SCHEMA.md` ← **AUTHORITATIVE SOURCE**
   - **Enforcement Rules:** `.claude/docs/database/SCHEMA_ENFORCEMENT.md`

3. **Transaction Data Source**: Transactions MUST ONLY come from TrueLayer API integration. NEVER create UI components or API endpoints for manual transaction entry.

4. **TypeScript**: Frontend uses TypeScript. All new files must be `.tsx/.ts`.

5. **Backend Server**: 
   ```bash
   source /mnt/c/dev/spending/backend/venv/bin/activate && cd /mnt/c/dev/spending/backend && python app.py
   ```

6. **Docker**: PostgreSQL runs in Docker. Start before backend:
   ```bash
   cd /mnt/c/dev/spending && docker-compose up -d
   ```

7. **TrueLayer API**: 
   - External docs: https://docs.truelayer.com/reference/welcome-api-reference
   - Local specs: `.claude/docs/api/True Layer API/` ← **USE THESE FOR IMPLEMENTATION**
   - Architecture: `.claude/docs/architecture/TRUELAYER_INTEGRATION.md`

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

### Documentation Rules:

1. **File into most specific folder** - Database docs → `database/`, API docs → `api/`
2. **Never create workflow folders** - No `draft/`, `final/`, `generated/`
3. **Update after code changes** - Schema change = immediate doc update
4. **Requirements before features** - No spec = no implementation

---

## Project Overview

**Privacy-first local personal finance analysis service** integrating with TrueLayer for real-time bank synchronization.

Key principles:
- All data processing is **local-only**
- Uses Claude via MCP for AI-assisted categorization
- **TypeScript** + React + Tailwind + daisyUI frontend
- Python Flask backend
- **PostgreSQL** (production) via Docker
- **Transactions only from TrueLayer API - no manual entry**

### Core Backend Components

| Component | Purpose |
|-----------|---------|
| `truelayer_auth` | OAuth2 authentication and token management |
| `truelayer_client` | API client for accounts and transactions |
| `truelayer_sync` | Synchronization logic |
| `categorizer` | Rule-based and AI classification |
| `llm_enricher` | Transaction metadata enrichment |
| `merchant_normalizer` | Merchant name normalization |

---

## Database Schema

> ⚠️ **DO NOT use the summary below for implementation.**
> 
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

> ⚠️ **For implementation details, check actual Flask routes in `backend/app.py`**

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

## Development Commands

### Prerequisites
```bash
# Start PostgreSQL
cd /mnt/c/dev/spending && docker-compose up -d

# Verify running
docker-compose ps
```

### Backend
```bash
source /mnt/c/dev/spending/backend/venv/bin/activate
cd /mnt/c/dev/spending/backend
export DB_TYPE=postgres
python app.py
# → http://localhost:5000
```

### Frontend
```bash
cd /mnt/c/dev/spending/frontend
npm run dev
# → http://localhost:5173
```

### Database Admin
```bash
# PostgreSQL shell
docker exec -it spending-postgres psql -U spending_user -d spending_db

# Backup
docker exec spending-postgres pg_dump -U spending_user spending_db > backup.sql
```

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
- Huququllah - Islamic financial categorization

**IMPORTANT**: Never create components for manual transaction entry.

---

## Privacy & Security

- All operations are **local** - no cloud upload
- Claude MCP interactions use anonymized data only
- Optional offline mode available
- Data folder: `~/FinanceData/` (configurable)

---

## Repository Structure

```
/backend/
  /mcp/            MCP components
  /migrations/     Database migrations
  app.py           Main Flask application
/frontend/
  /src/
    /components/   Reusable UI components
    /pages/        Main views
/.claude/
  /docs/           All documentation (AUTHORITATIVE)
  CLAUDE.md        This file
```

---

## Summary: The Three Rules

1. **STOP AND ASK** - If requirements are unclear, ask before coding
2. **READ THE DOCS** - Consult `.claude/docs/` before any database/API/feature work  
3. **REQUIREMENTS FIRST** - No spec = no implementation; create spec first if missing