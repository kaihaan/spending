# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## CRITICAL DEVELOPMENT RULES

### 🔴 ALWAYS Follow These Rules:

1. **Python Development**: ALWAYS activate the Python virtual environment before running any Python commands or starting the backend server:
   ```bash
   source /home/kaihaan/projects/spending/backend/venv/bin/activate
   ```

2. **Transaction Data Source**: Transactions MUST ONLY come from imported Santander Excel bank statements. NEVER create UI components or API endpoints that allow users to manually add, edit, or create transactions. This is a hard requirement for data integrity.

3. **TypeScript**: The frontend is built with TypeScript. All new components and files must use TypeScript (.tsx/.ts), not JavaScript (.jsx/.js).

4. **Backend Server**: When starting the backend, use absolute paths and activate venv:
   ```bash
   source /home/kaihaan/projects/spending/backend/venv/bin/activate && cd /home/kaihaan/projects/spending/backend && python app.py
   ```

## Project Overview

This is a **privacy-first local personal finance analysis service** that parses Santander Excel bank statements, categorizes transactions using AI (via Claude MCP), and provides spending insights through a web dashboard.

Key principles:
- All data processing is **local-only** (no cloud uploads)
- Uses Claude via MCP for AI-assisted transaction categorization
- Built with **TypeScript** + React + Tailwind + daisyUI frontend and Python backend
- Data stored in SQLite
- **Transactions only imported from bank statements - no manual entry allowed**

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

### Backend (Python + Flask)
```bash
# Always activate venv first!
source /home/kaihaan/projects/spending/backend/venv/bin/activate
cd /home/kaihaan/projects/spending/backend
python app.py
# Backend runs on http://localhost:5000
```

### Frontend (TypeScript + React + Vite)
```bash
cd /home/kaihaan/projects/spending/frontend
npm run dev
# Frontend runs on http://localhost:5173
```

### Important Notes:
- Backend MUST be started with venv activated
- Frontend is fully TypeScript - no JavaScript files
- Database is auto-initialized on backend startup

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

## Future Extensions

- Support for PDF and CSV formats
- Multi-bank support
- Budget and goal tracking
- Encrypted data store
- Export reports (PDF/CSV)
