# TrueLayer Batch Import Management - Implementation Plan

**Date:** 2025-11-28
**Status:** Planned (Phased Approach)
**User Requirements:** Date range selection, multi-account selection, batch management, progress tracking, async processing

---

## Overview

This document outlines a phased approach to implement advanced import management for TrueLayer transactions, enabling:
- Historical data imports with custom date ranges
- Incremental updates since last sync
- Multi-select account/card selection
- Batched processing with progress tracking
- Background async execution with queue management
- Post-import scheduled enrichment

**Implementation Timeline:** 6-8 weeks (3 phases)

---

## Phase 1: Foundation (Weeks 1-2)

### Goals
- Add backend date range API endpoints
- Create basic UI for date range selection
- Implement batch processing skeleton
- Add import history tracking

### Phase 1a: Backend - Date Range Management

#### New Database Tables

```sql
-- Track import jobs and history
CREATE TABLE truelayer_import_jobs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    connection_id INTEGER REFERENCES bank_connections(id),
    job_status VARCHAR DEFAULT 'pending', -- pending, running, completed, failed
    job_type VARCHAR, -- 'date_range', 'incremental', 'full_sync'

    -- Date range parameters
    from_date DATE,
    to_date DATE,

    -- Account selection
    account_ids TEXT[] DEFAULT ARRAY[]::TEXT[], -- Array of account IDs to sync
    card_ids TEXT[] DEFAULT ARRAY[]::TEXT[],    -- Array of card IDs to sync

    -- Results tracking
    total_accounts INTEGER DEFAULT 0,
    total_transactions INTEGER DEFAULT 0,
    total_duplicates INTEGER DEFAULT 0,
    total_errors INTEGER DEFAULT 0,

    -- Enrichment scheduling
    auto_enrich BOOLEAN DEFAULT TRUE,
    enrich_after_completion BOOLEAN DEFAULT FALSE,
    enrichment_job_id INTEGER REFERENCES truelayer_import_jobs(id),

    -- Timing
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    estimated_completion TIMESTAMP,

    -- Metadata
    metadata JSONB DEFAULT '{}' -- Store batch size, retry count, etc
);

-- Track per-account import progress
CREATE TABLE truelayer_import_progress (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES truelayer_import_jobs(id) ON DELETE CASCADE,
    account_id INTEGER REFERENCES truelayer_accounts(id),

    status VARCHAR DEFAULT 'pending', -- pending, syncing, completed, failed
    synced INTEGER DEFAULT 0,
    duplicates INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,

    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Track enrichment job history
CREATE TABLE truelayer_enrichment_jobs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    import_job_id INTEGER REFERENCES truelayer_import_jobs(id),

    job_status VARCHAR DEFAULT 'pending', -- pending, running, completed, failed
    transaction_ids INTEGER[] DEFAULT ARRAY[]::INTEGER[],

    total_transactions INTEGER DEFAULT 0,
    successful INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    cached_hits INTEGER DEFAULT 0,

    total_cost NUMERIC DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

#### New Database Functions

```python
# In database_postgres.py

def create_import_job(user_id, connection_id=None, job_type='date_range',
                     from_date=None, to_date=None, account_ids=None,
                     auto_enrich=True):
    """Create new import job and return job_id"""

def get_import_job(job_id):
    """Get import job details with progress"""

def update_import_job_status(job_id, status, estimated_completion=None):
    """Update job status (pending → running → completed/failed)"""

def add_import_progress(job_id, account_id, synced, duplicates, errors):
    """Record per-account progress"""

def get_import_progress(job_id):
    """Get all account-level progress for job"""

def mark_job_completed(job_id, total_txns, total_duplicates, total_errors):
    """Mark job as completed with final counts"""

def get_user_import_history(user_id, limit=50):
    """Get recent import jobs for user"""

def create_enrichment_job(user_id, import_job_id=None, transaction_ids=None):
    """Create enrichment job, return job_id"""

def update_enrichment_job(job_id, status, successful, failed, cost, tokens):
    """Update enrichment job progress"""
```

#### New API Endpoints

**POST /api/truelayer/import/plan**
```json
Request:
{
  "connection_id": 1,
  "from_date": "2024-01-01",
  "to_date": "2024-12-31",
  "account_ids": ["acc_001", "acc_002"],
  "card_ids": [],
  "auto_enrich": true,
  "batch_size": 50
}

Response:
{
  "job_id": 123,
  "status": "planned",
  "estimated_accounts": 2,
  "estimated_transactions": 250,
  "estimated_duration_seconds": 45,
  "date_range": {
    "from": "2024-01-01",
    "to": "2024-12-31"
  }
}
```

**POST /api/truelayer/import/start**
```json
Request:
{
  "job_id": 123
}

Response:
{
  "job_id": 123,
  "status": "running",
  "started_at": "2025-11-28T12:00:00Z",
  "accounts": [
    {
      "account_id": "acc_001",
      "status": "pending"
    },
    {
      "account_id": "acc_002",
      "status": "pending"
    }
  ]
}
```

**GET /api/truelayer/import/status/{job_id}**
```json
Response:
{
  "job_id": 123,
  "status": "running",
  "progress": {
    "completed_accounts": 1,
    "total_accounts": 2,
    "percent": 50
  },
  "accounts": [
    {
      "account_id": "acc_001",
      "display_name": "Current Account",
      "status": "completed",
      "synced": 125,
      "duplicates": 5,
      "errors": 0,
      "completed_at": "2025-11-28T12:10:00Z"
    },
    {
      "account_id": "acc_002",
      "display_name": "Savings Account",
      "status": "syncing",
      "synced": 45,
      "duplicates": 2,
      "errors": 0
    }
  ],
  "estimated_completion": "2025-11-28T12:15:00Z",
  "total_so_far": {
    "synced": 170,
    "duplicates": 7,
    "errors": 0
  }
}
```

**GET /api/truelayer/import/history**
```json
Response:
{
  "imports": [
    {
      "job_id": 123,
      "job_type": "date_range",
      "status": "completed",
      "date_range": {
        "from": "2024-01-01",
        "to": "2024-12-31"
      },
      "accounts_synced": 2,
      "transactions_imported": 170,
      "duplicates": 7,
      "created_at": "2025-11-28T12:00:00Z",
      "completed_at": "2025-11-28T12:15:00Z",
      "duration_seconds": 900
    }
  ]
}
```

#### Implementation Details

**File: `/backend/mcp/truelayer_import_manager.py`** (New)

```python
from datetime import datetime, timedelta
import database_postgres as database

class ImportJob:
    """Manages a batch import job"""

    def __init__(self, job_id):
        self.job_id = job_id
        self.job_data = database.get_import_job(job_id)
        self.progress = {}

    def plan(self, from_date, to_date, account_ids, card_ids):
        """Estimate transaction count and duration"""
        # Query TrueLayer API to count expected transactions
        # Return estimate with error margin
        pass

    def execute(self, use_parallel=False, max_workers=3):
        """Execute import job"""
        # Mark as running
        # For each account in account_ids:
        #   - Call sync_account_transactions with date range
        #   - Update progress
        #   - Handle errors per-account (don't fail entire job)
        # Mark as completed when all accounts done
        pass

    def get_status(self):
        """Get current job status"""
        return database.get_import_progress(self.job_id)

def create_import_job(user_id, connection_id, from_date, to_date, account_ids, auto_enrich=True):
    """Create and return new ImportJob"""
    job_id = database.create_import_job(
        user_id=user_id,
        connection_id=connection_id,
        job_type='date_range',
        from_date=from_date,
        to_date=to_date,
        account_ids=account_ids,
        auto_enrich=auto_enrich
    )
    return ImportJob(job_id)
```

### Phase 1b: Frontend - Date Range Selection UI

#### New Component: `ImportWizard.tsx`

```typescript
// Location: frontend/src/components/TrueLayer/ImportWizard.tsx

interface ImportWizardProps {
  connection: BankConnection;
  accounts: BankAccount[];
  onImportComplete: (job: ImportJob) => void;
}

// Step 1: Date Range Selection
const DateRangeStep = ({ onNext }) => {
  return (
    <div>
      <h3>Select Date Range</h3>
      <div className="grid grid-cols-2 gap-4">
        <button onClick={() => selectPreset('last_7_days')}>
          Last 7 Days
        </button>
        <button onClick={() => selectPreset('last_month')}>
          Last 30 Days
        </button>
        <button onClick={() => selectPreset('last_quarter')}>
          Last 3 Months
        </button>
        <button onClick={() => selectPreset('custom')}>
          Custom Range
        </button>
      </div>

      {/* Custom date picker */}
      {showCustom && (
        <div className="space-y-4 mt-4">
          <input type="date" value={fromDate} onChange={...} />
          <input type="date" value={toDate} onChange={...} />
          <span className="text-sm text-gray-500">
            {estimatedDays} days, ~{estimatedTransactions} transactions
          </span>
        </div>
      )}
    </div>
  );
};

// Step 2: Account Selection
const AccountSelectionStep = ({ accounts, onNext }) => {
  return (
    <div>
      <h3>Select Accounts to Import</h3>
      <label className="checkbox">
        <input type="checkbox" onChange={selectAll} /> All Accounts
      </label>
      {accounts.map(acc => (
        <label key={acc.id} className="checkbox">
          <input
            type="checkbox"
            checked={selected[acc.id]}
            onChange={() => toggleAccount(acc.id)}
          />
          <span>{acc.display_name} ({acc.currency})</span>
          <span className="text-xs text-gray-500">
            Last synced: {formatDate(acc.last_synced_at)}
          </span>
        </label>
      ))}
    </div>
  );
};

// Step 3: Configuration
const ConfigurationStep = ({ onNext }) => {
  return (
    <div>
      <h3>Import Settings</h3>
      <label className="checkbox">
        <input type="checkbox" defaultChecked={true} />
        Auto-enrich transactions with AI
      </label>
      <label>
        <span>Batch Size (transactions per request):</span>
        <input type="number" defaultValue={50} min={10} max={100} />
      </label>
      <label className="checkbox">
        <input type="checkbox" defaultChecked={true} />
        Schedule enrichment after import
      </label>
    </div>
  );
};

// Main Wizard Component
export const ImportWizard = ({ connection, accounts, onImportComplete }) => {
  const [step, setStep] = useState(1);
  const [config, setConfig] = useState({
    fromDate: getLastNDaysDate(90),
    toDate: new Date(),
    accountIds: [],
    autoEnrich: true,
    batchSize: 50,
  });

  const handlePlanImport = async () => {
    const response = await fetch('/api/truelayer/import/plan', {
      method: 'POST',
      body: JSON.stringify({
        connection_id: connection.id,
        from_date: config.fromDate,
        to_date: config.toDate,
        account_ids: config.accountIds,
        auto_enrich: config.autoEnrich,
        batch_size: config.batchSize,
      }),
    });

    const result = await response.json();
    setConfig(prev => ({ ...prev, jobId: result.job_id }));
    setStep(4); // Review step
  };

  const handleStartImport = async () => {
    await fetch(`/api/truelayer/import/start`, {
      method: 'POST',
      body: JSON.stringify({ job_id: config.jobId }),
    });

    // Start polling for progress
    startProgressPolling(config.jobId);
  };

  return (
    <div className="wizard space-y-4">
      {step === 1 && (
        <DateRangeStep onNext={() => setStep(2)} />
      )}
      {step === 2 && (
        <AccountSelectionStep accounts={accounts} onNext={() => setStep(3)} />
      )}
      {step === 3 && (
        <ConfigurationStep onNext={handlePlanImport} />
      )}
      {step === 4 && (
        <ReviewStep jobId={config.jobId} onStart={handleStartImport} />
      )}
      {step === 5 && (
        <ProgressStep jobId={config.jobId} onComplete={onImportComplete} />
      )}
    </div>
  );
};
```

#### New Component: `ImportProgressBar.tsx`

```typescript
// Shows real-time progress with account-by-account breakdown

const ImportProgressBar = ({ jobId }) => {
  const [job, setJob] = useState(null);
  const [progress, setProgress] = useState([]);

  useEffect(() => {
    const interval = setInterval(async () => {
      const response = await fetch(`/api/truelayer/import/status/${jobId}`);
      const data = await response.json();
      setJob(data);
      setProgress(data.accounts);
    }, 2000); // Poll every 2 seconds

    return () => clearInterval(interval);
  }, [jobId]);

  return (
    <div className="space-y-4">
      {/* Overall progress */}
      <div>
        <div className="flex justify-between mb-2">
          <span>Overall Progress</span>
          <span>{job?.progress?.percent}%</span>
        </div>
        <progress
          className="w-full"
          value={job?.progress?.percent}
          max={100}
        />
      </div>

      {/* Per-account progress */}
      {progress.map(acc => (
        <div key={acc.account_id} className="border rounded p-3">
          <div className="flex justify-between items-center mb-2">
            <span className="font-medium">{acc.display_name}</span>
            <StatusBadge status={acc.status} />
          </div>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <div>✓ {acc.synced} synced</div>
            <div>⟳ {acc.duplicates} duplicates</div>
            <div>✗ {acc.errors} errors</div>
          </div>
          {acc.status === 'syncing' && (
            <progress className="w-full mt-2" value={acc.percent} max={100} />
          )}
        </div>
      ))}

      {/* ETA */}
      <div className="text-sm text-gray-600">
        Est. completion: {formatTime(job?.estimated_completion)}
      </div>
    </div>
  );
};
```

### Phase 1c: Modifications to Existing Code

**Update: `backend/mcp/truelayer_sync.py`**

```python
def sync_account_transactions(
    connection_id: int,
    truelayer_account_id: str,
    db_account_id: int,
    access_token: str,
    from_date: str = None,  # NEW: Custom from_date
    to_date: str = None,    # NEW: Custom to_date
    days_back: int = 90,
    use_incremental: bool = True,
    import_job_id: int = None  # NEW: Track which job this is part of
) -> dict:
    """Sync with support for custom date ranges and job tracking"""

    # Determine sync window
    if from_date and to_date:
        # Use explicit date range (historical import)
        sync_from = from_date
        sync_to = to_date
    elif use_incremental and last_synced_at:
        # Use incremental (since last sync)
        sync_from = last_synced_at
        sync_to = datetime.utcnow().isoformat()
    else:
        # Use default window
        sync_from = (datetime.utcnow() - timedelta(days=days_back)).isoformat()
        sync_to = datetime.utcnow().isoformat()

    # Existing sync logic continues...
    # But now it reports back to import_job_id if provided

    if import_job_id:
        database.add_import_progress(
            job_id=import_job_id,
            account_id=db_account_id,
            synced=synced_count,
            duplicates=duplicate_count,
            errors=error_count
        )
```

### Phase 1 Deliverables

- ✅ Database schema for import jobs and history
- ✅ Backend API endpoints for planning and executing imports
- ✅ Import job management module
- ✅ Date range UI component (wizard)
- ✅ Progress tracking component
- ✅ Basic multi-select account UI
- ✅ Import history view

### Phase 1 Timeline: 2 weeks (80 hours)
- Backend endpoints: 20 hours
- Database schema & functions: 15 hours
- ImportWizard component: 25 hours
- Progress tracking: 15 hours
- Integration & testing: 5 hours

---

## Phase 2: Advanced Async & Queuing (Weeks 3-4)

### Goals
- Background async processing with job queues
- Parallel account sync with configurable concurrency
- Real-time progress updates via WebSocket
- Batch size optimization
- Error recovery and retry logic

### Phase 2a: Background Job Queue

#### Technology Choice: Celery + Redis
- Celery for distributed task queue
- Redis as message broker
- Monitoring via Flower

#### Installation
```bash
pip install celery redis flower
```

#### New Files

**`backend/config/celery_config.py`**
```python
from celery import Celery

celery_app = Celery(
    'spending_tasks',
    broker='redis://localhost:6379',
    backend='redis://localhost:6379'
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)
```

**`backend/tasks/truelayer_tasks.py`**
```python
from celery import Task
from config.celery_config import celery_app
from mcp.truelayer_import_manager import ImportJob
import database_postgres as database

@celery_app.task(bind=True)
def execute_import_job(self, job_id):
    """Execute import job in background"""
    job = ImportJob(job_id)

    try:
        database.update_import_job_status(job_id, 'running')

        # Execute with parallelization
        results = job.execute(use_parallel=True, max_workers=3)

        # Mark complete
        database.mark_job_completed(
            job_id,
            total_txns=results['total_synced'],
            total_duplicates=results['total_duplicates'],
            total_errors=results['total_errors']
        )

        # Trigger enrichment if requested
        job_data = database.get_import_job(job_id)
        if job_data['auto_enrich']:
            enrich_imported_transactions.delay(job_id)

    except Exception as e:
        database.update_import_job_status(job_id, 'failed')
        # Log error
        raise

@celery_app.task(bind=True)
def enrich_imported_transactions(self, job_id):
    """Enrich transactions after import"""
    try:
        job_data = database.get_import_job(job_id)
        transaction_ids = database.get_job_transaction_ids(job_id)

        enrichment_job_id = database.create_enrichment_job(
            user_id=job_data['user_id'],
            import_job_id=job_id,
            transaction_ids=transaction_ids
        )

        database.update_import_job_status(
            job_id,
            'enriching',
            enrichment_job_id=enrichment_job_id
        )

        # Call enricher
        from mcp.llm_enricher import get_enricher
        enricher = get_enricher()
        stats = enricher.enrich_transactions(
            transaction_ids=transaction_ids,
            direction='out'
        )

        database.update_enrichment_job(
            enrichment_job_id,
            status='completed',
            successful=stats.successful_enrichments,
            failed=stats.failed_enrichments,
            cost=stats.total_cost,
            tokens=stats.total_tokens_used
        )

        database.update_import_job_status(job_id, 'completed')

    except Exception as e:
        database.update_enrichment_job(enrichment_job_id, status='failed')
        raise
```

### Phase 2b: Real-Time Progress via WebSocket

**`backend/websocket_handlers.py`** (New)
```python
from flask_socketio import SocketIO, emit, join_room, leave_room
import database_postgres as database

socketio = SocketIO(cors_allowed_origins="*")

@socketio.on('subscribe_import_job')
def on_subscribe_import(data):
    job_id = data['job_id']
    user_id = data['user_id']

    # Verify user owns this job
    job = database.get_import_job(job_id)
    if job['user_id'] != user_id:
        emit('error', {'message': 'Unauthorized'})
        return

    join_room(f'import_{job_id}')
    emit('subscribed', {'job_id': job_id})

@socketio.on('unsubscribe_import_job')
def on_unsubscribe_import(data):
    job_id = data['job_id']
    leave_room(f'import_{job_id}')

# Emit progress updates
def broadcast_import_progress(job_id, progress_data):
    socketio.emit('import_progress', progress_data, room=f'import_{job_id}')
```

**Update: `backend/app.py`**
```python
from flask_socketio import SocketIO
from websocket_handlers import socketio

socketio = SocketIO(app)

@app.route('/api/truelayer/import/start', methods=['POST'])
def start_import():
    """Modified to use async task"""
    data = request.json
    job_id = data['job_id']

    # Start background task
    from tasks.truelayer_tasks import execute_import_job
    execute_import_job.delay(job_id)

    # Broadcast that job started
    from websocket_handlers import broadcast_import_progress
    broadcast_import_progress(job_id, {
        'job_id': job_id,
        'status': 'running'
    })

    return jsonify({'status': 'started', 'job_id': job_id})
```

### Phase 2c: Parallel Account Processing

**Update: `backend/mcp/truelayer_import_manager.py`**
```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

class ImportJob:
    def execute(self, use_parallel=False, max_workers=3):
        """Execute with optional parallelization"""

        accounts_to_sync = self._get_accounts_to_sync()
        results = []

        if use_parallel:
            # Parallel execution
            with ThreadPoolExecutor(max_workers=min(max_workers, len(accounts_to_sync))) as executor:
                futures = {
                    executor.submit(
                        self._sync_single_account,
                        account,
                        broadcast_progress=True
                    ): account for account in accounts_to_sync
                }

                for future in as_completed(futures):
                    account = futures[future]
                    try:
                        result = future.result(timeout=60)
                        results.append(result)
                    except Exception as e:
                        results.append({
                            'account_id': account['id'],
                            'status': 'failed',
                            'error': str(e)
                        })
        else:
            # Sequential execution
            for account in accounts_to_sync:
                result = self._sync_single_account(
                    account,
                    broadcast_progress=True
                )
                results.append(result)

        return self._aggregate_results(results)

    def _sync_single_account(self, account, broadcast_progress=False):
        """Sync single account and optionally broadcast progress"""
        from mcp.truelayer_sync import sync_account_transactions

        result = sync_account_transactions(
            connection_id=self.job_data['connection_id'],
            truelayer_account_id=account['account_id'],
            db_account_id=account['id'],
            access_token=self._get_access_token(),
            from_date=self.job_data['from_date'],
            to_date=self.job_data['to_date'],
            import_job_id=self.job_id
        )

        if broadcast_progress:
            from websocket_handlers import broadcast_import_progress
            broadcast_import_progress(self.job_id, {
                'account_id': account['id'],
                'status': 'completed',
                'result': result
            })

        return result
```

### Phase 2d: Frontend WebSocket Integration

**Update: `frontend/src/components/TrueLayer/ImportProgressBar.tsx`**
```typescript
useEffect(() => {
  const socket = io('http://localhost:5000');

  socket.emit('subscribe_import_job', {
    job_id: jobId,
    user_id: getCurrentUserId(),
  });

  socket.on('import_progress', (data) => {
    // Real-time progress update
    setProgress(prev => ({
      ...prev,
      [data.account_id]: data
    }));
  });

  return () => {
    socket.emit('unsubscribe_import_job', { job_id: jobId });
    socket.disconnect();
  };
}, [jobId]);
```

### Phase 2e: Batch Size Optimization

**Update: `backend/mcp/truelayer_client.py`**
```python
def fetch_all_transactions_batched(self, account_id, from_date, to_date, batch_size=100):
    """
    Fetch all transactions with pagination support.

    Args:
        batch_size: Number of transactions per request (default 100, max 1000)

    Yields:
        Lists of transactions
    """
    offset = 0
    has_more = True

    while has_more:
        response = self._make_request(
            'GET',
            f'/data/v1/accounts/{account_id}/transactions',
            params={
                'from': from_date,
                'to': to_date,
                'limit': batch_size,
                'offset': offset
            }
        )

        transactions = response.get('results', [])
        if not transactions:
            has_more = False
            break

        yield [self.normalize_transaction(txn) for txn in transactions]

        offset += batch_size
        if len(transactions) < batch_size:
            has_more = False
```

### Phase 2 Deliverables

- ✅ Celery task queue with Redis
- ✅ Background import execution
- ✅ WebSocket real-time progress updates
- ✅ Parallel account processing (3-5 worker threads)
- ✅ Batch size optimization
- ✅ Automatic enrichment scheduling post-import
- ✅ Error recovery and retry logic

### Phase 2 Timeline: 2 weeks (80 hours)
- Celery setup & tasks: 20 hours
- WebSocket integration: 20 hours
- Parallel processing: 15 hours
- Batch optimization: 10 hours
- Frontend updates: 10 hours
- Testing & documentation: 5 hours

---

## Phase 3: Production Hardening & Advanced Features (Weeks 5-8)

### Goals
- Production-ready monitoring and alerting
- Advanced queue management UI
- Retry strategies and error handling
- Rate limiting awareness
- Cost tracking and optimization
- Scheduled recurring imports

### Phase 3a: Queue Management UI

**New Component: `ImportQueueManager.tsx`**
```typescript
// Shows queued, running, and completed imports
// Allows pause/resume/cancel operations
// Shows cost breakdown and metrics
```

### Phase 3b: Rate Limiting & Cost Tracking

**Update: `backend/config/rate_limits.py`**
```python
TRUELAYER_RATE_LIMITS = {
    'sandbox': 100,    # requests/minute
    'production': 500,
}

# Track API calls per user
def can_execute_import(user_id, api_calls_needed):
    """Check if user is within rate limits"""
    # Implementation
    pass

def estimate_api_cost(transaction_count, batch_size, accounts):
    """Estimate API calls and cost"""
    min_calls = len(accounts)  # At least 1 per account
    estimated_calls = min_calls + (transaction_count // batch_size)
    estimated_cost = estimated_calls * COST_PER_CALL
    return estimated_cost
```

### Phase 3c: Monitoring & Alerting

**New: `backend/monitoring/import_metrics.py`**
```python
# Track:
# - Import duration by date range
# - API call counts vs estimates
# - Enrichment success rates
# - Queue depth
# - Error rates per error type
# - Cost trends

# Send to monitoring service (DataDog, NewRelic, etc.)
```

### Phase 3d: Recurring Import Schedules

**New Database Table**
```sql
CREATE TABLE truelayer_import_schedules (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    connection_id INTEGER REFERENCES bank_connections(id),

    -- Schedule config
    frequency VARCHAR, -- 'daily', 'weekly', 'monthly'
    run_time TIME DEFAULT '02:00:00', -- UTC time to run

    -- Job config
    days_back INTEGER DEFAULT 7, -- How far back to sync
    account_ids TEXT[] DEFAULT ARRAY[]::TEXT[],
    auto_enrich BOOLEAN DEFAULT TRUE,

    -- Status
    enabled BOOLEAN DEFAULT TRUE,
    last_run TIMESTAMP,
    next_run TIMESTAMP,
    last_status VARCHAR,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Phase 3e: Advanced Error Recovery

**New: `backend/tasks/error_recovery.py`**
```python
@celery_app.task(bind=True, max_retries=3)
def execute_import_with_retry(self, job_id):
    """Execute with exponential backoff retry"""
    try:
        execute_import_job(job_id)
    except Exception as exc:
        # Retry with exponential backoff: 60, 300, 900 seconds
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
```

### Phase 3f: Cost Optimization Dashboard

**Component: `ImportCostAnalytics.tsx`**
```typescript
// Show:
// - API calls vs estimated
// - Cost per import
// - Enrichment cost breakdown
// - Savings from cache hits
// - Projected monthly costs
```

### Phase 3 Deliverables

- ✅ Advanced queue management UI
- ✅ Rate limiting and cost tracking
- ✅ Monitoring and alerting integration
- ✅ Recurring scheduled imports
- ✅ Advanced error recovery
- ✅ Cost analytics dashboard
- ✅ Production deployment guide

### Phase 3 Timeline: 4 weeks (120 hours)
- Queue management UI: 20 hours
- Rate limiting: 15 hours
- Monitoring integration: 20 hours
- Recurring schedules: 25 hours
- Error recovery: 15 hours
- Cost analytics: 15 hours
- Documentation & deployment: 10 hours

---

## Implementation Summary

### Total Effort Estimate

| Phase | Duration | Effort | Key Deliverables |
|-------|----------|--------|------------------|
| **Phase 1: Foundation** | 2 weeks | 80 hours | Import wizard, date range UI, basic queue |
| **Phase 2: Async & Queuing** | 2 weeks | 80 hours | Background jobs, WebSockets, parallelization |
| **Phase 3: Production** | 4 weeks | 120 hours | Monitoring, scheduling, cost tracking |
| **TOTAL** | 8 weeks | 280 hours | Complete batch import management system |

### Start Options

**Option A: MVP Only (4 weeks)**
- Phase 1 (Foundation) + Phase 2a-b (Async basics)
- Date range + multi-select + background processing
- Real-time progress tracking
- ~160 hours total

**Option B: Full System (8 weeks)**
- All three phases
- Production-ready with monitoring
- ~280 hours total

### Parallel Development Strategy

Recommended team split for faster delivery:

**Team A (Backend)** - 160 hours
- Database schema (Week 1)
- API endpoints (Weeks 1-2)
- Celery tasks (Weeks 3-4)
- Monitoring (Weeks 5-6)

**Team B (Frontend)** - 120 hours
- Date range wizard (Weeks 1-2)
- Progress UI (Weeks 2-3)
- WebSocket integration (Weeks 3-4)
- Queue manager (Weeks 5-6)

---

## Risk Mitigation

### Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Celery/Redis downtime | Lost imports | Message persistence, retry queue |
| Rate limit hitting | Import failure | Implement rate limit checker |
| WebSocket disconnects | Lost progress updates | Implement reconnection with state sync |
| Large account sync stalls | UX timeout | Per-account 60-second timeout + error handling |
| Enrichment queue overflow | Memory issues | Implement enrichment batching + pagination |

### Testing Strategy

- Unit tests: Database functions, date calculations
- Integration tests: Full import flow end-to-end
- Load tests: 10 concurrent imports, 1000+ txn accounts
- WebSocket tests: Connection stability, real-time updates
- Error tests: Network failures, API errors, timeout scenarios

---

## Next Steps

1. **Review & Approval** - Present this plan to stakeholders
2. **Set Timeline** - Decide between MVP (4 weeks) or Full (8 weeks)
3. **Assign Teams** - Backend vs Frontend (consider parallel development)
4. **Setup Infrastructure** - Redis/Celery in staging
5. **Begin Phase 1** - Start with foundation
6. **Weekly Syncs** - Track progress against this plan

---

## Questions for Clarification

Before starting implementation, confirm:

1. **MVP vs Full:** Do you want MVP (date range + progress) or full system (with schedules)?
2. **Team Size:** How many developers? Can we do parallel teams?
3. **Timeline:** Is 4-8 weeks feasible for your roadmap?
4. **Infrastructure:** Do you have Redis/Celery experience? Need help setting up?
5. **Batch Size:** What's optimal batch size for your users? (50, 100, 200?)
6. **Rate Limits:** Are you hitting TrueLayer rate limits? What's your usage pattern?
7. **Enrichment:** Should enrichment auto-run or require user confirmation?
8. **Monitoring:** Do you have DataDog/NewRelic already? What's preferred?
