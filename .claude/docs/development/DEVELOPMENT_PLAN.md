# Development Plan - Personal Finance Analysis Service

## Tech Stack: Python + React

**Backend:** Python 3.10+ with Flask, pandas, SQLite, Anthropic Claude SDK
**Frontend:** React 18 + Vite + Tailwind CSS + daisyUI

---

## Phase 1: Minimal Full-Stack POC (2-3 days)
**Goal:** Working full-stack app with basic API communication.

### Backend Setup
```bash
mkdir backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install flask flask-cors pandas openpyxl
```

### File Structure
```
backend/
├── app.py              # Main Flask application
├── database.py         # SQLite connection and schema
├── requirements.txt    # Dependencies
└── mcp/               # MCP components (add later)
```

### Backend Implementation
**`backend/database.py`:**
```python
import sqlite3

def init_db():
    conn = sqlite3.connect('finance.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT DEFAULT 'Other',
            source_file TEXT,
            merchant TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
```

**`backend/app.py`:**
```python
from flask import Flask, jsonify, request
from flask_cors import CORS
import database

app = Flask(__name__)
CORS(app)

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok'})

@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    # TODO: Query from database
    return jsonify([])

@app.route('/api/transactions', methods=['POST'])
def add_transaction():
    data = request.json
    # TODO: Insert into database
    return jsonify({'id': 1, **data}), 201

if __name__ == '__main__':
    database.init_db()
    app.run(debug=True, port=5000)
```

### Frontend Setup
```bash
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm install -D tailwindcss postcss autoprefixer
npm install daisyui axios
npx tailwindcss init -p
```

**`frontend/tailwind.config.js`:**
```javascript
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  plugins: [require('daisyui')],
}
```

### Frontend Components
- Transaction list component
- Form to manually add transaction
- Basic layout with daisyUI styling

### Deliverable
✅ Backend API running on `http://localhost:5000`
✅ Frontend running on `http://localhost:5173`
✅ Can add and view transactions via UI

---

## Phase 2: Excel Import (2-3 days)
**Goal:** Parse and import Santander Excel statements.

### Backend Changes
**Create `backend/mcp/excel_parser.py`:**
```python
import pandas as pd
from datetime import datetime

def parse_santander_excel(file_path):
    """Parse Santander Excel format into normalized transactions."""
    df = pd.read_excel(file_path)

    # Expected columns: Date, Description, Debit, Credit, Balance
    # Handle UK currency format (£ symbol, commas)

    transactions = []
    for _, row in df.iterrows():
        amount = -float(row['Debit']) if pd.notna(row['Debit']) else float(row['Credit'])

        transactions.append({
            'date': row['Date'].strftime('%Y-%m-%d'),
            'description': row['Description'].strip(),
            'amount': amount,
            'merchant': extract_merchant(row['Description']),
            'source_file': file_path.split('/')[-1]
        })

    return transactions

def extract_merchant(description):
    """Extract merchant name from transaction description."""
    # Remove card numbers, dates, locations
    # e.g., "TESCO STORES 1234 LONDON" -> "TESCO STORES"
    parts = description.split()
    return ' '.join(parts[:2])  # Simple heuristic
```

**Create `backend/mcp/file_manager.py`:**
```python
import os
from pathlib import Path

DATA_FOLDER = Path.home() / 'FinanceData'

def list_excel_files():
    """List all Excel files in data folder."""
    if not DATA_FOLDER.exists():
        DATA_FOLDER.mkdir(parents=True)
        return []

    files = []
    for file in DATA_FOLDER.glob('*.xlsx'):
        files.append({
            'name': file.name,
            'size': file.stat().st_size,
            'modified': file.stat().st_mtime,
            'imported': check_if_imported(file.name)
        })
    return files
```

**New API Endpoints:**
```python
@app.route('/api/files', methods=['GET'])
def get_files():
    from mcp.file_manager import list_excel_files
    return jsonify(list_excel_files())

@app.route('/api/import', methods=['POST'])
def import_file():
    filename = request.json['filename']
    from mcp.excel_parser import parse_santander_excel
    from mcp.file_manager import DATA_FOLDER

    transactions = parse_santander_excel(DATA_FOLDER / filename)
    # Insert transactions into database

    return jsonify({'imported': len(transactions)})
```

### Frontend Changes
- New `<FileList />` component
- Import button with loading state
- Toast notifications for success/error

### Test Data
Create sample Excel file: `~/FinanceData/2025-01-santander.xlsx`

### Deliverable
✅ Scan and display available Excel files
✅ Import button parses and stores transactions
✅ Transactions appear in list after import

---

## Phase 3: Rule-Based Categorization (2-3 days)
**Goal:** Auto-categorize transactions using keyword rules.

### Backend Changes
**Create `backend/mcp/categorizer.py`:**
```python
import re

CATEGORY_RULES = {
    'Groceries': ['tesco', 'sainsbury', 'asda', 'morrisons', 'aldi', 'lidl'],
    'Transport': ['tfl', 'uber', 'trainline', 'national rail', 'shell', 'bp'],
    'Dining': ['restaurant', 'cafe', 'pizza', 'mcdonalds', 'kfc', 'nando'],
    'Entertainment': ['cinema', 'spotify', 'netflix', 'amazon prime'],
    'Utilities': ['thames water', 'british gas', 'edf', 'vodafone', 'ee'],
    'Shopping': ['amazon', 'ebay', 'argos', 'john lewis', 'zara', 'h&m'],
}

def categorize_transaction(description):
    """Match transaction description against category rules."""
    description_lower = description.lower()

    for category, keywords in CATEGORY_RULES.items():
        for keyword in keywords:
            if keyword in description_lower:
                return category

    return 'Other'  # Uncategorized

def categorize_transactions(transactions):
    """Bulk categorize transactions."""
    for txn in transactions:
        if not txn.get('category') or txn['category'] == 'Other':
            txn['category'] = categorize_transaction(txn['description'])
    return transactions
```

**Database Updates:**
```python
# Add categories table
c.execute('''
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        rule_pattern TEXT,
        ai_suggested BOOLEAN DEFAULT 0
    )
''')

# Seed default categories
default_categories = ['Groceries', 'Transport', 'Dining', 'Entertainment',
                      'Utilities', 'Shopping', 'Income', 'Other']
for cat in default_categories:
    c.execute('INSERT OR IGNORE INTO categories (name) VALUES (?)', (cat,))
```

**New API Endpoints:**
```python
@app.route('/api/categories', methods=['GET'])
def get_categories():
    # Return all categories
    pass

@app.route('/api/transactions/<int:id>/category', methods=['PUT'])
def update_category(id):
    # Manually update transaction category
    pass
```

### Frontend Changes
- Category badges with colors (daisyUI)
- Dropdown to manually change category
- Filter transactions by category
- Basic dashboard showing spending by category

### Deliverable
✅ Transactions auto-categorized on import
✅ Manual category override via dropdown
✅ Dashboard shows category breakdown

---

## Phase 4: Claude AI Integration (3-4 days)
**Goal:** Use Claude for ambiguous transactions and insights.

### Backend Setup
```bash
pip install anthropic
```

**Create `backend/mcp/claude_service.py`:**
```python
import anthropic
import os

client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))

def categorize_with_ai(transaction, available_categories):
    """Use Claude to categorize ambiguous transaction."""

    prompt = f"""Categorize this bank transaction:

Description: {transaction['description']}
Amount: £{abs(transaction['amount']):.2f}
Date: {transaction['date']}

Available categories: {', '.join(available_categories)}

Respond with JSON only:
{{"category": "CategoryName", "confidence": 0.95, "reason": "brief explanation"}}"""

    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    )

    import json
    return json.loads(message.content[0].text)

def generate_insights(transactions, period='last_3_months'):
    """Generate spending insights using Claude."""

    # Aggregate transaction data
    summary = aggregate_transactions(transactions)

    prompt = f"""Analyze these spending patterns:

Period: {period}
Total spent: £{summary['total']:.2f}
Top categories: {summary['top_categories']}
Transaction count: {summary['count']}

Provide:
1. Top 3 spending observations
2. Any unusual patterns
3. One specific, actionable savings opportunity

Keep response under 200 words."""

    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    return message.content[0].text
```

**New API Endpoints:**
```python
@app.route('/api/categorize/ai', methods=['POST'])
def ai_categorize():
    # Categorize uncategorized transactions with Claude
    pass

@app.route('/api/insights', methods=['GET'])
def get_insights():
    from mcp.claude_service import generate_insights
    # Get recent transactions and generate insights
    pass
```

### Frontend Changes
- "Categorize with AI" button for "Other" transactions
- Show AI confidence and reasoning
- Insights panel component with refresh button
- Settings toggle to enable/disable AI features

### Environment Setup
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### Deliverable
✅ AI categorization for ambiguous transactions
✅ Insights panel with Claude recommendations
✅ User control over AI features

---

## Phase 5: Analytics & Visualizations (3-4 days)
**Goal:** Visual dashboard with charts and trends.

### Backend Changes
**Create `backend/mcp/analytics_engine.py`:**
```python
from datetime import datetime, timedelta
import sqlite3

def compute_monthly_trends(months=6):
    """Calculate spending trends over time."""
    # Group by month, sum amounts, categorize
    pass

def category_breakdown(period='3m'):
    """Spending by category for period."""
    pass

def top_merchants(limit=10):
    """Most frequent merchants."""
    pass

def spending_summary():
    """Key metrics: total, average, change %."""
    pass
```

**New API Endpoints:**
```python
@app.route('/api/analytics/summary')
def analytics_summary():
    pass

@app.route('/api/analytics/trends')
def analytics_trends():
    pass

@app.route('/api/analytics/merchants')
def analytics_merchants():
    pass
```

### Frontend Components
- `<D3LineChart />` - Line chart (D3.js)
- `<D3BarChart />` - Bar chart (D3.js)
- `<MetricsCards />` - Summary stats
- Time period selector (1M, 3M, 6M, 1Y)

### Deliverable
✅ Visual dashboard with multiple charts
✅ Monthly trend analysis
✅ Interactive time period selection

---

## Phase 6: Polish & Features (3-5 days)
**Goal:** Production-ready application.

### Frontend Polish
- Light/dark mode toggle (daisyUI themes)
- Responsive design (mobile-friendly)
- Loading states and error handling
- Search and filter transactions
- Pagination for large datasets

### Backend Enhancements
- Input validation
- Error handling with proper HTTP codes
- Database indexes for performance
- Logging

### Additional Features
- Export transactions to CSV
- Category management UI (CRUD)
- Settings page (data folder, API key)
- User guide / help page

### Testing
- Unit tests for parsers (`pytest`)
- API endpoint tests
- Sample data for demos

### Documentation
- Update README with installation steps
- API documentation
- Development commands in CLAUDE.md

### Deliverable
✅ Polished, user-friendly application
✅ Full documentation
✅ Ready for personal use

---

## Quick Start Commands

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python app.py
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Data Folder
```bash
mkdir -p ~/FinanceData
# Place Santander Excel files here
```

---

## Project Structure
```
spending/
├── backend/
│   ├── app.py
│   ├── database.py
│   ├── requirements.txt
│   ├── finance.db (generated)
│   └── mcp/
│       ├── excel_parser.py
│       ├── file_manager.py
│       ├── categorizer.py
│       ├── claude_service.py
│       └── analytics_engine.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   └── App.jsx
│   ├── package.json
│   └── tailwind.config.js
├── data/
│   └── FinanceData/ (user's local folder)
├── CLAUDE.md
├── DEVELOPMENT_PLAN.md
└── README.md
```

---

## Timeline: 15-22 days total

Ready to start Phase 1?
