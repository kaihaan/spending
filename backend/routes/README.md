# Flask Routes - Blueprint Organization

This directory contains Flask blueprints organized by domain, extracted from the
monolithic app.py (5,121 lines, 159 routes).

## Structure

```
backend/routes/
├── __init__.py              # Blueprint registry
├── gmail.py                 # Gmail sync & receipts (28 routes)
├── truelayer.py             # Bank connections & sync (17 routes)
├── amazon.py                # Amazon orders & matching (16 routes)
├── amazon_business.py       # Amazon Business (9 routes)
├── rules.py                 # Category & merchant rules (14 routes)
├── enrichment.py            # LLM enrichment (11 routes)
├── apple.py                 # Apple transactions (11 routes)
├── categories.py            # Categories v1 & v2 (17 routes)
├── direct_debit.py          # Direct debit mappings (6 routes)
├── transactions.py          # Transaction endpoints (5 routes)
├── settings.py              # User settings (5 routes)
├── matching.py              # Cross-source matching (4 routes)
├── migrations.py            # Data migrations (3 routes)
├── huququllah.py            # Islamic finance (3 routes)
└── testing.py               # Testing endpoints (~10 routes)
```

## Blueprint Pattern

Each blueprint follows this structure:

```python
from flask import Blueprint, request, jsonify
from services import gmail_service

gmail_bp = Blueprint('gmail', __name__, url_prefix='/api/gmail')

@gmail_bp.route('/sync', methods=['POST'])
def sync_gmail():
    """Thin controller - delegates to service layer."""
    result = gmail_service.start_sync(user_id=1)
    return jsonify(result)
```

## Principles

1. **Thin Controllers**: Routes handle HTTP concerns only
2. **Service Delegation**: Business logic in services/
3. **Clear Naming**: Route names match domain modules
4. **Error Handling**: Consistent error responses
5. **Documentation**: Docstrings for all routes
