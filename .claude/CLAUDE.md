# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## CRITICAL DEVELOPMENT RULES

### 🔴 ALWAYS Follow These Rules:

1. **Python Development**: ALWAYS activate the Python virtual environment before running any Python commands or starting the backend server:
   ```bash
   source /mnt/c/dev/spending/backend/venv/bin/activate
   ```

2. **Database Configuration**:
   - **Primary DB:** PostgreSQL (via Docker) - production ready
   - **Legacy DB:** SQLite (finance.db) - no longer used
   - **Switching:** Use `DB_TYPE=postgres` or `DB_TYPE=sqlite` in `.env`
   - **Default:** Configured for PostgreSQL

3. **Transaction Data Source**: Transactions MUST ONLY come from imported Santander Excel bank statements or TrueLayer API. NEVER create UI components or API endpoints that allow users to manually add, edit, or create transactions. This is a hard requirement for data integrity.

4. **TypeScript**: The frontend is built with TypeScript. All new components and files must use TypeScript (.tsx/.ts), not JavaScript (.jsx/.js).

5. **Backend Server**: When starting the backend, use absolute paths and activate venv:
   ```bash
   source /mnt/c/dev/spending/backend/venv/bin/activate && cd /mnt/c/dev/spending/backend && python app.py
   ```

6. **Docker**: PostgreSQL database runs in Docker. Must be started before running backend:
   ```bash
   cd /mnt/c/dev/spending
   docker-compose up -d
   ```

7. **Truelayer API reference**
   Refer to this source when planning True Layer API integrations: https://docs.truelayer.com/reference/welcome-api-reference

8. **Documentation**

Claude must store all documentation in `.claude/docs/` using this structure:

- project/
- architecture/
- design/
- database/
- containers/
- development/
- operations/
- reference/
- releases/

Claude should file documents into the most specific folder.
If the document concerns:
- Database schemas, ERDs, migrations → database/
- Containers, Docker, container images → containers/
- Local development environment setup → development/setup/

Claude should never create workflow-based folders (draft, final, generated).

9. **Planning & documentation maintainence**

1. When planning always consult existing documentation first
2. Always update documentation after completing material code changes


## Project Overview

This is a **privacy-first local personal finance analysis service** that parses Santander Excel bank statements, categorizes transactions using AI (via Claude MCP), provides spending insights through a web dashboard, and integrates with TrueLayer for real-time bank synchronization.

Key principles:
- All data processing is **local-only** (no cloud uploads of raw data)
- Uses Claude via MCP for AI-assisted transaction categorization
- Built with **TypeScript** + React + Tailwind + daisyUI frontend and Python backend
- Data stored in **PostgreSQL** (production) or SQLite (legacy)
- **Transactions only imported from bank statements or TrueLayer API - no manual entry allowed**
- Support for multiple data sources: Santander Excel, Amazon orders, Apple transactions, TrueLayer banks

## System Architecture

### MCP Components (Model Context Protocol)
The backend is structured around MCP components that expose capabilities:

1. **`excel_parser`** - Parses Santander-specific Excel format into normalized transactions
2. **`file_manager`** - Scans local folder for available Excel files
3. **`categorizer`** - Applies rule-based and AI-assisted transaction classification
4. **`analytics_engine`** - Aggregates transactions and computes spending trends
5. **`ui_server`** - Serves REST API and frontend assets

### Data Flow
1. User uploads Santander `.xlsx` file through web UI
2. `excel_parser` extracts transactions (date, description, amount, balance)
3. `categorizer` assigns categories (groceries, transport, etc.) using rules + Claude AI
4. Transactions stored in local database
5. `analytics_engine` generates insights (trends, top categories, savings opportunities)
6. Dashboard displays charts and AI-generated recommendations

### Database Schema

**transactions table:**
- id (INTEGER, PK)
- date (DATE)
- description (TEXT) - Original transaction text
- amount (REAL) - Negative for expenses, positive for income
- category (TEXT)
- source_file (TEXT) - Excel filename
- merchant (TEXT) - Extracted merchant name

**categories table:**
- name (TEXT)
- rule_pattern (TEXT) - Regex or keyword matching rule
- ai_suggested (BOOLEAN)

## Development Commands

### Prerequisites (Run First)
```bash
# Start PostgreSQL database
cd /mnt/c/dev/spending
docker-compose up -d

# Verify container is running
docker-compose ps
```

### Backend (Python + Flask)
```bash
# Always activate venv first!
source /mnt/c/dev/spending/backend/venv/bin/activate
cd /mnt/c/dev/spending/backend

# Set database type (default: postgres)
export DB_TYPE=postgres

# Run backend
python app.py
# Backend runs on http://localhost:5000
```

### Frontend (TypeScript + React + Vite)
```bash
cd /mnt/c/dev/spending/frontend
npm run dev
# Frontend runs on http://localhost:5173
```

### Database Administration
```bash
# Access PostgreSQL shell
docker exec -it spending-postgres psql -U spending_user -d spending_db

# Check database health
docker-compose logs postgres

# Backup database
docker exec spending-postgres pg_dump -U spending_user spending_db > backup.sql

# Stop/start database (keeps data)
docker-compose down
docker-compose up -d
```

### Important Notes:
- PostgreSQL MUST be running before starting backend
- Backend MUST be started with venv activated and DB_TYPE=postgres
- Frontend is fully TypeScript - no JavaScript files
- See `docs/POSTGRES_MIGRATION.md` for migration procedures

## API Endpoints

- `GET /api/files` - List available Excel files in data folder
- `POST /api/import` - Parse and import selected Excel file
- `GET /api/categories` - Return all categories and classification rules
- `GET /api/summary` - Aggregated spending summary
- `GET /api/trends` - Timeseries spending data

## Frontend Structure

Built with **TypeScript** + React + Vite, styled with Tailwind CSS v4 + daisyUI.

**Current components:**
- `<TransactionList />` - Display imported transactions from bank statements

**Planned components:**
- `<FileList />` - Lists `.xlsx` files and import status
- `<SpendingChart />` - Monthly spending visualization
- `<CategoryBreakdown />` - Pie chart by category
- `<InsightsPanel />` - Claude-generated savings suggestions

**IMPORTANT**: Never create components for manual transaction entry. All transactions come from Excel imports only.

## Claude MCP Integration

When implementing categorization logic:
1. Identify ambiguous transactions without clear rule matches
2. Send transaction context to Claude MCP: `{"transaction": "TESCO STORES 1234", "amount": -42.75, "date": "2025-07-05"}`
3. Claude returns: `{"category": "Groceries", "confidence": 0.93}`
4. Store category assignment and optionally create new rule for similar transactions

Example insight generation:
> "Your average grocery spending in the past 3 months increased by 12%. You could save ~£45/month by reducing supermarket frequency."

## Santander Excel Format

Expected column structure:
- Date
- Description (merchant/transaction text)
- Debit (expenses)
- Credit (income)
- Balance

Parser must handle UK number formats (£ symbol, comma thousands separator).

## Privacy & Security Considerations

- Never transmit raw bank data to external services
- Claude MCP interactions should only include anonymized transaction descriptions and amounts
- Support optional offline mode (disable AI categorization)
- Data folder location: `~/FinanceData/` (configurable)

## Repository Structure

```
/backend/          Backend service (Go or Python)
  /mcp/            MCP component implementations
  /db/             Database migrations and schemas
  /api/            HTTP handlers and routing
/frontend/         React + Vite + Tailwind UI
  /src/
    /components/   Reusable UI components
    /pages/        Main views (Dashboard, Transactions, Files, Insights)
/data/             Local Excel statement files (not in git)
  /FinanceData/
```

## Database Layer

### Database Module Selection
The application uses conditional imports to switch between SQLite and PostgreSQL:

```python
# In app.py or any backend file:
import database_init as database

# Then use database functions:
transactions = database.get_all_transactions()
database.add_transaction(date, description, amount, category, source_file, merchant)
```

The correct database is automatically selected based on `DB_TYPE` environment variable:
- `DB_TYPE=postgres` → Uses `database_postgres.py` (production, Docker)
- `DB_TYPE=sqlite` → Uses `database.py` (legacy, local file)

### Database Functions Available

**Transaction Management:**
- `get_all_transactions()` - Get all transactions
- `add_transaction()` - Add single transaction
- `get_transaction_by_id()` - Get by ID
- `update_transaction_category()` - Update category
- `update_merchant()` - Update merchant name

**Amazon Integration:**
- `import_amazon_orders()` - Bulk import
- `get_amazon_orders()` - Get with filters
- `match_amazon_transaction()` - Record match
- `get_amazon_statistics()` - Get stats

**Apple Integration:**
- `import_apple_transactions()` - Bulk import
- `get_apple_transactions()` - Get with filters
- `match_apple_transaction()` - Record match
- `get_apple_statistics()` - Get stats

**Huququllah Classification:**
- `update_transaction_huququllah()` - Classify transaction
- `get_unclassified_transactions()` - Get unclassified
- `get_huququllah_summary()` - Get summary stats

See `backend/database_postgres.py` for complete function signatures.

### Migration from SQLite to PostgreSQL

To migrate existing SQLite data:

```bash
cd /mnt/c/dev/spending

# 1. Start PostgreSQL
docker-compose up -d

# 2. Run migration script
cd backend
source venv/bin/activate
python migrate_to_postgres.py

# 3. Update .env
# DB_TYPE=postgres (default in .env.example)

# 4. Restart backend
# Backend will now use PostgreSQL
```

See `docs/POSTGRES_MIGRATION.md` for detailed instructions.

## Future Extensions

- Support for PDF and CSV formats
- Multi-bank support (TrueLayer integration)
- Budget and goal tracking
- Encrypted data store
- Export reports (PDF/CSV)
- Machine learning for category predictions
- Duplicate transaction detection
