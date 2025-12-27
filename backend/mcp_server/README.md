# Spending App MCP Server

Model Context Protocol server that enables AI assistants to autonomously run spending app operations.

## Features

- **32 MCP Tools** across 8 categories
- **Smart Defaults** - 90% of calls work without parameters
- **Comprehensive Error Handling** with retry logic
- **Async Job Support** for long-running operations
- **Health Monitoring** and analytics
- **Transaction Search** - Query and analyze transaction data

## Quick Start

### Claude Code CLI

The MCP server is automatically available in Claude Code. Just ask Claude to run operations:

```
"Sync all my data sources from the last month"
"Check if any data sources are stale"
"Run the full pipeline - sync, match, and enrich"
"Get enrichment statistics"
```

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "spending-app": {
      "command": "/home/kaihaan/prj/spending/backend/mcp_server/run.sh",
      "args": [],
      "env": {
        "FLASK_API_URL": "http://localhost:5000",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

## Available Tools

### High-Level Workflows (5 tools)

**`sync_all_sources`** - Sync all data sources (bank, Gmail, Apple, Amazon)
```python
# No parameters needed - uses smart defaults
sync_all_sources()

# Or customize
sync_all_sources(date_from="2024-12-01", date_to="2024-12-31")
```

**`run_full_pipeline`** - Complete pipeline: sync → parse → match → enrich
```python
run_full_pipeline()  # Complete pipeline with defaults
run_full_pipeline(enrichment_provider="openai", batch_size=20)
```

**`run_pre_enrichment`** - Run all matching operations before LLM enrichment
```python
run_pre_enrichment()  # Match all sources
run_pre_enrichment(sources=["amazon", "gmail"])  # Match specific sources
```

**`check_sync_status`** - Get status of active/recent sync operations
```python
check_sync_status()  # Active jobs only
check_sync_status(include_completed=True, hours_back=48)
```

**`get_source_coverage`** - Check data coverage and staleness
```python
get_source_coverage()  # Shows which sources need syncing
```

### Sync Operations (6 tools)

**`sync_bank_transactions`** - Sync TrueLayer bank transactions
```python
sync_bank_transactions()
```

**`sync_gmail_receipts`** - Sync Gmail receipt emails
```python
sync_gmail_receipts()  # Auto sync last 30 days
sync_gmail_receipts(sync_type="full", force_reparse=True)
```

**`poll_job_status`** - Poll async job until completion
```python
poll_job_status(job_id="42", job_type="gmail_sync")
```

### Matching Operations (4 tools)

**`match_amazon_orders`** - Match Amazon to bank transactions
```python
match_amazon_orders()
```

**`match_apple_purchases`** - Match Apple to bank transactions
```python
match_apple_purchases()
```

**`match_gmail_receipts`** - Match Gmail to bank transactions
```python
match_gmail_receipts()
```

**`run_unified_matching`** - Run all matching in parallel
```python
run_unified_matching()
run_unified_matching(sources=["amazon", "gmail"])
```

### Enrichment (2 tools)

**`enrich_transactions`** - Trigger LLM enrichment
```python
enrich_transactions()  # Enrich all unenriched
enrich_transactions(provider="anthropic", batch_size=20)
```

**`get_enrichment_stats`** - Get enrichment statistics
```python
get_enrichment_stats()
```

### Analytics & Monitoring (5 tools)

**`get_endpoint_health`** - Check API health
```python
get_endpoint_health()
get_endpoint_health(include_details=True)
```

**`get_system_analytics`** - System analytics
```python
get_system_analytics()
get_system_analytics(time_period="week")
```

**`get_error_logs`** - Get failure logs
```python
get_error_logs()
get_error_logs(limit=100, severity="error")
```

### Status (3 tools)

**`get_connection_status`** - Check OAuth connections
```python
get_connection_status()
```

**`get_data_summary`** - Summary of all data
```python
get_data_summary()
```

**`get_recent_activity`** - Recent activity feed
```python
get_recent_activity()
get_recent_activity(hours_back=48, limit=50)
```

### Search & Query (4 tools)

**`search_transactions`** - Search transactions by criteria
```python
# Search by merchant
search_transactions(merchant="Amazon")

# Search by amount range
search_transactions(min_amount=50, max_amount=200)

# Search by date and category
search_transactions(
    date_from="2024-12-01",
    category="Shopping",
    enriched_only=True
)

# Search by description
search_transactions(description="subscription")
```

**`get_transaction_details`** - Get full transaction details
```python
get_transaction_details(transaction_id=12345)
```

**`get_enrichment_details`** - Get enrichment details and stats
```python
# Get overall enrichment stats
get_enrichment_details()

# Get enrichment for specific transaction
get_enrichment_details(transaction_id=12345)

# Get failed enrichments
get_enrichment_details(include_failed=True, limit=50)
```

**`search_enriched_transactions`** - Search enriched transactions
```python
# Find all enriched transactions
search_enriched_transactions()

# Find high-confidence Anthropic enrichments
search_enriched_transactions(
    provider="anthropic",
    min_confidence=0.9
)

# Find grocery categorizations
search_enriched_transactions(
    category="Groceries",
    date_from="2024-12-01"
)
```

### Gmail Debugging (3 tools)

**`debug_gmail_receipt`** - Get comprehensive debugging info for a specific receipt
```python
# Debug by receipt ID
debug_gmail_receipt(receipt_id=123)

# Debug by Gmail message ID
debug_gmail_receipt(message_id="18f3a1b2c3d4e5f6")

# Returns:
# - Parsed data (merchant, amount, line_items)
# - Parsing metadata (method, confidence, status, errors)
# - Transaction match details
# - Line items type debugging (is_list, count, structure)
# - Actionable recommendations
```

**`search_gmail_receipts`** - Search receipts by criteria to find parsing issues
```python
# Find receipts missing line items
search_gmail_receipts(has_line_items=False)

# Find failed Amazon parses
search_gmail_receipts(
    merchant="Amazon",
    parsing_status="failed"
)

# Find unmatched receipts from last week
search_gmail_receipts(
    has_transaction_match=False,
    date_from="2024-12-20"
)

# Returns receipts with summary statistics
```

**`analyze_parsing_gaps`** - Generate comprehensive data quality report
```python
# Analyze all receipts from last 30 days
analyze_parsing_gaps()

# Analyze last 90 days
analyze_parsing_gaps(date_from="2024-10-01")

# Returns:
# - Overall parsing statistics by status and method
# - Per-merchant success rates and quality metrics
# - Identified issues (missing line_items, failed parses, low confidence)
# - Prioritized, actionable recommendations for parser improvements
```

## Configuration

Environment variables (set in `.claude/mcp-settings.json` or `.env`):

```bash
FLASK_API_URL=http://localhost:5000      # Flask backend URL
FLASK_API_TIMEOUT=30                      # Request timeout (seconds)
DEFAULT_USER_ID=1                         # Default user ID
DEFAULT_DATE_RANGE_DAYS=30                # Default date range
LOG_LEVEL=INFO                            # Logging level
ENABLE_AUTO_RETRY=true                    # Enable automatic retries
MAX_RETRY_ATTEMPTS=3                      # Max retry attempts
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Claude Code CLI / Claude Desktop               │
└────────────┬────────────────────────────────────┘
             │ MCP Protocol (stdio)
             ▼
┌─────────────────────────────────────────────────┐
│  MCP Server (Python)                            │
│  - 32 MCP tools                                 │
│  - Smart defaults                               │
│  - Error handling                               │
└────────────┬────────────────────────────────────┘
             │ HTTP (requests library)
             ▼
┌─────────────────────────────────────────────────┐
│  Flask Backend (http://localhost:5000)          │
│  - API endpoints                                │
│  - Business logic                               │
│  - Database access                              │
└─────────────────────────────────────────────────┘
```

## Example Workflows

### Daily Sync Workflow
```
1. sync_all_sources()           # Sync all data
2. run_pre_enrichment()         # Match receipts
3. enrich_transactions()        # Categorize with AI
4. get_enrichment_stats()       # Check progress
```

### Troubleshooting Workflow
```
1. get_endpoint_health()        # Check system health
2. get_error_logs()             # Review errors
3. get_source_coverage()        # Check data staleness
4. sync_gmail_receipts()        # Re-sync if needed
```

### Complete Pipeline (One Command)
```
run_full_pipeline()  # Does all of the above automatically
```

## Development

### Running the Server Standalone
```bash
source backend/venv/bin/activate
python3 -m backend.mcp_server.server
```

### Testing
```bash
# Run integration tests
pytest backend/mcp_server/tests/

# Test individual tool
python3 -c "
from backend.mcp_server.tools.workflows import sync_all_sources
import asyncio
result = asyncio.run(sync_all_sources())
print(result)
"
```

### Logging

Server logs go to stderr by default. To enable file logging:

```bash
export LOG_FILE=/tmp/mcp-server.log
```

View logs:
```bash
tail -f /tmp/mcp-server.log
```

## Troubleshooting

### "Flask API health check failed"
- Ensure Flask backend is running: `docker-compose up -d backend`
- Check Flask is accessible: `curl http://localhost:5000/api/health`

### "Connection error"
- Check network connectivity
- Verify FLASK_API_URL is correct
- Ensure no firewall blocking localhost:5000

### "Tool not found"
- Restart Claude Code/Desktop to reload MCP configuration
- Check `.claude/mcp-settings.json` is valid JSON
- Verify `run.sh` script has execute permissions

### "Job timeout"
- Increase DEFAULT_JOB_TIMEOUT in config
- Check Celery workers are running: `docker ps | grep celery`
- View Celery logs: `docker logs -f spending-celery`

## Support

For issues or questions:
- Check logs: `tail -f /tmp/mcp-server.log`
- Verify configuration: Check `.claude/mcp-settings.json`
- Test Flask API: `curl http://localhost:5000/api/health`
