# TrueLayer Celery Async Sync Architecture

## Overview

Implement asynchronous transaction sync with progress tracking for TrueLayer bank accounts, following Gmail's proven Celery patterns while adapting for TrueLayer's specific characteristics.

## Current State (Synchronous)

**Problems:**
- User waits for entire sync (can be 30+ seconds for large date ranges)
- No progress visibility
- HTTP timeout risk for long-running syncs
- Sequential account processing (slow for multi-account users)
- No rate limit handling (429 errors)

**Flow:**
```
Frontend → POST /api/truelayer/sync → sync_transactions() → sync_all_accounts() → [WAIT] → Response
```

## Target State (Asynchronous with Progress)

**Benefits:**
- Immediate response (task ID returned)
- Real-time progress updates
- No HTTP timeout issues
- Optional parallel account sync (with rate limit awareness)
- Retry logic for transient failures

**Flow:**
```
Frontend → POST /api/truelayer/sync?async=true
    ↓
Route creates Celery task
    ↓
Returns task_id immediately
    ↓
Frontend polls GET /api/celery/task/<task_id>
    ↓
Shows progress: "Syncing Santander Current Account (2/3 accounts)"
```

## Architecture Components

### 1. Celery Task (`backend/tasks/truelayer_tasks.py`)

**Task Signature:**
```python
@celery_app.task(bind=True, time_limit=1800, soft_time_limit=1700)
def sync_truelayer_task(
    self,
    user_id: int,
    connection_id: int = None,
    date_from: str = None,
    date_to: str = None
):
    """
    Async TrueLayer sync with progress updates.

    Progress states:
    - 'started': Task initiated
    - 'syncing': Processing account N of M
    - 'completed': All accounts synced
    - 'failed': Error occurred
    """
```

**Progress Update Pattern (from Gmail):**
```python
self.update_state(state='PROGRESS', meta={
    'status': 'syncing',
    'current_account': 'Santander Current Account',
    'accounts_done': 2,
    'total_accounts': 3,
    'transactions_synced': 450,
    'duplicates': 12,
    'errors': 0
})
```

### 2. Rate Limit Handler (`backend/mcp/truelayer_client.py`)

**Add to `_make_request()` method:**
```python
def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict:
    max_retries = 3
    retry_delay = 2  # Start with 2 seconds

    for attempt in range(max_retries):
        try:
            response = requests.request(...)
            response.raise_for_status()
            return response.json()

        except requests.HTTPError as e:
            if e.response.status_code == 429:
                if attempt < max_retries - 1:
                    # Exponential backoff: 2s, 4s, 8s
                    wait_time = retry_delay * (2 ** attempt)
                    print(f"⚠️  Rate limited (429), retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise  # Give up after max retries
            else:
                raise
```

### 3. Performance Tracker (`backend/mcp/truelayer_sync.py`)

**Add SyncPerformanceTracker class (from Gmail):**
```python
class SyncPerformanceTracker:
    """Track performance metrics during TrueLayer sync."""

    def __init__(self):
        self.api_calls = []
        self.db_writes = []
        self.pagination_times = []
        self.start_time = time.time()

    def record_api_call(self, duration: float):
        self.api_calls.append(duration)

    def record_db_write(self, duration: float):
        self.db_writes.append(duration)

    def report(self, account_count: int, total_transactions: int):
        """Log performance summary."""
        total_time = time.time() - self.start_time

        print("=" * 80)
        print(f"PERFORMANCE SUMMARY: {total_transactions} transactions from {account_count} accounts in {total_time:.1f}s")
        print("=" * 80)
        print(f"Throughput: {total_transactions / (total_time / 60):.1f} transactions/min")

        if self.api_calls:
            print(f"API calls: avg={sum(self.api_calls)/len(self.api_calls):.3f}s, max={max(self.api_calls):.3f}s")

        if self.db_writes:
            print(f"DB writes: avg={sum(self.db_writes)/len(self.db_writes):.3f}s, max={max(self.db_writes):.3f}s")

        print("=" * 80)
```

### 4. Route Update (`backend/routes/truelayer.py`)

**Add async mode support:**
```python
@truelayer_bp.route('/sync', methods=['POST'])
def sync_transactions():
    """
    Trigger TrueLayer transaction sync.

    Query params:
        async (str): If 'true', runs as Celery task with task_id returned

    Request body:
        user_id, connection_id, date_from, date_to
    """
    async_mode = request.args.get('async', 'false').lower() == 'true'

    if async_mode:
        # Async mode: Trigger Celery task
        from tasks.truelayer_tasks import sync_truelayer_task

        task = sync_truelayer_task.delay(
            user_id=user_id,
            connection_id=connection_id,
            date_from=date_from,
            date_to=date_to
        )

        return jsonify({
            'job_id': task.id,
            'status': 'queued',
            'message': 'TrueLayer sync started in background'
        })
    else:
        # Sync mode (existing behavior)
        result = truelayer_service.sync_transactions(...)
        return jsonify(result)
```

## Implementation Phases

### Phase 1: Rate Limit Handling (Foundation)
**Goal:** Prevent 429 errors from crashing sync

**Tasks:**
1. Add retry logic with exponential backoff to `truelayer_client._make_request()`
2. Test with intentional rate limit (rapid API calls)
3. Verify logs show retry attempts

**Files:**
- `backend/mcp/truelayer_client.py` (lines 44-105)

**Acceptance Criteria:**
- 429 errors trigger retry with backoff (2s, 4s, 8s)
- Logs show: "⚠️  Rate limited (429), retrying in Xs..."
- Sync completes successfully after retry

---

### Phase 2: Performance Tracking
**Goal:** Measure where time is spent (API vs DB vs pagination)

**Tasks:**
1. Copy `SyncPerformanceTracker` class from `gmail_sync.py`
2. Instrument `sync_all_accounts()` to track metrics
3. Add `tracker.report()` at end of sync

**Files:**
- `backend/mcp/truelayer_sync.py` (add class at top, use in `sync_all_accounts`)

**Acceptance Criteria:**
- Performance summary printed after sync
- Shows: transactions/min, avg API call time, max DB write time
- Identifies bottlenecks (e.g., "pagination is slow")

---

### Phase 3: Celery Task Creation
**Goal:** Enable async sync with progress updates

**Tasks:**
1. Create `backend/tasks/truelayer_tasks.py`
2. Implement `sync_truelayer_task()` modeled after `sync_gmail_receipts_task`
3. Add progress updates using `self.update_state()`
4. Test with Celery worker

**Files:**
- `backend/tasks/truelayer_tasks.py` (NEW)

**Acceptance Criteria:**
- Task runs in background (returns immediately)
- Progress updates every account: "Syncing account 2/3"
- Task ID can be used to query status
- Logs appear in Celery worker, not Flask terminal

---

### Phase 4: Route Integration
**Goal:** Frontend can choose sync vs async mode

**Tasks:**
1. Update `/sync` route to accept `?async=true` parameter
2. Return task_id for async mode
3. Keep existing sync mode for backwards compatibility

**Files:**
- `backend/routes/truelayer.py` (lines 320-360)

**Acceptance Criteria:**
- `POST /sync` - synchronous (existing behavior)
- `POST /sync?async=true` - returns `{job_id: "...", status: "queued"}`
- Frontend can poll `/api/celery/task/<job_id>` for progress

---

### Phase 5: Frontend Progress UI (Optional)
**Goal:** Show real-time sync progress to user

**Tasks:**
1. Update `TrueLayerIntegration.tsx` to support async mode
2. Add progress bar component
3. Poll task status every 2 seconds
4. Display: "Syncing Santander (2/3 accounts) - 450 transactions"

**Files:**
- `frontend/src/components/TrueLayerIntegration.tsx`

**Acceptance Criteria:**
- Progress bar animates during sync
- Shows current account name and count
- Updates every 2 seconds
- Completes when task status = 'completed'

## Rate Limit Considerations

### Current Risk
- No `X-PSU-IP` header → all requests treated as unattended
- No retry logic → 429 errors crash sync
- Pagination can trigger rapid API calls (50 pages × N accounts)

### Mitigation Strategy

**Immediate (Phase 1):**
- Add retry logic with exponential backoff
- Max 3 retries per request (2s, 4s, 8s delays)

**Short-term (Phase 3):**
- Monitor 429 frequency in logs
- Alert if 429s occur frequently

**Long-term (Future):**
- Add `X-PSU-IP` header for user-triggered syncs (requires frontend to pass user IP)
- Implement adaptive rate limiting (slow down if 429s occur)
- Consider parallel account sync with concurrency limits (see Phase 6 below)

## Phase 6: Parallel Account Sync (Advanced - Not Implemented Yet)

**Goal:** Sync multiple accounts concurrently (like Gmail)

**Pattern from Gmail:**
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

TRUELAYER_SYNC_WORKERS = int(os.getenv('TRUELAYER_SYNC_WORKERS', '2'))

with ThreadPoolExecutor(max_workers=TRUELAYER_SYNC_WORKERS) as executor:
    futures = {
        executor.submit(sync_account_transactions, acc): acc
        for acc in accounts
    }

    for future in as_completed(futures):
        account = futures[future]
        result = future.result()
        # Update progress
```

**Caution:**
- Start with `TRUELAYER_SYNC_WORKERS=2` (conservative)
- Monitor for 429 errors
- Each account has pagination (100 txns/page), which multiplies API calls
- Example: 3 accounts × 5 pages each = 15 API calls
  - Sequential: 15 calls × 0.5s = 7.5s
  - Parallel (workers=3): ~2.5s (but higher 429 risk)

**Recommendation:**
- Implement Phases 1-4 first
- Monitor performance metrics
- Only add parallel sync if single-threaded is too slow AND 429s are rare

## Testing Strategy

### Unit Tests
- Mock TrueLayer API responses (including 429)
- Test retry logic triggers correctly
- Verify performance tracker calculates metrics

### Integration Tests
1. **Small sync:** 1 account, 10 transactions (should be fast)
2. **Date range sync:** 1 account, 90 days (test pagination)
3. **Multi-account:** 3 accounts, 30 days (test sequential processing)
4. **Rate limit:** Trigger 429 intentionally (rapid successive calls)

### Celery Testing
```bash
# Terminal 1: Start Celery worker
docker-compose logs -f celery

# Terminal 2: Trigger sync
curl -X POST "http://localhost:5000/api/truelayer/sync?async=true" \
  -H "Content-Type: application/json" \
  -d '{"connection_id": 16, "date_from": "2024-12-01", "date_to": "2024-12-27"}'

# Expected output:
{
  "job_id": "a1b2c3d4-...",
  "status": "queued",
  "message": "TrueLayer sync started in background"
}

# Check status:
curl http://localhost:5000/api/celery/task/a1b2c3d4-...

# Celery logs should show:
# ✅ Page 1: Fetched 100 transactions
# ✅ Page 2: Fetched 100 transactions
# ✅ Sync complete: 450 synced, 12 duplicates, 0 errors
# PERFORMANCE SUMMARY: 450 transactions in 8.5s
```

## Success Criteria

**Phase 1 Complete:**
- ✅ 429 errors don't crash sync
- ✅ Retry logic works with exponential backoff
- ✅ Logs show retry attempts

**Phase 2 Complete:**
- ✅ Performance summary logged after every sync
- ✅ Identifies slowest operation (API/DB/pagination)

**Phase 3 Complete:**
- ✅ Celery task executes successfully
- ✅ Progress updates visible in Celery logs
- ✅ Task ID can query status

**Phase 4 Complete:**
- ✅ Async mode works: `POST /sync?async=true`
- ✅ Sync mode still works: `POST /sync`
- ✅ Frontend can use either mode

**Overall Success:**
- User sees progress instead of waiting
- Large syncs (90 days, multiple accounts) complete reliably
- 429 errors handled gracefully
- Performance metrics help optimize further

## References

- Gmail implementation: `backend/tasks/gmail_tasks.py` (lines 8-157)
- Amazon SP rate limiting: `backend/mcp/amazon_sp_client.py` (lines 105-171)
- Performance tracking: `backend/mcp/gmail_sync.py` (lines 70-126)
- TrueLayer rate limits: `.claude/CLAUDE.md` (lines 428-453)
