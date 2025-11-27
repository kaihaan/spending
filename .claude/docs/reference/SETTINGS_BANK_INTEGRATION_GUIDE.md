# Settings Page - Bank Integration Details

## Overview

Enhanced the Settings page with a comprehensive view of connected banks, displaying all associated accounts and cards in a collapsible accordion format.

## Components Created

### 1. BankIntegrationDetails.tsx (Main Container)
**Location:** `frontend/src/components/BankIntegrationDetails.tsx`

Responsibilities:
- Fetches account and card data from TrueLayer API endpoints
- Combines data by bank/connection
- Manages loading and error states
- Implements refresh functionality to re-discover accounts and cards
- Listens for bank connection updates via window events

**Features:**
- Displays statistics (total accounts and cards)
- "Refresh Accounts & Cards" button with loading spinner
- Error handling with user-friendly messages
- Auto-updates when bank operations complete
- Empty state message when no banks are connected

**API Endpoints Used:**
- `GET /api/truelayer/accounts` - Fetch all connected accounts
- `GET /api/truelayer/cards` - Fetch all connected cards
- `POST /api/truelayer/fetch-accounts` - Trigger account sync
- `POST /api/truelayer/fetch-cards` - Trigger card discovery & sync

---

### 2. BankAccordionItem.tsx (Per-Bank Accordion)
**Location:** `frontend/src/components/BankAccordionItem.tsx`

Responsibilities:
- Displays a single bank in accordion format
- Shows bank connection status as a badge
- Organizes accounts and cards into separate subsections
- Renders child AccountCard and CardDisplay components

**Features:**
- Collapsible accordion using DaisyUI `collapse` component
- Status badge showing connection health (active/inactive/expired)
- Count badges showing number of accounts and cards
- Clean visual separation between accounts and cards sections
- Responsive layout

**Displayed Information:**
- Bank name
- Connection status (color-coded)
- Number of accounts and cards
- Nested accounts list
- Nested cards list

---

### 3. AccountCard.tsx (Individual Account Display)
**Location:** `frontend/src/components/AccountCard.tsx`

Responsibilities:
- Displays a single bank account with key details
- Shows sync status with visual indicator
- Formats timestamps in human-readable format

**Features:**
- Account display name and type
- Currency badge
- Sync status indicator (colored dot: green=current, yellow=stale, red=very old)
- Last synced timestamp (relative format: "2h ago", "3d ago", etc.)
- Hover tooltip showing full timestamp
- DaisyUI card styling with hover effect

**Sync Status Colors:**
- 🟢 **Green** - Synced within 24 hours (current)
- 🟡 **Yellow** - Synced 1-3 days ago (getting stale)
- 🔴 **Red** - Synced more than 3 days ago or never (stale)

---

### 4. CardDisplay.tsx (Individual Card Display)
**Location:** `frontend/src/components/CardDisplay.tsx`

Responsibilities:
- Displays a single credit/debit card with key details
- Shows sync status with visual indicator
- Formats timestamps in human-readable format
- Displays masked card information

**Features:**
- Card name and type
- Last 4 digits (masked for security)
- Card issuer name (if available)
- Currency badge
- Sync status indicator (colored dot)
- Last synced timestamp (relative format)
- Hover tooltip showing full timestamp
- DaisyUI card styling with hover effect

**Card Information Display:**
- Card name (e.g., "Chase Sapphire")
- Card type (Credit, Debit, Prepaid, etc.)
- Last 4 digits badge (e.g., "•••• 4242")
- Issuer badge (e.g., "Chase", "Visa")

---

## Integration with Settings Page

### File Modified
- `frontend/src/pages/Settings.tsx`

### Changes Made

1. **Added Import**
```typescript
import BankIntegrationDetails from '../components/BankIntegrationDetails';
```

2. **Added Section** (after TrueLayerIntegration)
```jsx
{/* Bank Integration Details Section */}
<div className="mb-8">
  <h2 className="text-xl font-semibold mb-4">Connected Banks - Accounts & Cards</h2>
  <BankIntegrationDetails />
</div>
```

### Section Location
Positioned after:
- Account Mappings
- Amazon Order History
- Amazon Returns
- Apple Transactions
- TrueLayer Bank Integration (basic view)

---

## User Interface

### Layout Structure

```
┌─ Settings Page
│
├─ Account Mappings Section
├─ Amazon Order History
├─ Amazon Returns
├─ Apple Transactions
├─ TrueLayer Bank Integration (basic)
│
└─ Connected Banks - Accounts & Cards ◄── NEW
   │
   ├─ Statistics Bar
   │  ├─ [✓] X Accounts badge
   │  └─ [✓] Y Cards badge
   │
   ├─ [🔄] Refresh Accounts & Cards Button
   │
   └─ Bank Accordions
      │
      ├─ [▼] Bank 1 (Active)
      │  ├─ Accounts (3)
      │  │  ├─ Checking Account (GBP) - Green (2h ago)
      │  │  ├─ Savings Account (GBP) - Yellow (2d ago)
      │  │  └─ Student Account (GBP) - Green (1h ago)
      │  │
      │  └─ Cards (2)
      │     ├─ Chase Sapphire (•••• 4242) - Green (1h ago)
      │     └─ Amazon Prime Card (•••• 1234) - Yellow (1d ago)
      │
      └─ [▶] Bank 2 (Active)
         └─ (expandable)
```

### DaisyUI Components Used

1. **Collapse** - Accordion per bank
   - `collapse collapse-arrow` - Accordion with arrow indicator
   - `collapse-title` - Bank header with status
   - `collapse-content` - Expanded content with accounts/cards

2. **Badge** - Status and count indicators
   - `badge-primary` - Account count
   - `badge-secondary` - Card count
   - `badge-success` - Active status
   - `badge-warning` - Inactive status
   - `badge-error` - Expired status
   - `badge-neutral` - Currency and last 4 digits
   - `badge-outline` - Card issuer
   - `badge-sm` - Small badges

3. **Card** - Account and card displays
   - `card bg-base-200` - Lightweight card styling
   - `card-body` - Content container
   - Hover effects with `shadow-md`

4. **Button** - Refresh action
   - `btn btn-sm btn-outline` - Refresh button
   - Loading spinner during refresh
   - Disabled state while refreshing

5. **Tooltip** - Timestamp details
   - `tooltip` class with `data-tip` attribute
   - Shows full timestamp on hover over sync indicator

---

## Data Flow

### Initial Load
```
BankIntegrationDetails mounts
    ↓
useEffect: fetchBankDetails()
    ↓
Parallel fetch:
  - GET /api/truelayer/accounts
  - GET /api/truelayer/cards
    ↓
Combine data by connection_id
    ↓
Render BankAccordionItem for each bank
    ↓
Each accordion renders:
  - AccountCard for each account
  - CardDisplay for each card
```

### Refresh Action
```
User clicks "Refresh Accounts & Cards"
    ↓
POST /api/truelayer/fetch-accounts (sync accounts)
POST /api/truelayer/fetch-cards (discover & sync cards)
    ↓
Loading spinner shown
    ↓
Both requests complete
    ↓
fetchBankDetails() called
    ↓
Display updated with new data
```

### Event-Driven Updates
```
Window event: 'bank-connected'
    ↓
Listener triggers fetchBankDetails()
    ↓
Display refreshes automatically

Window event: 'transactions-updated'
    ↓
Listener triggers fetchBankDetails()
    ↓
Display refreshes automatically
```

---

## Features Delivered

✅ **Accordion Layout Per Bank**
- Collapsible accordion for each connected bank
- Expands to show accounts and cards

✅ **Organized Display**
- Accounts section with all linked bank accounts
- Cards section with all linked credit/debit cards
- Separate subsections with visual dividers

✅ **Account Details**
- Display name and account type
- Currency badge
- Last synced timestamp (relative format)
- Sync status indicator (color-coded)

✅ **Card Details**
- Card name and type
- Last 4 digits (masked)
- Card issuer (if available)
- Last synced timestamp (relative format)
- Sync status indicator (color-coded)

✅ **Refresh Functionality**
- "Refresh Accounts & Cards" button
- Triggers auto-discovery from TrueLayer API
- Syncs transactions for discovered accounts/cards
- Loading spinner during operation
- Auto-updates display with new data

✅ **Visual Status Indicators**
- Color-coded sync status (green/yellow/red)
- Hover tooltips with full timestamp
- Connection status badge
- Account and card count badges

✅ **Error Handling**
- Loading spinner on initial load
- Error messages for failed operations
- Empty state message when no banks connected
- Graceful fallbacks

✅ **Responsive Design**
- Mobile-friendly layout
- Stacked cards on smaller screens
- Touch-friendly accordions

---

## Styling Details

### Colors & Status
- **Green (text-success)** - Synced within 24 hours
- **Yellow (text-warning)** - Synced 1-3 days ago
- **Red (text-error)** - Synced 3+ days ago or never

### Spacing
- Cards: `p-3` padding
- Sections: `mb-8` spacing between major sections
- Internal spacing: `gap-2` to `gap-3` between elements

### Typography
- Bank name: `font-semibold text-base`
- Account/Card name: `font-semibold text-sm`
- Type/Info: `text-xs text-base-content/60`
- Timestamp: `text-xs text-base-content/60`

---

## Browser Compatibility

✅ Chrome/Chromium (latest)
✅ Firefox (latest)
✅ Safari (latest)
✅ Mobile browsers (iOS Safari, Chrome)

Requires:
- ES2020+ JavaScript support
- CSS Grid support
- CSS Flexbox support

---

## Performance Considerations

### Data Fetching
- Parallel requests for accounts and cards (faster loading)
- Data combined client-side (no extra API calls)
- Window event listeners clean up on unmount

### Rendering
- Accordion items only rendered for connected banks
- Accounts/Cards rendered in lists (no nested loops)
- DaisyUI components are lightweight

### User Experience
- Refresh button disabled while loading
- Loading spinner provides visual feedback
- Timestamps calculated client-side (no re-fetches)

---

## Future Enhancement Ideas

1. **Transaction Count** - Show number of synced transactions per account/card
2. **Balance Display** - Show current balance for each account/card
3. **Quick Actions** - Sync individual accounts or cards without full refresh
4. **Details Modal** - Click to see more information about specific accounts/cards
5. **Filter/Search** - Search by account/card name or type
6. **Export** - Export account list as CSV
7. **Alerts** - Notify when sync is stale (>24 hours)
8. **Charts** - Historical balance charting for cards

---

## Testing Checklist

✅ Component renders without errors
✅ Loads account and card data correctly
✅ Displays banks in accordion format
✅ Expands/collapses accordion items
✅ Shows status indicators correctly
✅ Refresh button triggers sync operations
✅ Loading spinner displays during refresh
✅ Error messages display properly
✅ Empty state shows when no banks connected
✅ Window event listeners work correctly
✅ Responsive layout on mobile devices
✅ Timestamps format correctly

---

## File Locations

- **New Components:**
  - `frontend/src/components/BankIntegrationDetails.tsx` (Main container)
  - `frontend/src/components/BankAccordionItem.tsx` (Accordion item)
  - `frontend/src/components/AccountCard.tsx` (Account display)
  - `frontend/src/components/CardDisplay.tsx` (Card display)

- **Modified Files:**
  - `frontend/src/pages/Settings.tsx` (Added import and section)

---

## Dependencies

- React 19.1.1 (hooks: useState, useEffect)
- Axios 1.12.2 (HTTP requests)
- DaisyUI 5.3.7 (UI components)
- Tailwind CSS 4.1.14 (styling)

No additional dependencies required.

