# Business Logic Services

This directory contains the service layer, separating business logic from
HTTP routing concerns.

## Structure

```
backend/services/
├── __init__.py              # Service exports
├── gmail_service.py         # Gmail business logic
├── truelayer_service.py     # Bank sync logic
├── enrichment_service.py    # LLM enrichment orchestration
├── matching_service.py      # Cross-source matching
├── category_service.py      # Category inference
└── import_service.py        # Import orchestration
```

## Service Pattern

Services contain business logic and coordinate between database and external APIs:

```python
"""Gmail Sync Service - Business Logic"""

from database import gmail
from mcp import gmail_client, gmail_parser

def start_sync(user_id: int) -> dict:
    """
    Orchestrate Gmail sync process.
    
    - Validates connection
    - Fetches emails via API
    - Parses receipts
    - Stores in database
    - Returns job status
    """
    # Business logic here
    connection = gmail.get_gmail_connection(user_id)
    if not connection:
        raise ValueError("No Gmail connection found")
    
    job = gmail.create_gmail_sync_job(connection['id'])
    # ... orchestration logic
    return {'job_id': job['id'], 'status': 'started'}
```

## Principles

1. **Pure Business Logic**: No HTTP concerns (request/response)
2. **Testable**: Easy to unit test without Flask
3. **Reusable**: Can be called from routes, CLI, background jobs
4. **Single Responsibility**: Each service handles one domain
5. **Database Coordination**: Uses database modules, not direct SQL
