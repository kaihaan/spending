# TrueLayer Integration - Optimization Quick Reference

**Last Updated:** 2025-11-28
**Document Type:** Quick Reference & Action Items
**Target Audience:** Developers, Technical Leads

---

## Executive Summary

The TrueLayer integration works well end-to-end (OAuth → Account Discovery → Transaction Sync), but has **3 critical bottlenecks** that impact user experience and operational efficiency:

1. **Sequential Account Processing** - Multi-account syncs take 3-5x longer than necessary
2. **Missing Auto-Enrichment** - TrueLayer transactions stay uncategorized until manual enrichment
3. **Inefficient Deduplication** - Per-transaction DB queries instead of batch

**Implementing the top 2 optimizations would deliver 3-5x faster syncs and consistent user experience.**

---

## Current Workflow Summary

```
OAuth (5 min)
    ↓
Account Discovery (2 min)
    ↓
Manual Sync Trigger
    ↓
Token Refresh (auto, <1 sec if needed)
    ↓
Fetch Transactions from TrueLayer API (2-5 sec per account)
    ↓
Normalize & Deduplicate (1-2 sec per 100 txns)
    ↓
Store in Database (1-2 sec per 100 txns)
    ↓
❌ MISSING: Auto-Enrichment with LLM (3-5 sec per 100 txns)
    ↓
[User sees "Other" category transactions]
```

---

## Top 5 Optimization Opportunities

### 1. 🔴 HIGH PRIORITY: Parallel Account Syncing
**Impact:** 3-5x faster syncs for multi-account users
**Effort:** 6-8 hours
**Status:** Not Implemented

**Current:**
```python
# Syncs accounts SEQUENTIALLY
for account in accounts:
    result = sync_account_transactions(...)  # Waits for completion
    # 5 accounts = wait for account 1, then 2, then 3, then 4, then 5
```

**Expected Improvement:**
- 1 account: ~1 second (no change)
- 5 accounts: 5 seconds → 1-1.5 seconds (80% faster)
- 10 accounts: 10 seconds → 2-3 seconds (70% faster)

**Implementation:**
```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=3) as executor:
    futures = [
        executor.submit(sync_account_transactions, ...)
        for account in accounts
    ]
    results = [future.result() for future in futures]
```

**Files to Modify:**
- `backend/mcp/truelayer_sync.py:301-396` (sync_all_accounts)
- Test with 3-5 concurrent threads to avoid API rate limits

---

### 2. 🔴 HIGH PRIORITY: Auto-Enrich After Sync
**Impact:** Consistent categorization, better UX
**Effort:** 4-6 hours
**Status:** Not Implemented

**Current:**
- Santander Excel imports: Auto-enrich ✓
- TrueLayer sync: No enrichment ✗
- Users see "Other" until manual enrichment

**Expected Improvement:**
- Users see properly categorized transactions immediately
- Consistent UX across all import sources
- Better spending insights in dashboard

**Implementation:**
```python
# In app.py:sync_truelayer_transactions()

result = sync_all_accounts(user_id)

# NEW: Auto-enrich newly synced transactions
newly_synced_ids = result.get('newly_synced_transaction_ids', [])
if newly_synced_ids:
    try:
        enricher = get_enricher()
        if enricher:
            enrich_stats = enricher.enrich_transactions(
                transaction_ids=newly_synced_ids,
                direction='out'
            )
            result['enrichment_stats'] = enrich_stats
    except Exception as e:
        logger.error(f"Enrichment failed (non-fatal): {e}")
```

**Files to Modify:**
- `backend/app.py:1523-1580` (sync_truelayer_transactions endpoint)
- `backend/mcp/truelayer_sync.py:301-396` (sync_all_accounts - return synced txn IDs)
- `backend/database_postgres.py` (add get_newly_synced_transactions_ids method)

**Time Added to Sync:**
- 3-5 seconds for 100 transactions
- Trade-off: Worth it for immediate categorization

---

### 3. 🟡 MEDIUM PRIORITY: Batch Deduplication
**Impact:** 500-1000ms savings per sync
**Effort:** 2-3 hours
**Status:** Not Implemented

**Current:**
```python
# Query DB 100 TIMES for 100 transactions
for txn in transactions:
    existing = database.get_truelayer_transaction_by_id(normalised_id)  # DB query
    if existing:
        duplicate_count += 1
```

**Optimized:**
```python
# Query DB ONCE for 100 transactions
normalised_ids = [t['normalised_provider_id'] for t in transactions]
existing_ids = set(database.get_existing_ids_batch(normalised_ids))  # 1 query

for txn in transactions:
    if txn['normalised_provider_id'] in existing_ids:  # O(1) lookup
        duplicate_count += 1
```

**Expected Improvement:**
- 100 txns: 100 queries → 1 query
- Savings: ~500-1000ms per sync

**Files to Modify:**
- `backend/mcp/truelayer_sync.py:143-193`
- `backend/database_postgres.py` (add get_existing_ids_batch method)

---

### 4. 🟡 MEDIUM PRIORITY: Improve Incremental Sync Window
**Impact:** 15-20% fewer API calls
**Effort:** 2-3 hours
**Status:** Not Implemented

**Current Problem:**
```python
days_since_sync = (now - last_sync).days       # e.g., 2 days
sync_days = max(1, days_since_sync + 1)        # REQUESTS 3 DAYS
# Fetches 1 day of redundant data every sync
```

**Optimized:**
```python
# Track last_synced_at more precisely (per-account, not just connection)
# Remove the "+1 day buffer" (use exact timestamp with 1-minute buffer)
time_since_sync = (now - last_sync).total_seconds()
sync_days = max(1, math.ceil(time_since_sync / 86400))  # 1 minute tolerance
```

**Expected Improvement:**
- Fetches only truly new transactions
- 15-20% fewer API calls
- Slightly faster syncs

**Files to Modify:**
- `backend/mcp/truelayer_sync.py:94-128`
- `backend/database_postgres.py` (track per-account last_synced_at)

---

### 5. 🟢 LOW PRIORITY: Add Database Indexes
**Impact:** Better scalability (50K+ transactions)
**Effort:** < 1 hour
**Status:** Not Implemented

**Current:**
- UNIQUE index on `normalised_provider_transaction_id` (good)
- Missing composite indexes (future bottleneck)

**Add These Indexes:**
```sql
-- For enrichment cache lookups
CREATE INDEX idx_enrichment_cache_lookup
ON enrichment_cache(description_hash, direction);

-- For connection queries
CREATE INDEX idx_truelayer_accounts_connection
ON truelayer_accounts(connection_id, account_id);
```

**Expected Improvement:**
- Future-proofing for 50K+ cached enrichments
- Faster webhook account lookups

---

## Implementation Roadmap

### Phase 1: Critical Path (1-2 weeks)
1. **Auto-Enrich After Sync** (Priority 2) - 4-6 hours
   - Best ROI for user experience
   - Relatively low risk
   - Consistent with Excel imports
2. **Parallel Account Sync** (Priority 1) - 6-8 hours
   - Biggest performance gain
   - Requires threading knowledge
   - Needs careful error handling

### Phase 2: Performance Tuning (1 week)
3. **Batch Deduplication** (Priority 3) - 2-3 hours
4. **Incremental Sync Window** (Priority 4) - 2-3 hours
5. **Database Indexes** (Priority 5) - <1 hour

### Phase 3: Advanced (2-3 weeks)
6. **Connection-Level Sync Status** - 4-6 hours
7. **Webhook Signature Validation** - 2-3 hours
8. **Per-Account Sync Status Tracking** - 4-6 hours

---

## Key Metrics to Track

### Before Optimization
- Multi-account sync time: ~5-10 seconds
- Enrichment coverage: 50% (only Excel, not TrueLayer)
- DB queries per sync: ~150-200 (dedup checks)
- API calls for incremental sync: 20% redundant

### After Optimization
- Multi-account sync time: ~1-2 seconds (3-5x faster)
- Enrichment coverage: 100% (all sources)
- DB queries per sync: ~10-20 (batch checks)
- API calls: Exact match to needed data

---

## Technical Deep Dives

### Parallel Sync Thread Safety

**Concern:** Multiple threads accessing same encryption key
**Solution:** ThreadPoolExecutor is thread-safe for read operations
- Decryption is read-only
- Token refresh already handles locking via database transactions
- No shared mutable state between threads

**Testing Needed:**
```python
# Test with 10 accounts, 3 concurrent threads
# Verify:
# - All accounts synced correctly
# - No duplicate insertions
# - All errors captured
# - No DB connection exhaustion
```

### Enrichment Timing

**Current:** 3-5 seconds added to sync
**Optimization Options:**
1. Enrich in background task (user doesn't wait)
2. Enrich incrementally (cache first, lazy enrich rest)
3. Sample enrichment (enrich only 10% initially)

**Recommended:** Option 1 (background task)
- Keep sync fast
- Enrich happens within 30 seconds
- User sees categories shortly after sync

---

## Risk Assessment

### Low Risk Changes
✓ Batch deduplication
✓ Database indexes
✓ Incremental sync window
✓ Webhook payload optimization

### Medium Risk Changes
⚠ Parallel account sync (threading complexity)
⚠ Auto-enrichment (adds latency to sync)

### Risk Mitigation
- Start with feature flags (enable/disable optimizations)
- Extensive testing on multi-account users
- Gradual rollout (10% → 50% → 100%)
- Comprehensive error logging
- Rollback plan documented

---

## Code Quality Checklist

Before implementing optimizations:
- [ ] Write unit tests for new functions
- [ ] Add integration tests for multi-account scenarios
- [ ] Document configuration options
- [ ] Add feature flags for safe rollout
- [ ] Update API documentation
- [ ] Add monitoring/alerting for new metrics
- [ ] Performance regression tests
- [ ] Load testing (50K transactions, 10 accounts)

---

## Quick Reference: File Locations

| Component | File | Lines | Key Functions |
|-----------|------|-------|---|
| **Sync Logic** | `backend/mcp/truelayer_sync.py` | 67-225 | `sync_account_transactions` |
| **Multi-Account Sync** | `backend/mcp/truelayer_sync.py` | 301-396 | `sync_all_accounts` |
| **Token Management** | `backend/mcp/truelayer_auth.py` | 227-298 | `refresh_token_if_needed` |
| **API Endpoints** | `backend/app.py` | 1523-1580 | `sync_truelayer_transactions` |
| **Enrichment** | `backend/mcp/llm_enricher.py` | 92-259 | `enrich_transactions` |
| **Database** | `backend/database_postgres.py` | 964-1227 | Transaction storage |

---

## Questions to Answer Before Implementing

1. **Parallel Sync:** How many threads can TrueLayer API handle? (Test with 3, 5, 10)
2. **Enrichment Timing:** Is 3-5 seconds acceptable to add to sync time?
3. **Background Tasks:** Should enrichment run async? Need Celery/RQ?
4. **Monitoring:** What metrics matter most to track?
5. **Rollback:** What's the safest way to roll back if issues arise?

---

## Success Criteria

| Metric | Current | Target | Owner |
|--------|---------|--------|-------|
| Multi-account sync time | 5-10s | <2s | Dev |
| Enrichment coverage | 50% | 100% | Dev |
| User wait time | 5-10s | <3s | UX |
| API efficiency | -15% redundant | 0% | DevOps |
| Error rate | <1% | <0.1% | QA |

---

## Next Steps

1. **Review** this analysis with the team
2. **Prioritize** based on business impact
3. **Create** tracking issues in GitHub
4. **Assign** to developers with threading/async experience
5. **Plan** 2-week sprint for Phase 1
6. **Test** thoroughly on staging before production rollout
7. **Monitor** metrics post-deployment
