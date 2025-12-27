# Bank Integration - Troubleshooting Guide

## Issue: No Cards or Accounts Showing

### Root Cause
The TrueLayer sandbox environment has **no test banks connected yet**. The APIs are working correctly, but there are no actual accounts or cards to display.

### Evidence
API responses show empty arrays:
```bash
GET /api/truelayer/accounts
{
  "connections": [
    {
      "id": 3,
      "connection_status": "active",
      "accounts": [],      # ← Empty!
      "last_synced_at": null
    }
  ]
}

GET /api/truelayer/cards
{
  "connections": [
    {
      "connection_id": 3,
      "cards": [],         # ← Empty!
      "connection_status": "active"
    }
  ]
}

POST /api/truelayer/fetch-accounts
{
  "result": {
    "total_accounts": 0,  # ← No accounts to sync
    "total_synced": 0
  }
}

POST /api/truelayer/fetch-cards
{
  "result": {
    "total_cards": 0,     # ← No cards to discover
    "total_synced": 0
  }
}
```

## Solution: Connect Test Bank in TrueLayer Sandbox

### Step 1: Go to Settings Page
1. Navigate to the Settings page in your app
2. Scroll to "TrueLayer Bank Integration" section

### Step 2: Click "Connect Bank"
1. Click the "Connect Bank" button
2. This will redirect you to TrueLayer's sandbox authorization page

### Step 3: Select Test Bank
In the TrueLayer sandbox, you can select from test providers:
- **Barclays** (test)
- **HSBC** (test)
- **Lloyds** (test)
- **NatWest** (test)
- etc.

### Step 4: Select Test Accounts
The TrueLayer sandbox provides mock accounts and cards:
- Current accounts (transaction accounts)
- Savings accounts
- Credit cards
- Debit cards

Select the accounts/cards you want to connect.

### Step 5: Authorize
Complete the OAuth flow by clicking "Authorize"

### Step 6: Verify Connection
After authorization completes:
1. You'll be redirected back to your app
2. The "TrueLayer Bank Integration" section should show your connected bank
3. The browser will show a success message

### Step 7: View in Bank Integration Details
Once connected, the "Connected Banks - Accounts & Cards" section will show:
- Your connected bank(s)
- All accounts with sync status
- All cards with sync status
- Last synced timestamps

### Step 8: Refresh to Load Data
Click "Refresh Accounts & Cards" to:
1. Discover all connected accounts from TrueLayer API
2. Discover all connected cards from TrueLayer API
3. Sync transactions for each account/card
4. Update the UI with the data

## How to Verify Setup is Working

### 1. Check Backend APIs with curl

**Check accounts endpoint:**
```bash
curl http://localhost:5000/api/truelayer/accounts
```

Expected response (after connecting a bank):
```json
{
  "connections": [
    {
      "id": 3,
      "connection_status": "active",
      "accounts": [
        {
          "id": 1,
          "account_id": "acc_123",
          "display_name": "Current Account",
          "account_type": "TRANSACTION_ACCOUNT",
          "currency": "GBP",
          "last_synced_at": "2024-11-25T15:30:00"
        }
      ]
    }
  ]
}
```

**Check cards endpoint:**
```bash
curl http://localhost:5000/api/truelayer/cards
```

Expected response (after connecting a bank with cards):
```json
{
  "connections": [
    {
      "connection_id": 3,
      "cards": [
        {
          "id": 1,
          "card_id": "card_789",
          "card_name": "Chase Sapphire",
          "card_type": "CREDIT_CARD",
          "last_four": "4242",
          "issuer": "Chase",
          "last_synced_at": "2024-11-25T15:00:00"
        }
      ]
    }
  ]
}
```

### 2. Check Browser Console
1. Open Developer Tools (F12 or Ctrl+Shift+I)
2. Go to "Console" tab
3. Look for any error messages
4. Check "Network" tab for failed API requests

### 3. Check Frontend Rendering
Once the backend has data:
1. Go to Settings page
2. Scroll to "Connected Banks - Accounts & Cards" section
3. You should see:
   - Statistics showing "X Accounts" and "Y Cards"
   - Collapsible accordion for each bank
   - Expanded view showing accounts and cards

## Testing the Components (Without Real TrueLayer Data)

If you want to test the UI components before connecting to TrueLayer, you can:

### Option 1: Mock API Response
Modify `BankIntegrationDetails.tsx` to use mock data:

```typescript
// In fetchBankDetails() function, replace axios calls with:
const mockAccountsRes = {
  data: {
    connections: [
      {
        id: 3,
        provider_id: 'truelayer',
        connection_status: 'active',
        last_synced_at: '2024-11-25T15:30:00',
        accounts: [
          {
            id: 1,
            account_id: 'acc_123',
            display_name: 'Current Account',
            account_type: 'TRANSACTION_ACCOUNT',
            currency: 'GBP',
            last_synced_at: '2024-11-25T15:30:00'
          },
          {
            id: 2,
            account_id: 'acc_456',
            display_name: 'Savings Account',
            account_type: 'SAVINGS_ACCOUNT',
            currency: 'GBP',
            last_synced_at: '2024-11-25T10:15:00'
          }
        ]
      }
    ]
  }
};

const mockCardsRes = {
  data: {
    user_id: 1,
    connections: [
      {
        connection_id: 3,
        provider_id: 'truelayer',
        connection_status: 'active',
        cards: [
          {
            id: 1,
            card_id: 'card_789',
            card_name: 'Chase Sapphire Reserve',
            card_type: 'CREDIT_CARD',
            last_four: '4242',
            issuer: 'Chase',
            last_synced_at: '2024-11-25T15:00:00'
          }
        ]
      }
    ]
  }
};

// Then use mockAccountsRes and mockCardsRes instead of axios responses
```

### Option 2: Use Browser DevTools Mock
1. Open Network tab in DevTools
2. Right-click on API requests
3. Use "Edit as cURL" to modify responses
4. Or use browser extensions like "Mock Service Worker"

## Component Verification Checklist

✅ **Backend APIs Working**
- GET /api/truelayer/accounts returns valid JSON
- GET /api/truelayer/cards returns valid JSON
- POST /api/truelayer/fetch-accounts completes successfully
- POST /api/truelayer/fetch-cards completes successfully

✅ **Frontend Components Loading**
- No JavaScript errors in console
- BankIntegrationDetails component mounts
- No errors in Network tab

✅ **Proper Data Structure**
When connected to TrueLayer:
- Each connection has an `id` field
- Accounts have required fields (account_id, display_name, account_type, currency)
- Cards have required fields (card_id, card_name, card_type)

✅ **UI Rendering**
- Statistics badges show correct counts
- Refresh button is clickable
- Accordions expand/collapse
- Status indicators display correctly
- Timestamps format properly

## Next Steps After Connecting Bank

1. **Initial Load**
   - The "Connected Banks - Accounts & Cards" section auto-loads data
   - Shows your connected bank and all accounts/cards

2. **First Refresh**
   - Click "Refresh Accounts & Cards" button
   - This syncs all transaction data from TrueLayer
   - Progress indicator shows during sync

3. **Monitor Sync Status**
   - Green indicator = synced within 24 hours
   - Yellow indicator = synced 1-3 days ago
   - Red indicator = stale (3+ days) or never synced

4. **View in Dashboard**
   - Your accounts and cards data is now available
   - Transactions from accounts/cards will appear in the main dashboard
   - Use account mappings to categorize transactions

## Common Issues & Solutions

### Issue: "Failed to load bank integration details"
**Cause:** Backend API not responding
**Solution:**
1. Check if Flask backend is running: `curl http://localhost:5000/api/health`
2. Check Flask logs for errors
3. Restart Flask if needed

### Issue: "No connected banks found"
**Cause:** No TrueLayer connection yet OR OAuth flow didn't complete
**Solution:**
1. Go to "TrueLayer Bank Integration" section above
2. Click "Connect Bank"
3. Complete the OAuth flow with TrueLayer sandbox
4. Return to Settings page

### Issue: Accounts appear but cards are empty
**Cause:** Connected test bank has no test cards
**Solution:**
1. Try connecting a different test bank in TrueLayer
2. Some sandbox banks only have accounts, no cards
3. Check TrueLayer documentation for banks with card support

### Issue: Timestamps not updating after refresh
**Cause:** Sync completed but data not modified in database
**Solution:**
1. This is normal if no new transactions were found
2. Timestamp updates when transactions are synced
3. If it's been >24h, try refreshing again

### Issue: Loading spinner never stops
**Cause:** API request timing out or hanging
**Solution:**
1. Check browser Network tab for slow requests
2. Restart Flask backend
3. Check internet connection to TrueLayer API
4. Try refresh again

## Performance Tips

- Refresh is fast if no new data to sync
- First refresh may take longer as it syncs all accounts/cards
- Each subsequent refresh only syncs new transactions since last sync
- The UI remains responsive during refresh (async operation)

## Component Architecture for Debugging

```
BankIntegrationDetails.tsx (Container)
  │
  ├─ useEffect: fetchBankDetails()
  │   ├─ GET /api/truelayer/accounts
  │   ├─ GET /api/truelayer/cards
  │   └─ Combine data by connection
  │
  ├─ handleRefreshAccounts()
  │   ├─ POST /api/truelayer/fetch-accounts
  │   ├─ POST /api/truelayer/fetch-cards
  │   └─ Refresh display
  │
  └─ Render:
      └─ BankAccordionItem (per bank)
          ├─ AccountCard (per account)
          └─ CardDisplay (per card)
```

## Getting TrueLayer Sandbox Test Credentials

If you need to set up a fresh TrueLayer connection:

1. Go to TrueLayer Console: https://console.truelayer.com
2. Create a test application
3. Get `client_id` and `client_secret`
4. Use for OAuth flow

Test banks available in sandbox:
- Barclays Test
- HSBC Test
- Lloyds Test
- NatWest Test
- RBS Test
- Santander Test
- And many more...

Each test bank has mock accounts and cards available.
