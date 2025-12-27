# Routes & Services Refactoring - Status Report

## Goal

Decompose app.py (5,121 lines, 159 routes) into:
- Domain-specific Flask blueprints (routes/)
- Business logic services (services/)
- Simplified main app.py (~200 lines)

## Current Status

### ✅ Complete

**Infrastructure Created:**
- `/backend/routes/` directory with README
- `/backend/services/` directory with README
- Existing routes: `auth.py`, `health.py`

### 🚧 In Progress

**Route Analysis Complete:**
| Domain | Routes | Status |
|--------|--------|--------|
| Gmail | 28 | TODO |
| TrueLayer | 17 | TODO |
| Amazon | 16 | TODO |
| Amazon Business | 9 | TODO |
| Rules | 14 | TODO |
| Enrichment | 11 | TODO |
| Apple | 11 | TODO |
| Categories (v1+v2) | 17 | TODO |
| Direct Debit | 6 | TODO |
| Transactions | 5 | TODO |
| Settings | 5 | TODO |
| Matching | 4 | TODO |
| Migrations | 3 | TODO |
| Huququllah | 3 | TODO |
| Others | ~10 | TODO |
| **Total** | **159** | **0% extracted** |

### ⏳ TODO

1. Create service modules (6 services)
2. Extract routes to blueprints (14 blueprints)
3. Update app.py to register blueprints
4. Test each blueprint independently

## Extraction Priority

**Phase 1** (Largest domains):
1. Gmail routes → `routes/gmail.py` + `services/gmail_service.py`
2. TrueLayer routes → `routes/truelayer.py` + `services/truelayer_service.py`
3. Amazon routes → `routes/amazon.py` + `services/amazon_service.py`

**Phase 2** (Core functionality):
4. Enrichment routes → `routes/enrichment.py` + `services/enrichment_service.py`
5. Categories routes → `routes/categories.py` + `services/category_service.py`
6. Rules routes → `routes/rules.py`

**Phase 3** (Remaining):
7-14. All remaining blueprints

## Success Metrics

- ✅ Directory structure created
- ⏳ All routes extracted to blueprints
- ⏳ Business logic in services/
- ⏳ app.py < 300 lines
- ⏳ All tests passing
- ⏳ No route over 500 lines

## Estimated Completion

- **Infrastructure**: ✅ Complete
- **Service Layer**: 2-3 hours (6 services)
- **Blueprint Extraction**: 4-6 hours (14 blueprints)
- **Testing & Integration**: 1-2 hours

**Total**: 7-11 hours for complete routes refactoring
