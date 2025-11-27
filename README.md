# Personal Finance Analysis Service

A **privacy-first local personal finance tracker** that parses Santander bank statements and TrueLayer bank connections, categorizes transactions using AI, and provides spending insights through a web dashboard.

## Key Features

- 📊 **Import & Analyze** - Parse Santander Excel bank statements automatically
- 🏦 **Bank Integration** - TrueLayer API for real-time bank synchronization
- 🤖 **AI-Powered Categorization** - Uses Claude MCP for intelligent transaction classification
- 📈 **Spending Insights** - Track trends, identify patterns, and get savings recommendations
- 🔒 **Privacy-First** - All data processing is **local-only** (no cloud uploads)
- 💾 **PostgreSQL Storage** - Production-ready database with ACID compliance
- 📦 **Docker Ready** - PostgreSQL runs in Docker for easy setup

## Tech Stack

### Frontend
- **TypeScript** + React 19
- **Vite** - Fast build tool
- **Tailwind CSS v4** + daisyUI - Modern styling
- **Recharts** - Data visualization
- **Axios** - API communication

### Backend
- **Python 3** + Flask
- **pandas** + openpyxl - Excel parsing
- **PostgreSQL** (production) or SQLite (legacy) - Database
- **psycopg2** - PostgreSQL adapter
- **Docker** - Container for PostgreSQL
- **Claude API** - AI-assisted categorization via MCP
- **TrueLayer API** - Bank data synchronization

## Prerequisites

Before you begin, ensure you have the following installed:

- **Node.js** (v18 or higher) and **npm**
- **Python 3.8+**
- **Docker** and **Docker Compose** (for PostgreSQL database)
- **Git**

## Setup Instructions

### 1. Clone the Repository

```bash
git clone <repository-url>
cd spending
```

### 2. Environment Setup

```bash
# Copy environment template
cp .env.example .env

# Edit .env and configure:
# - POSTGRES_PASSWORD (secure password)
# - POSTGRES_PORT (default: 5433)
# - DB_TYPE=postgres (default)
# - ANTHROPIC_API_KEY (for Claude MCP)
```

### 3. PostgreSQL Database Setup

```bash
# Start PostgreSQL container
docker-compose up -d

# Verify container is running
docker-compose ps

# Check initialization logs
docker-compose logs postgres
```

### 4. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create a Python virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt
```

### 5. Data Migration (if you have existing SQLite data)

```bash
# Ensure you're in the backend directory with venv activated
cd backend
source venv/bin/activate

# Run the migration script
python migrate_to_postgres.py

# Follow the prompts - it will validate and ask for confirmation
```

### 6. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install npm dependencies
npm install
```

## Running the Development Servers

You'll need **three terminal windows** - one for Docker, one for the backend, and one for the frontend.

### Terminal 0: Docker PostgreSQL Database (First!)

```bash
# Start PostgreSQL container (run from project root)
docker-compose up

# Or run in background
docker-compose up -d
```

Wait for the message: `PostgreSQL init process complete; ready for start up.`

### Terminal 1: Backend Server

```bash
# Navigate to backend directory
cd backend

# Always activate venv first!
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Ensure environment variables are set
export DB_TYPE=postgres
export ANTHROPIC_API_KEY=your_key_here

# Start the Flask server
python app.py
```

The backend API will run on **http://localhost:5000**

### Terminal 2: Frontend Server

```bash
# Navigate to frontend directory
cd frontend

# Start the Vite dev server
npm run dev
```

The frontend will run on **http://localhost:5173**

### Connecting to Database (Optional - for debugging)

```bash
# Access PostgreSQL shell
docker exec -it spending-postgres psql -U spending_user -d spending_db

# List tables
\dt

# Exit shell
\q
```

## Project Structure

```
spending/
├── backend/                # Python backend service
│   ├── app.py             # Flask application entry point
│   ├── database.py        # SQLite database layer
│   ├── requirements.txt   # Python dependencies
│   ├── mcp/              # MCP component implementations
│   └── venv/             # Python virtual environment
│
├── frontend/              # React frontend
│   ├── src/
│   │   ├── components/   # Reusable UI components
│   │   ├── pages/        # Main views
│   │   └── main.tsx      # App entry point
│   ├── package.json
│   └── vite.config.ts
│
├── sample/               # Sample bank statements for testing
├── CLAUDE.md            # AI assistant instructions
└── README.md            # This file
```

## API Endpoints

- `GET /api/files` - List available Excel files in data folder
- `POST /api/import` - Parse and import selected Excel file
- `GET /api/categories` - Return all categories and classification rules
- `GET /api/summary` - Aggregated spending summary
- `GET /api/trends` - Timeseries spending data

## Important Notes

### Data Source Policy
**Transactions MUST ONLY come from imported Santander Excel bank statements.** The application does not support manually adding, editing, or creating transactions. This is a hard requirement for data integrity.

### Virtual Environment
Always activate the Python virtual environment before running any backend commands:
```bash
source /home/kaihaan/projects/spending/backend/venv/bin/activate
```

### TypeScript
The frontend is fully TypeScript. All new components must use `.tsx` or `.ts` extensions (not `.jsx` or `.js`).

### Privacy & Security
- Raw bank data never leaves your machine
- Claude MCP only receives anonymized transaction descriptions and amounts
- All analysis is performed locally
- Optional offline mode available (disables AI categorization)

## Santander Excel Format

The parser expects the following column structure:
- **Date** - Transaction date
- **Description** - Merchant/transaction text
- **Debit** - Expenses (outgoing)
- **Credit** - Income (incoming)
- **Balance** - Account balance after transaction

UK number formats are supported (£ symbol, comma thousands separator).

## Development

### Frontend Scripts
```bash
npm run dev      # Start dev server
npm run build    # Build for production
npm run preview  # Preview production build
npm run lint     # Run ESLint
```

### Database

PostgreSQL database is initialized by Docker during `docker-compose up`. The schema is created from `postgres/init/01_schema.sql` and includes:

- **9 Legacy Tables:** transactions, categories, account_mappings, amazon_orders, etc.
- **8 TrueLayer Tables:** For future bank integration (users, bank_connections, truelayer_transactions, etc.)

**Switching Databases:**
```bash
# Use PostgreSQL (default, production)
export DB_TYPE=postgres

# Use SQLite (legacy, local file)
export DB_TYPE=sqlite
```

**Database Connection:**
- PostgreSQL: `localhost:5433` (or 5432 inside Docker network)
- SQLite: `backend/finance.db`

## Future Roadmap

- ✅ **PostgreSQL Integration** - Production-ready database
- ✅ **Amazon Order Matching** - Link transactions to Amazon purchases
- ✅ **Apple Transaction Matching** - Link transactions to App Store purchases
- 🔄 **TrueLayer Bank Integration** - Real-time bank synchronization (in progress)
- 📱 Support for PDF and CSV bank statements
- 💼 Budget and goal tracking
- 🔐 Encrypted data store
- 📄 Export reports (PDF/CSV)
- 🔄 Recurring transaction detection
- 🧠 Machine learning for category predictions
- ⚠️ Duplicate transaction detection
- 🏦 Multi-bank support (beyond Santander)

## License

Private project - All rights reserved

## Contributing

This is a personal project. For questions or suggestions, please open an issue.
