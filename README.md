# Personal Finance Analysis Service

A **privacy-first local personal finance tracker** that parses Santander bank statements, categorizes transactions using AI, and provides spending insights through a web dashboard.

## Key Features

- 📊 **Import & Analyze** - Parse Santander Excel bank statements automatically
- 🤖 **AI-Powered Categorization** - Uses Claude MCP for intelligent transaction classification
- 📈 **Spending Insights** - Track trends, identify patterns, and get savings recommendations
- 🔒 **Privacy-First** - All data processing is **local-only** (no cloud uploads)
- 💾 **SQLite Storage** - Lightweight database for fast queries

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
- **SQLite** - Database
- **Claude API** - AI-assisted categorization via MCP

## Prerequisites

Before you begin, ensure you have the following installed:

- **Node.js** (v18 or higher) and **npm**
- **Python 3.8+**
- **Git**

## Setup Instructions

### 1. Clone the Repository

```bash
git clone <repository-url>
cd spending
```

### 2. Backend Setup

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

### 3. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install npm dependencies
npm install
```

## Running the Development Servers

You'll need **two terminal windows** - one for the backend and one for the frontend.

### Terminal 1: Backend Server

```bash
# Always activate venv first!
source /home/kaihaan/projects/spending/backend/venv/bin/activate

# Navigate to backend directory
cd /home/kaihaan/projects/spending/backend

# Start the Flask server
python app.py
```

The backend API will run on **http://localhost:5000**

### Terminal 2: Frontend Server

```bash
# Navigate to frontend directory
cd /home/kaihaan/projects/spending/frontend

# Start the Vite dev server
npm run dev
```

The frontend will run on **http://localhost:5173**

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
SQLite database (`finance.db`) is automatically initialized on backend startup. No manual setup required.

## Future Roadmap

- Support for PDF and CSV bank statements
- Multi-bank support
- Budget and goal tracking
- Encrypted data store
- Export reports (PDF/CSV)
- Recurring transaction detection

## License

Private project - All rights reserved

## Contributing

This is a personal project. For questions or suggestions, please open an issue.
