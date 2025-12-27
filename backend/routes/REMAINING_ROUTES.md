# Remaining Routes to Extract

**Total routes in app.py:** 159
**Already extracted:** 60 (Gmail: 28, TrueLayer: 17, Amazon: 16 + 9)
**Remaining:** 99 routes

---

## 1. Transactions (5 routes)
**Blueprint:** `transactions_bp` → `/api/transactions`

- `GET /api/transactions` - List all transactions with filters
- `POST /api/transactions/<id>/toggle-required` - Toggle enrichment required flag
- `PUT /api/transactions/<id>/huququllah` - Update Huququllah classification
- `GET /api/transactions/<id>/enrichment-sources` - Get enrichment sources for transaction
- `POST /api/transactions/<id>/enrichment-sources/primary` - Set primary enrichment source

---

## 2. Categories v1 (Legacy) (7 routes)
**Blueprint:** `categories_bp` → `/api/categories`

- `GET /api/categories` - Get all categories
- `GET /api/categories/summary` - Get category spending summary
- `GET /api/categories/<category_name>/subcategories` - Get subcategories
- `POST /api/categories/promote` - Promote category to top level
- `POST /api/categories/hide` - Hide category
- `POST /api/categories/unhide` - Unhide category
- `GET /api/categories/custom` - Get custom categories

---

## 3. Categories v2 (10 routes)
**Blueprint:** `categories_v2_bp` → `/api/v2/categories`

**Categories:**
- `GET /api/v2/categories` - List all categories
- `GET /api/v2/categories/<id>` - Get category by ID
- `POST /api/v2/categories` - Create category
- `PUT /api/v2/categories/<id>` - Update category
- `DELETE /api/v2/categories/<id>` - Delete category

**Subcategories:**
- `GET /api/v2/subcategories` - List all subcategories
- `GET /api/v2/subcategories/<id>` - Get subcategory by ID
- `POST /api/v2/categories/<id>/subcategories` - Create subcategory
- `PUT /api/v2/subcategories/<id>` - Update subcategory
- `DELETE /api/v2/subcategories/<id>` - Delete subcategory

---

## 4. Enrichment/LLM (12 routes)
**Blueprint:** `enrichment_bp` → `/api/enrichment`, `/api/llm`

**Configuration:**
- `GET /api/enrichment/config` - Get LLM provider config
- `GET /api/enrichment/account-info` - Get API account info
- `GET /api/llm/available-models` - List available models

**Operations:**
- `POST /api/enrichment/estimate` - Estimate enrichment cost
- `POST /api/enrichment/trigger` - Trigger enrichment job
- `POST /api/enrichment/validate` - Validate enrichment config
- `POST /api/enrichment/retry` - Retry failed enrichments
- `GET/POST /api/enrichment/enrich-stream` - Stream enrichment

**Status:**
- `GET /api/enrichment/status/<job_id>` - Get job status
- `GET /api/enrichment/stats` - Get enrichment statistics
- `GET /api/enrichment/failed` - Get failed enrichments
- `GET /api/enrichment/cache/stats` - Get cache statistics
- `GET /api/enrichment-sources/<id>/details` - Get enrichment source details

---

## 5. Huququllah (3 routes)
**Blueprint:** `huququllah_bp` → `/api/huququllah`

- `GET /api/huququllah/suggest/<id>` - Get suggestion for transaction
- `GET /api/huququllah/summary` - Get Huququllah summary
- `GET /api/huququllah/unclassified` - Get unclassified transactions

---

## 6. Rules (14 routes)
**Blueprint:** `rules_bp` → `/api/rules`

**Category Rules:**
- `GET /api/rules/category` - List category rules
- `POST /api/rules/category` - Create category rule
- `PUT /api/rules/category/<id>` - Update category rule
- `DELETE /api/rules/category/<id>` - Delete category rule
- `POST /api/rules/category/<id>/test` - Test category rule
- `POST /api/rules/category/test-pattern` - Test pattern matching

**Merchant Rules:**
- `GET /api/rules/merchant` - List merchant normalization rules
- `POST /api/rules/merchant` - Create merchant rule
- `PUT /api/rules/merchant/<id>` - Update merchant rule
- `DELETE /api/rules/merchant/<id>` - Delete merchant rule
- `POST /api/rules/merchant/<id>/test` - Test merchant rule

**Bulk Operations:**
- `GET /api/rules/statistics` - Get rule usage statistics
- `POST /api/rules/test-all` - Test all rules
- `POST /api/rules/apply-all` - Apply all rules

---

## 7. Settings (5 routes)
**Blueprint:** `settings_bp` → `/api/settings`

- `GET /api/settings/account-mappings` - Get account mappings
- `POST /api/settings/account-mappings` - Create account mapping
- `PUT /api/settings/account-mappings/<id>` - Update account mapping
- `DELETE /api/settings/account-mappings/<id>` - Delete account mapping
- `GET /api/settings/account-mappings/discover` - Discover new accounts

---

## 8. Direct Debit (6 routes)
**Blueprint:** `direct_debit_bp` → `/api/direct-debit`

- `GET /api/direct-debit/payees` - Get all payees
- `GET /api/direct-debit/mappings` - Get direct debit mappings
- `POST /api/direct-debit/mappings` - Create mapping
- `DELETE /api/direct-debit/mappings/<id>` - Delete mapping
- `POST /api/direct-debit/apply-mappings` - Apply mappings to transactions
- `GET /api/direct-debit/new` - Detect new direct debits

---

## 9. Matching (4 routes)
**Blueprint:** `matching_bp` → `/api/matching`

- `GET /api/matching/jobs/<id>` - Get matching job status
- `POST /api/matching/jobs/cleanup-stale` - Clean up stale jobs
- `GET /api/matching/coverage` - Get matching coverage statistics
- `POST /api/matching/run` - Run matching job

---

## 10. Apple (11 routes)
**Blueprint:** `apple_bp` → `/api/apple`

**Import:**
- `POST /api/apple/import` - Import from HTML file
- `POST /api/apple/import/browser-start` - Start browser automation
- `GET /api/apple/import/browser-status` - Get browser status
- `POST /api/apple/import/browser-capture` - Capture from browser
- `POST /api/apple/import/browser-cancel` - Cancel browser import

**Operations:**
- `GET /api/apple` - Get all Apple transactions
- `GET /api/apple/statistics` - Get statistics
- `POST /api/apple/match` - Run matching
- `DELETE /api/apple` - Clear all Apple data
- `GET /api/apple/files` - List available files
- `POST /api/apple/export-csv` - Export to CSV

---

## 11. Pre-enrichment (3 routes)
**Blueprint:** `pre_enrichment_bp` → `/api/pre-enrichment`, `/api/preai`

- `GET /api/pre-enrichment/summary` - Get pre-enrichment summary
- `POST /api/pre-enrichment/backfill` - Backfill pre-enrichment data
- `GET /api/preai/jobs/active` - Get active pre-AI jobs

---

## 12. Migrations (3 routes)
**Blueprint:** `migrations_bp` → `/api/migrations`

- `POST /api/migrations/fix-card-payment-merchants` - Fix merchant names
- `POST /api/migrations/add-huququllah-column` - Add Huququllah column
- `POST /api/migrations/reapply-account-mappings` - Reapply mappings

---

## 13. Storage/Attachments (3 routes)
**Blueprint:** `storage_bp` → `/api/attachments`, `/api/storage`

- `GET /api/attachments/<id>/download` - Download attachment
- `GET /api/attachments/<id>/url` - Get attachment URL
- `GET /api/storage/status` - Get storage status (MinIO)

---

## 14. Cache (1 route)
**Blueprint:** `cache_bp` → `/api/cache`

- `GET /api/cache/stats` - Get cache statistics

---

## 15. Testing (1 route)
**Blueprint:** `testing_bp` → `/api/testing`

- `POST /api/testing/clear` - Clear all test data

---

## Extraction Priority

**High Priority (Core Features):**
1. **Transactions** (5 routes) - Core data operations
2. **Enrichment** (12 routes) - Critical LLM functionality
3. **Rules** (14 routes) - Core categorization logic
4. **Apple** (11 routes) - Third data source integration

**Medium Priority (Important Features):**
5. **Categories v1 + v2** (17 routes) - Category management
6. **Huququllah** (3 routes) - Islamic finance calculations
7. **Direct Debit** (6 routes) - Payment management
8. **Matching** (4 routes) - Cross-source matching

**Low Priority (Utilities):**
9. **Settings** (5 routes) - Configuration
10. **Pre-enrichment** (3 routes) - Background processing
11. **Migrations** (3 routes) - One-time operations
12. **Storage** (3 routes) - File operations
13. **Cache** (1 route) - Monitoring
14. **Testing** (1 route) - Development utility

---

## Summary

| Blueprint | Routes | Status |
|-----------|--------|--------|
| Transactions | 5 | Pending |
| Categories v1 | 7 | Pending |
| Categories v2 | 10 | Pending |
| Enrichment | 12 | Pending |
| Huququllah | 3 | Pending |
| Rules | 14 | Pending |
| Settings | 5 | Pending |
| Direct Debit | 6 | Pending |
| Matching | 4 | Pending |
| Apple | 11 | Pending |
| Pre-enrichment | 3 | Pending |
| Migrations | 3 | Pending |
| Storage | 3 | Pending |
| Cache | 1 | Pending |
| Testing | 1 | Pending |
| **TOTAL REMAINING** | **88** | |

**Note:** Original count was 99 remaining, but after careful review, the actual count is 88 routes remaining to extract.
