# Feature Requirements: Testing Dashboard

**Status:** Draft
**Author:** Requirements Development Agent
**Created:** 2025-11-29
**Last Updated:** 2025-11-29
**Approved By:** [Pending Stakeholder Approval]

---

## 1. Overview

### 1.1 Summary
The Testing Dashboard is a developer-focused tool that provides controlled data clearing capabilities within the Settings page. It enables developers and testers to reset specific data categories independently, facilitating iterative testing of import, enrichment, and integration features without database-wide resets or manual SQL operations.

### 1.2 Problem Statement
During development and testing of data import features (TrueLayer, Amazon, Apple) and enrichment capabilities (LLM categorization), developers need to repeatedly test import workflows with clean data states. Currently, clearing test data requires direct database access via SQL commands or full database resets, which is:
- Time-consuming and disruptive to development workflow
- Error-prone (risk of deleting unintended data)
- Requires context-switching away from the application UI
- Makes testing cumbersome for non-database-savvy testers

The Testing Dashboard solves this by providing a safe, controlled, UI-driven mechanism to selectively clear specific data categories needed for testing, without requiring database expertise or risking unintended data loss.

### 1.3 Goals
- Streamline developer/tester workflow by eliminating need for direct database access during testing
- Provide granular control over data clearing operations (independent selection of data types)
- Reduce risk of accidental data loss through confirmation dialogs and explicit selection
- Enable rapid iteration on import and enrichment features by making data reset fast and safe
- Maintain data integrity by preventing cascade deletions and requiring explicit selection per data type

### 1.4 Non-Goals (Out of Scope)
- **Audit logging or persistent deletion history** - No tracking of what was deleted, when, or by whom
- **Cascade clearing or automatic relationship cleanup** - Each data type must be explicitly selected; no automatic deletion of related data
- **Rollback or undo capability** - Deletions are permanent; no transaction support or restore functionality
- **Detailed progress indication** - Only simple "in progress" message; no progress bars or percentage completion
- **Access control or user permissions** - Available to all users (appropriate for local-only application)
- **Data export before deletion** - No backup or archive functionality
- **Selective filtering within data types** - Clears all records of selected type; no date range or conditional filtering
- **Production environment use** - Explicitly designed for development and testing only

---

## 2. User Stories

### 2.1 Primary User Story
**As a** developer working on transaction import features
**I want to** selectively clear transaction data, enrichment cache, and import history
**So that** I can test import workflows repeatedly with clean data states without manual database operations or full database resets

### 2.2 Additional User Stories
- **As a** tester validating Amazon order matching, **I want to** clear only Amazon-related data (orders and matches) **so that** I can re-test the matching algorithm without affecting bank transaction data
- **As a** developer debugging LLM enrichment, **I want to** clear only the enrichment cache **so that** I can force re-enrichment of transactions without re-importing them
- **As a** developer testing TrueLayer integration, **I want to** clear TrueLayer transactions and import history independently **so that** I can test incremental sync behavior with different data scenarios
- **As a** tester, **I want to** see confirmation before deletion and a summary of what was cleared **so that** I understand the impact and can verify the operation succeeded
- **As a** developer, **I want to** clear category rules during testing **so that** I can validate rule generation and application from scratch

---

## 3. Functional Requirements

### 3.1 Required Behaviors
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-001 | Display "Dev Tools" collapsible section at bottom of Settings page | Must Have |
| FR-002 | Render nine checkboxes grouped by category (Bank Data, Linked Data, Metadata) | Must Have |
| FR-003 | Show "Are you sure?" confirmation dialog when user clicks "Clear Selected Data" button | Must Have |
| FR-004 | Only enable "Clear Selected Data" button when at least one checkbox is selected | Must Have |
| FR-005 | Support independent selection/deselection of each data type (no cascade selection) | Must Have |
| FR-006 | Execute clearing operation asynchronously (non-blocking UI) | Should Have |
| FR-007 | Display "Clearing in progress..." message during operation | Should Have |
| FR-008 | Show modal with summary counts of deleted items after successful completion | Must Have |
| FR-009 | Display error message with failure details if clearing operation fails | Must Have |
| FR-010 | Return JSON response with counts per data type from API endpoint | Must Have |
| FR-011 | Collapse "Dev Tools" section by default (user must expand to access) | Should Have |
| FR-012 | Clear all checkboxes after successful clearing operation | Should Have |

### 3.2 Input/Output Specifications

**Inputs:**
- **Selected Data Types** (Array of strings): User-selected checkboxes from the following allowed values:
  - `truelayer_transactions` - TrueLayer bank transactions
  - `legacy_transactions` - Legacy Santander Excel import transactions
  - `amazon_orders` - Amazon order data
  - `amazon_matches` - Amazon-to-transaction match records
  - `apple_transactions` - Apple transaction data
  - `apple_matches` - Apple-to-transaction match records
  - `enrichment_cache` - LLM enrichment metadata cache
  - `import_history` - Import job history records
  - `category_rules` - Transaction categorization rules

  **Validation Rules:**
  - At least one data type must be selected
  - Only values from allowed list accepted
  - Empty array or unknown types rejected with 400 error

- **User Confirmation** (Boolean): Result of "Are you sure?" dialog
  - `true` - User confirmed, proceed with clearing
  - `false` - User cancelled, abort operation

**Outputs:**
- **Success Response** (JSON object):
  ```json
  {
    "success": true,
    "cleared": {
      "truelayer_transactions": 523,
      "legacy_transactions": 0,
      "amazon_orders": 0,
      "amazon_matches": 0,
      "apple_transactions": 0,
      "apple_matches": 0,
      "enrichment_cache": 45,
      "import_history": 8,
      "category_rules": 0
    }
  }
  ```
  - `success` (boolean): Always `true` in success response
  - `cleared` (object): Map of data type to count of deleted records
  - Counts are integers >= 0
  - All nine data types must be present in response, even if count is 0

- **Error Response** (JSON object):
  ```json
  {
    "success": false,
    "error": "Failed to clear truelayer_transactions: database connection lost"
  }
  ```
  - `success` (boolean): Always `false` in error response
  - `error` (string): Human-readable error message describing failure

- **Summary Modal Display** (UI component):
  - Heading: "Data Cleared Successfully"
  - Body: Line-separated list of cleared data types with counts, excluding types with 0 count
  - Example:
    ```
    TrueLayer Transactions: 523 deleted
    LLM Enrichment Cache: 45 deleted
    Import Job History: 8 deleted
    ```
  - Close button to dismiss modal

### 3.3 Business Rules
1. **Independent Clearing Rule**: Each data type clears independently; selecting "TrueLayer Transactions" does NOT automatically clear "Import History" or any related data
2. **No Cascade Deletion**: Deleting Amazon Matches does not delete Amazon Orders; deleting transactions does not delete enrichment cache; user must explicitly select all desired types
3. **Fail-Fast Behavior**: If clearing any single data type fails, stop immediately, return error, and do not attempt to clear remaining selected types
4. **Zero-Count Acceptance**: Clearing a data type with 0 records is valid and succeeds (not treated as error)
5. **Local-Only Operation**: All clearing happens on local database only; no external API calls or remote data deletion
6. **No Soft Deletes**: Data is permanently deleted from database (hard delete); no soft-delete flags or archival
7. **Confirmation Required**: Destructive operation requires explicit user confirmation via dialog; no silent or auto-clearing

---

## 4. Technical Requirements

### 4.1 Database Changes

**New Tables:**
- None (feature uses existing tables only)

**Modified Tables:**
- None (no schema changes required)

**Tables Affected by Clearing Operations:**
| Table Name | Data Type Mapping | Clearing Method |
|------------|-------------------|-----------------|
| `truelayer_transactions` | `truelayer_transactions` | `DELETE FROM truelayer_transactions` |
| `transactions` | `legacy_transactions` | `DELETE FROM transactions` |
| `amazon_orders` | `amazon_orders` | `DELETE FROM amazon_orders` |
| `amazon_transaction_matches` | `amazon_matches` | `DELETE FROM amazon_transaction_matches` |
| `apple_transactions` | `apple_transactions` | `DELETE FROM apple_transactions` |
| `apple_transaction_matches` | `apple_matches` | `DELETE FROM apple_transaction_matches` |
| `llm_enrichment_metadata` | `enrichment_cache` | `DELETE FROM llm_enrichment_metadata` |
| `import_jobs` | `import_history` | `DELETE FROM import_jobs` |
| `transaction_categories` | `category_rules` | `DELETE FROM transaction_categories` |

**Database Function Requirements:**
- Must use PostgreSQL connection from `database_postgres.py` module
- Must execute each DELETE operation in separate statement (no batching)
- Must capture row count using `cursor.rowcount` after each DELETE
- Must handle database exceptions and convert to API error responses

### 4.2 API Changes

**New Endpoints:**
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/testing/clear` | Clear selected data types and return summary counts |

**Request/Response Schemas:**

```json
// POST /api/testing/clear
// Request (Query Parameters)
// URL: /api/testing/clear?types=truelayer_transactions,amazon_orders,enrichment_cache

// No request body required
// Query Parameters:
// - types (string, required): Comma-separated list of data types to clear
//   Valid values: truelayer_transactions, legacy_transactions, amazon_orders,
//                 amazon_matches, apple_transactions, apple_matches,
//                 enrichment_cache, import_history, category_rules

// Success Response (200 OK)
{
  "success": true,
  "cleared": {
    "truelayer_transactions": 523,
    "legacy_transactions": 0,
    "amazon_orders": 0,
    "amazon_matches": 0,
    "apple_transactions": 0,
    "apple_matches": 0,
    "enrichment_cache": 45,
    "import_history": 8,
    "category_rules": 0
  }
}

// Error Response (400 Bad Request - Invalid Input)
{
  "success": false,
  "error": "Invalid data type: invalid_type. Allowed types: truelayer_transactions, legacy_transactions, amazon_orders, amazon_matches, apple_transactions, apple_matches, enrichment_cache, import_history, category_rules"
}

// Error Response (400 Bad Request - No Types Selected)
{
  "success": false,
  "error": "No data types specified. At least one type must be selected."
}

// Error Response (500 Internal Server Error - Database Failure)
{
  "success": false,
  "error": "Failed to clear truelayer_transactions: database connection lost"
}
```

**API Implementation Requirements:**
- Validate `types` query parameter is present and non-empty
- Parse comma-separated types and validate each against allowed list
- Return 400 error if validation fails
- Execute DELETE operations sequentially in order received
- Stop on first error (fail-fast)
- Return 500 error with specific failure message if any DELETE fails
- Return 200 with counts object if all operations succeed
- Use database connection pooling (existing infrastructure)
- Set reasonable timeout (30 seconds max for entire operation)

### 4.3 Frontend Changes

**New Components:**
- [x] **New component required:** `TestingDashboard.tsx`
  - Renders "Dev Tools" collapsible section
  - Contains checkbox groups and clear button
  - Handles confirmation dialog
  - Displays progress message and result modal
  - Location: `/frontend/src/components/TestingDashboard.tsx`

**Modified Components:**
- [x] **Modify existing:** `Settings.tsx` (Settings page)
  - Import and render `<TestingDashboard />` component
  - Position at bottom of page (after existing settings sections)
  - No props required (component is self-contained)

**Component Specifications:**

**TestingDashboard.tsx Structure:**
```typescript
interface DataTypeCheckbox {
  id: string;           // e.g., 'truelayer_transactions'
  label: string;        // e.g., 'TrueLayer Transactions'
  checked: boolean;
}

interface ClearResponse {
  success: boolean;
  cleared?: Record<string, number>;
  error?: string;
}

const DATA_TYPE_GROUPS = {
  "Bank Data": [
    { id: "truelayer_transactions", label: "TrueLayer Transactions" },
    { id: "legacy_transactions", label: "Legacy Transactions" }
  ],
  "Linked Data": [
    { id: "amazon_orders", label: "Amazon Orders" },
    { id: "amazon_matches", label: "Amazon Matches" },
    { id: "apple_transactions", label: "Apple Transactions" },
    { id: "apple_matches", label: "Apple Matches" }
  ],
  "Metadata": [
    { id: "enrichment_cache", label: "LLM Enrichment Cache" },
    { id: "import_history", label: "Import Job History" },
    { id: "category_rules", label: "Category Rules" }
  ]
};

// Component manages:
// - Checkbox state for all 9 data types
// - Collapsed/expanded state of section
// - Loading state during API call
// - Confirmation dialog state
// - Result modal state and content
```

**UI Framework Usage:**
- Use **Tailwind CSS v4** for styling
- Use **daisyUI** components for:
  - Collapse component (collapsible section)
  - Checkbox components (data type selection)
  - Button component (Clear Selected Data)
  - Modal component (confirmation and result modals)
  - Alert component (error messages)
- Follow existing Settings page styling patterns for consistency

### 4.4 Dependencies

**Backend Dependencies:**
- Python `psycopg2` library (existing) - PostgreSQL database operations
- Flask framework (existing) - API endpoint routing
- `database_postgres.py` module (existing) - Database connection and query execution

**Frontend Dependencies:**
- React (existing) - Component framework
- TypeScript (existing) - Type safety
- Tailwind CSS v4 (existing) - Styling
- daisyUI (existing) - UI component library
- Fetch API (browser native) - HTTP requests to backend

**No New External Dependencies Required** - Feature uses existing project infrastructure only

---

## 5. UI/UX Requirements

### 5.1 User Flow

**Primary Flow (Happy Path):**
1. User navigates to Settings page
2. User scrolls to bottom and sees collapsed "Dev Tools" section
3. User clicks "Dev Tools" header to expand section
4. System displays grouped checkboxes and disabled "Clear Selected Data" button
5. User selects one or more checkboxes (e.g., TrueLayer Transactions, LLM Enrichment Cache, Import History)
6. System enables "Clear Selected Data" button
7. User clicks "Clear Selected Data" button
8. System shows "Are you sure?" confirmation dialog with selected data types listed
9. User clicks "Yes" in confirmation dialog
10. System closes confirmation dialog and shows "Clearing in progress..." message
11. System sends POST request to `/api/testing/clear` with selected types
12. Backend deletes data and returns success response with counts
13. System hides progress message and displays summary modal:
    ```
    Data Cleared Successfully

    TrueLayer Transactions: 523 deleted
    LLM Enrichment Cache: 45 deleted
    Import Job History: 8 deleted
    ```
14. User clicks "Close" on modal
15. System closes modal, clears all checkboxes, and disables button

**Cancellation Flow:**
1. (Steps 1-8 same as primary flow)
2. User clicks "Cancel" in confirmation dialog
3. System closes dialog and takes no action (checkboxes remain selected)

**Error Flow:**
1. (Steps 1-11 same as primary flow)
2. Backend encounters error (e.g., database connection lost)
3. Backend returns error response: `{"success": false, "error": "Failed to clear truelayer_transactions: database connection lost"}`
4. System hides progress message and displays error alert:
   ```
   Error Clearing Data
   Failed to clear truelayer_transactions: database connection lost
   ```
5. User dismisses error alert
6. System keeps checkboxes selected (allows user to retry)

**Empty Selection Flow:**
1. (Steps 1-4 same as primary flow)
2. User attempts to click "Clear Selected Data" button (disabled state prevents click)
3. No action occurs (button remains disabled until checkbox selected)

### 5.2 Wireframes/Mockups

**Visual Layout (Text-Based Mockup):**

```
Settings Page
─────────────────────────────────────────────────
[Other Settings Sections Above...]

┌─────────────────────────────────────────────┐
│ ▶ Dev Tools (Collapsed by default)         │
└─────────────────────────────────────────────┘

[After clicking to expand:]

┌─────────────────────────────────────────────┐
│ ▼ Dev Tools                                 │
├─────────────────────────────────────────────┤
│                                             │
│ Warning: Clearing data is permanent and     │
│ cannot be undone. Use for testing only.     │
│                                             │
│ Bank Data                                   │
│   ☐ TrueLayer Transactions                  │
│   ☐ Legacy Transactions                     │
│                                             │
│ Linked Data                                 │
│   ☐ Amazon Orders                           │
│   ☐ Amazon Matches                          │
│   ☐ Apple Transactions                      │
│   ☐ Apple Matches                           │
│                                             │
│ Metadata                                    │
│   ☐ LLM Enrichment Cache                    │
│   ☐ Import Job History                      │
│   ☐ Category Rules                          │
│                                             │
│ [Clear Selected Data] (disabled)            │
│                                             │
└─────────────────────────────────────────────┘

[After selecting checkboxes:]

│ Bank Data                                   │
│   ☑ TrueLayer Transactions                  │
│   ☐ Legacy Transactions                     │
│                                             │
│ Metadata                                    │
│   ☑ LLM Enrichment Cache                    │
│   ☑ Import Job History                      │
│   ☐ Category Rules                          │
│                                             │
│ [Clear Selected Data] (enabled, red)        │

[Confirmation Dialog:]

┌─────────────────────────────────────────────┐
│ Are you sure?                               │
├─────────────────────────────────────────────┤
│                                             │
│ You are about to permanently delete:        │
│                                             │
│ • TrueLayer Transactions                    │
│ • LLM Enrichment Cache                      │
│ • Import Job History                        │
│                                             │
│ This action cannot be undone.               │
│                                             │
│         [Cancel]  [Yes, Clear Data]         │
│                                             │
└─────────────────────────────────────────────┘

[During Operation:]

│ Clearing in progress...                     │

[Success Modal:]

┌─────────────────────────────────────────────┐
│ Data Cleared Successfully                   │
├─────────────────────────────────────────────┤
│                                             │
│ TrueLayer Transactions: 523 deleted         │
│ LLM Enrichment Cache: 45 deleted            │
│ Import Job History: 8 deleted               │
│                                             │
│                  [Close]                    │
│                                             │
└─────────────────────────────────────────────┘
```

**Design Specifications:**
- **Section Header**: Use daisyUI collapse component with chevron icon indicating expand/collapse state
- **Warning Message**: Display in yellow/amber alert box at top of expanded section
- **Checkbox Groups**: Use semantic headings (h4 or h5) for group names; indent checkboxes slightly
- **Button State**:
  - Disabled: Gray background, no hover effect, cursor not-allowed
  - Enabled: Red/destructive color (daisyUI btn-error), hover darkens
- **Confirmation Dialog**: Modal dialog, centered, with destructive action highlighted in red
- **Progress Message**: Centered, with optional spinner/loading icon
- **Result Modal**: Success state with green accent; displays only non-zero counts

### 5.3 Error Handling

| Error Condition | User Message | System Behavior |
|-----------------|--------------|-----------------|
| No data types selected | *(Button disabled - no message)* | "Clear Selected Data" button remains disabled; click has no effect |
| Invalid data type sent to API | "Invalid data type: [type]. Please refresh and try again." | Display error alert; keep selections; allow retry |
| Database connection failure | "Database connection lost. Please check that the database is running and try again." | Display error alert with technical details from API response |
| Individual DELETE fails | "Failed to clear [data type]: [error message]" | Display error alert; stop clearing remaining types; keep selections |
| Network request timeout | "Request timed out. Please try again." | Display error alert; keep selections; allow retry |
| API returns non-JSON response | "Unexpected response from server. Please try again or contact support." | Display generic error alert; log response to console for debugging |
| User cancels during operation | *(Not applicable - operation not cancellable once started)* | N/A - operation runs to completion or failure |

**Error Display Pattern:**
- Use daisyUI alert component with error/danger styling (red accent)
- Position alert at top of Dev Tools section (above checkboxes)
- Include dismiss button to close alert
- Preserve user selections after error (allow immediate retry)
- Log detailed error to browser console for developer debugging

---

## 6. Acceptance Criteria

**The feature is complete when:**

- [ ] **AC-001**: Settings page displays "Dev Tools" collapsible section at bottom, collapsed by default
- [ ] **AC-002**: Expanding "Dev Tools" reveals warning message and nine checkboxes organized into three groups (Bank Data, Linked Data, Metadata)
- [ ] **AC-003**: "Clear Selected Data" button is disabled when no checkboxes are selected
- [ ] **AC-004**: "Clear Selected Data" button becomes enabled when at least one checkbox is selected
- [ ] **AC-005**: Clicking "Clear Selected Data" displays confirmation dialog listing selected data types
- [ ] **AC-006**: Clicking "Cancel" in confirmation dialog closes dialog and takes no action
- [ ] **AC-007**: Clicking "Yes, Clear Data" in confirmation dialog shows "Clearing in progress..." message
- [ ] **AC-008**: API endpoint `/api/testing/clear` accepts comma-separated `types` query parameter
- [ ] **AC-009**: API returns 400 error if `types` parameter is missing or contains invalid values
- [ ] **AC-010**: API successfully deletes data from all selected data types when valid request received
- [ ] **AC-011**: API returns JSON response with `success: true` and count for each data type (including 0 counts)
- [ ] **AC-012**: Frontend displays success modal showing only non-zero counts after successful clearing
- [ ] **AC-013**: Success modal lists cleared data types with human-readable labels and counts (e.g., "TrueLayer Transactions: 523 deleted")
- [ ] **AC-014**: Closing success modal clears all checkboxes and disables button
- [ ] **AC-015**: API returns 500 error with descriptive message if any DELETE operation fails
- [ ] **AC-016**: Frontend displays error alert with message from API response when operation fails
- [ ] **AC-017**: Error alert preserves user checkbox selections to allow retry
- [ ] **AC-018**: Clearing operation executes asynchronously without blocking UI interaction
- [ ] **AC-019**: Each data type can be independently selected and cleared without affecting other types
- [ ] **AC-020**: Clearing "TrueLayer Transactions" does NOT cascade to delete enrichment cache or import history
- [ ] **AC-021**: All nine data types correctly map to their corresponding database tables
- [ ] **AC-022**: Component uses TypeScript with proper type definitions (no `any` types)
- [ ] **AC-023**: Component follows existing Settings page styling patterns (Tailwind + daisyUI)
- [ ] **AC-024**: Feature works correctly when database has 0 records (returns 0 counts without error)
- [ ] **AC-025**: Documentation updated (requirements document committed to `.claude/docs/requirements/`)

---

## 7. Open Questions

| # | Question | Answer | Status |
|---|----------|--------|--------|
| 1 | Should the Dev Tools section have an icon or badge indicating it's for development use only? | Not required - section title and warning message sufficient | Resolved |
| 2 | Should we add a "Select All" / "Deselect All" convenience button? | Out of scope for initial implementation - can be added later if user feedback indicates need | Resolved |
| 3 | Should clearing category rules also prompt additional confirmation since it affects categorization logic? | No - single confirmation sufficient; all operations equally destructive | Resolved |
| 4 | Should we display timestamp of when data was last cleared? | Out of scope - no persistent logging or history tracking | Resolved |
| 5 | Should the feature be hidden behind a feature flag or environment variable check? | Not required - local-only app context means no production risk | Resolved |

---

## 8. Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2025-11-29 | Requirements Development Agent | Initial draft based on stakeholder elicitation |

---

## Approval

- [ ] Requirements reviewed with stakeholder
- [ ] Technical feasibility confirmed
- [ ] Ready for implementation

**Approved for implementation:** Pending
**Approved by:** [Awaiting Stakeholder Review]
**Date:** [Pending]

---

## Appendix A: Database Table Reference

**Tables Affected by Clearing Operations (Actual Database Schema):**

| Data Type | Table Name | Key Columns | Typical Record Count |
|-----------|------------|-------------|---------------------|
| `truelayer_transactions` | `truelayer_transactions` | id, transaction_id, account_id, timestamp, amount, description | High (hundreds to thousands) |
| `legacy_transactions` | `transactions` | id, date, description, amount, category, source_file | Low to Medium (legacy data only) |
| `amazon_orders` | `amazon_orders` | id, order_id, order_date, total, item_description | Medium (varies by user) |
| `amazon_matches` | `amazon_transaction_matches` | id, transaction_id, amazon_order_id | Low to Medium |
| `apple_transactions` | `apple_transactions` | id, transaction_id, transaction_date, amount, description | Low to Medium |
| `apple_matches` | `apple_transaction_matches` | id, transaction_id, apple_transaction_id | Low to Medium |
| `enrichment_cache` | `llm_enrichment_cache` | id, transaction_id, enrichment_data | Medium to High (caching layer) |
| `import_history` | `truelayer_import_jobs` | id, user_id, status, created_at, updated_at | Low (job tracking only) |
| `category_rules` | `category_keywords` | id, category_name, keyword, priority | Low (configuration data) |

**Referential Integrity Notes:**
- Deleting transactions does NOT cascade to enrichment_cache (orphaned records acceptable)
- Deleting import_history does NOT cascade to imported transactions (records remain)
- Deleting matches does NOT cascade to source records (orders/transactions remain)
- Deleting category_rules does NOT cascade to transactions (category values remain as-is)

---

## Appendix B: Example API Usage

**Request Examples:**

```bash
# Clear single data type
curl -X POST "http://localhost:5000/api/testing/clear?types=enrichment_cache"

# Clear multiple data types
curl -X POST "http://localhost:5000/api/testing/clear?types=truelayer_transactions,import_history,enrichment_cache"

# Clear all bank data
curl -X POST "http://localhost:5000/api/testing/clear?types=truelayer_transactions,legacy_transactions"
```

**Response Examples:**

```json
// Successful clearing (some data deleted)
{
  "success": true,
  "cleared": {
    "truelayer_transactions": 523,
    "legacy_transactions": 0,
    "amazon_orders": 0,
    "amazon_matches": 0,
    "apple_transactions": 0,
    "apple_matches": 0,
    "enrichment_cache": 45,
    "import_history": 8,
    "category_rules": 0
  }
}

// Successful clearing (no data to delete)
{
  "success": true,
  "cleared": {
    "truelayer_transactions": 0,
    "legacy_transactions": 0,
    "amazon_orders": 0,
    "amazon_matches": 0,
    "apple_transactions": 0,
    "apple_matches": 0,
    "enrichment_cache": 0,
    "import_history": 0,
    "category_rules": 0
  }
}

// Error: Invalid data type
{
  "success": false,
  "error": "Invalid data type: invalid_type. Allowed types: truelayer_transactions, legacy_transactions, amazon_orders, amazon_matches, apple_transactions, apple_matches, enrichment_cache, import_history, category_rules"
}

// Error: Database failure (fail-fast on first error)
{
  "success": false,
  "error": "Failed to clear truelayer_transactions: FATAL:  terminating connection due to administrator command"
}
```

---

## Appendix C: Frontend Component Integration Example

**Settings.tsx Integration:**

```typescript
// File: /frontend/src/pages/Settings.tsx

import TestingDashboard from '../components/TestingDashboard';

export default function Settings() {
  return (
    <div className="container mx-auto p-4">
      <h1 className="text-3xl font-bold mb-6">Settings</h1>

      {/* Existing settings sections */}
      <TrueLayerSettings />
      <EnrichmentSettings />
      <HuququllahSettings />

      {/* New Testing Dashboard section at bottom */}
      <div className="mt-8">
        <TestingDashboard />
      </div>
    </div>
  );
}
```

**Component Props:**
- No props required - component is fully self-contained
- Manages own state for checkboxes, modals, loading states
- Makes API calls directly without parent coordination
