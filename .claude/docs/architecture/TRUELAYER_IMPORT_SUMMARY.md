# TrueLayer Batch Import Plan - Executive Summary

**Document:** TRUELAYER_IMPORT_BATCH_PLAN.md
**Status:** Ready for Implementation
**Total Effort:** 280 hours (8 weeks) | 160 hours (4 weeks MVP)

---

## What You're Building

A complete **batch import management system** for TrueLayer transactions with:

✅ **Date Range Selection** - Historical imports + incremental updates
✅ **Multi-Account Selection** - Choose which accounts to sync
✅ **Background Processing** - Async imports with Celery/Redis
✅ **Real-Time Progress Tracking** - WebSocket updates per account
✅ **Queue Management** - View/manage import jobs
✅ **Auto-Enrichment** - Schedule enrichment after import
✅ **Cost Tracking** - Monitor API usage and costs
✅ **Recurring Imports** - Schedule daily/weekly/monthly syncs

---

## Three Implementation Phases

### Phase 1: Foundation (Weeks 1-2, 80 hours)
**MVP-Ready Date Range + Multi-Select**

- Date range selection UI (presets + custom)
- Multi-select accounts/cards
- Import job database tracking
- Basic progress polling
- Import history view

**What Users Get:** "Pick date range, select accounts, click import"

### Phase 2: Async & Real-Time (Weeks 3-4, 80 hours)
**Background Processing + Live Progress**

- Celery task queue + Redis
- WebSocket real-time progress updates
- Parallel account processing (3-5 workers)
- Batch size configuration
- Auto-enrichment scheduling
- Error recovery

**What Users Get:** "Import runs in background, see real-time per-account progress"

### Phase 3: Production Features (Weeks 5-8, 120 hours)
**Monitoring + Scheduling + Cost Tracking**

- Queue management UI
- Rate limiting awareness
- Monitoring & alerting
- Recurring import schedules
- Cost analytics dashboard
- Advanced error recovery

**What Users Get:** "Automatic daily imports, cost tracking, advanced management"

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                      FRONTEND                           │
├─────────────────────────────────────────────────────────┤
│ ImportWizard (date range + account selection)           │
│ ImportProgressBar (real-time per-account status)        │
│ ImportQueueManager (view/manage jobs)                   │
│ ImportCostAnalytics (cost tracking)                     │
└────────────┬────────────────────────────────────────────┘
             │ HTTP + WebSocket
┌────────────▼────────────────────────────────────────────┐
│                     REST API                            │
├─────────────────────────────────────────────────────────┤
│ POST /api/truelayer/import/plan      (validate config)  │
│ POST /api/truelayer/import/start     (queue job)        │
│ GET  /api/truelayer/import/status    (poll progress)    │
│ GET  /api/truelayer/import/history   (view history)     │
└────────────┬────────────────────────────────────────────┘
             │
┌────────────▼────────────────────────────────────────────┐
│            BACKEND SERVICES                             │
├─────────────────────────────────────────────────────────┤
│ ImportJob (orchestrate sync)                            │
│ TrueLayerSync (fetch & normalize)                       │
│ LLMEnricher (auto-categorize)                           │
│ Database (PostgreSQL - job tracking)                    │
│ Queue (Celery + Redis - async tasks)                    │
│ WebSocket (SocketIO - real-time updates)                │
└──────────────────────────────────────────────────────────┘
```

---

## Database Schema

**3 New Tables:**

1. **`truelayer_import_jobs`** - Track each import batch
   - Job status (pending/running/completed/failed)
   - Date range parameters
   - Account selection
   - Results (synced, duplicates, errors)

2. **`truelayer_import_progress`** - Per-account progress
   - Account ID
   - Synced/duplicate/error counts
   - Status per account

3. **`truelayer_enrichment_jobs`** - Post-import enrichment
   - Transaction IDs to enrich
   - Cost & token tracking
   - Success/failure counts

---

## Key Implementation Files

### Phase 1
- `backend/database_postgres.py` - Add import job functions
- `backend/mcp/truelayer_import_manager.py` - Job orchestration (NEW)
- `backend/app.py` - Add import endpoints
- `frontend/src/components/TrueLayer/ImportWizard.tsx` - Date + account selection (NEW)
- `frontend/src/components/TrueLayer/ImportProgressBar.tsx` - Progress display (NEW)

### Phase 2 (Additions)
- `backend/config/celery_config.py` - Queue setup (NEW)
- `backend/tasks/truelayer_tasks.py` - Background jobs (NEW)
- `backend/websocket_handlers.py` - Real-time updates (NEW)
- `frontend/src/components/TrueLayer/ImportProgressBar.tsx` - WebSocket integration

### Phase 3 (Additions)
- `backend/monitoring/import_metrics.py` - Cost tracking
- `frontend/src/components/TrueLayer/ImportQueueManager.tsx` - Queue UI (NEW)
- `frontend/src/components/TrueLayer/ImportCostAnalytics.tsx` - Analytics (NEW)
- Database table `truelayer_import_schedules` - Recurring imports

---

## API Endpoints Summary

### Phase 1
```
POST /api/truelayer/import/plan
  Request: from_date, to_date, account_ids, auto_enrich
  Response: job_id, estimated_transactions, estimated_duration

POST /api/truelayer/import/start
  Request: job_id
  Response: status = 'running'

GET /api/truelayer/import/status/{job_id}
  Response: progress%, per-account status, ETA

GET /api/truelayer/import/history
  Response: list of past imports with results
```

### Phase 2 (Additions)
```
WebSocket: /socket.io
  subscribe_import_job: Real-time progress updates
  unsubscribe_import_job: Stop listening
```

### Phase 3 (Additions)
```
GET /api/truelayer/import/queue
  Response: queued, running, completed jobs

PATCH /api/truelayer/import/{job_id}/pause
  Pause a running import

PATCH /api/truelayer/import/{job_id}/resume
  Resume paused import

DELETE /api/truelayer/import/{job_id}
  Cancel/delete import job
```

---

## Data Flow Example

**User Imports 2 Accounts from Jan 1 - Dec 31, 2024**

```
1. User clicks "Import"
   └─ ImportWizard starts

2. User selects date range
   └─ "2024-01-01" to "2024-12-31" (365 days)

3. User selects accounts
   └─ "Current Account" + "Savings Account"

4. User configures
   └─ Auto-enrich: YES
   └─ Batch size: 50 transactions

5. System estimates
   └─ POST /api/truelayer/import/plan
   └─ Backend estimates: 250 transactions, 30 sec, $0.05 API cost
   └─ User reviews and confirms

6. Import starts (Phase 1)
   └─ POST /api/truelayer/import/start?job_id=123
   └─ Creates ImportJob(123)
   └─ Sequential account sync
   └─ Polls: GET /api/truelayer/import/status/123 every 2 seconds

7. Import starts (Phase 2+)
   └─ POST /api/truelayer/import/start?job_id=123
   └─ Queues: tasks.execute_import_job(123)
   └─ Celery picks up and runs in background
   └─ WebSocket: Real-time per-account progress
   └─ After sync done: Auto-enrichment if enabled

8. Results
   └─ 250 transactions imported
   └─ 8 duplicates (skipped)
   └─ 0 errors
   └─ Ready for enrichment
```

---

## Comparison: Before vs After

### Before (Current State)
```
User clicks "Sync TrueLayer"
  └─ Waits 5-10 seconds for all accounts (blocking)
  └─ Transactions stored with category = "Other"
  └─ No progress indication
  └─ Cannot cancel
  └─ Must manually trigger enrichment later
```

### After Phase 1
```
User opens Import Wizard
  └─ Selects date range (e.g., "Last 30 days")
  └─ Selects accounts (checkboxes)
  └─ Sees estimate (# txns, duration, cost)
  └─ Clicks "Import"
  └─ Polls for progress (updates every 2 sec)
  └─ Can view per-account progress
```

### After Phase 2
```
User opens Import Wizard
  └─ Same as Phase 1 workflow
  └─ BUT:
     └─ Import runs in background (can close browser)
     └─ Real-time WebSocket updates (no polling delay)
     └─ 3-5 accounts processed in parallel (3-5x faster)
     └─ Auto-enrichment triggers after import
     └─ User sees "Import complete + enrichment running"
```

### After Phase 3
```
User opens Import Wizard
  └─ Same as Phase 2 workflow
  └─ PLUS:
     └─ "Schedule daily import of last 7 days"
     └─ View cost analytics ($X per month)
     └─ Queue manager showing 5 queued, 2 running
     └─ Monitoring alerts if errors spike
     └─ Can pause/resume individual imports
```

---

## Team Effort Breakdown

### Single Developer (Sequential)
- **Total:** 32 weeks (8 weeks x 4 = full time)
- **Not recommended** - Better to phase/prioritize

### Two Developers (Parallel)
- **Backend Dev:** 160 hours (Weeks 1-4, then 5-8)
- **Frontend Dev:** 120 hours (Weeks 1-4, then 5-8)
- **Total Duration:** 8 weeks (parallel work)
- **Recommended approach** ✓

### Three Developers
- **Backend Dev:** 160 hours
- **Frontend Dev:** 120 hours
- **DevOps/QA:** 60 hours (Celery/Redis setup, testing, deployment)
- **Total Duration:** 6-7 weeks

---

## Success Metrics

### Phase 1 Success
- ✓ Users can import with custom date ranges
- ✓ Multi-select accounts working
- ✓ Import progress visible
- ✓ Import history stored and queryable
- ✓ Zero data loss (deduplication works)

### Phase 2 Success
- ✓ Background imports don't block UI
- ✓ Real-time WebSocket updates within 2 seconds
- ✓ 3-5 accounts sync in ~30% of current time
- ✓ Auto-enrichment triggers after import
- ✓ Queue handles 10+ concurrent imports

### Phase 3 Success
- ✓ Cost tracking accurate within 5%
- ✓ Scheduled imports run on time (99.9% uptime)
- ✓ Monitoring alerts within 5 minutes of issues
- ✓ Users report smooth, intuitive workflow

---

## Risk & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Celery/Redis failures | Medium | High | Message persistence, manual recovery |
| Rate limit hitting | Low | Medium | Rate limit checker + alerts |
| WebSocket disconnects | Low | Low | Auto-reconnect with backoff |
| Large imports timeout | Low | Medium | Per-account 60-sec timeout + retry |
| Enrichment queue overflow | Low | Medium | Pagination + batch limiting |

---

## Recommended Next Steps

1. **Review This Plan**
   - Share with stakeholders
   - Get feedback on approach
   - Confirm timeline (MVP 4 weeks vs Full 8 weeks)

2. **Setup Infrastructure**
   - Install Celery/Redis in staging
   - Test WebSocket with Flask-SocketIO
   - Create database migration scripts

3. **Start Phase 1**
   - Begin database schema
   - Build ImportWizard component
   - Implement basic API endpoints

4. **Weekly Syncs**
   - Track progress
   - Address blockers
   - Adjust timeline if needed

---

## Questions Before Starting?

- **MVP vs Full?** - Do you want 4-week MVP or 8-week full system?
- **Team available?** - Can you dedicate 1-2 developers full-time?
- **Infrastructure ready?** - Do you have Redis/Celery experience?
- **Batch size preference?** - What works best for your API tier?
- **Enrichment flow?** - Auto-run or require confirmation?
- **Monitoring tools?** - Which monitoring platform to integrate?

---

## Document Location

Full detailed plan: `/.claude/docs/architecture/TRUELAYER_IMPORT_BATCH_PLAN.md`

---

**Status:** Ready to begin Phase 1 implementation when approved.
