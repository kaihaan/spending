Gmail Receipt Integration Plan (Revised)

 Overview

 Integrate Gmail receipts as a transaction enrichment source, following existing OAuth (TrueLayer) and matching (Amazon/Apple) patterns.

 User Requirements:
 - Parse all merchant receipts (broadest coverage)
 - Use Schema.org + LLM fallback parsing approach
 - Per-user OAuth (each user connects their own Gmail)

 ---
 Security & Privacy

 OAuth Scope Transparency

 - Use https://www.googleapis.com/auth/gmail.readonly (minimum required)
 - UI must clearly explain: "This grants read-only access to your entire inbox. We only process emails that look like receipts."
 - No mail.google.com (full access) ever

 Token Encryption

 - Use existing Fernet encryption (same as TrueLayer)
 - Add encryption_version column for future key rotation
 - Store key ID alongside ciphertext

 Data Retention Policy

 - Auto-delete unmatched receipts after 90 days
 - Full data deletion on disconnect (not just token revoke)
 - Add deleted_at for soft deletes
 - GDPR-compliant purpose limitation

 PII Protection

 - Never log sender_email, line_items, or full email content
 - Log only: message_id, parse_method, confidence, error codes
 - Mask PII in error messages

 Multi-User Isolation

 - All database queries MUST filter by `user_id` - no cross-user data leakage
 - Consider row-level security or enforce isolation via ORM/repository layer
 - Rate limits apply per-user, not globally
 - Tokens stored per user_id + email combination (unique constraint exists)

 ---
 Database Schema (Revised)

 gmail_connections - OAuth Token Storage

 CREATE TABLE IF NOT EXISTS gmail_connections (
     id SERIAL PRIMARY KEY,
     user_id INTEGER NOT NULL DEFAULT 1,
     email_address VARCHAR(255) NOT NULL,
     access_token TEXT NOT NULL,              -- Encrypted with Fernet
     refresh_token TEXT NOT NULL,             -- Encrypted with Fernet
     token_expires_at TIMESTAMP WITH TIME ZONE,
     encryption_version INTEGER DEFAULT 1,    -- For key rotation
     scopes TEXT,
     connection_status VARCHAR(20) DEFAULT 'active',  -- active, expired, revoked
     history_id VARCHAR(50),                  -- Gmail historyId for incremental sync
     last_synced_at TIMESTAMP WITH TIME ZONE,
     sync_from_date DATE,
     error_count INTEGER DEFAULT 0,           -- Track consecutive errors
     last_error TEXT,                         -- Last error message
     created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
     updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
     CONSTRAINT gmail_connections_user_email_unique UNIQUE (user_id, email_address)
 );

 CREATE INDEX idx_gmail_connections_user ON gmail_connections(user_id);
 CREATE INDEX idx_gmail_connections_status ON gmail_connections(connection_status);

 gmail_receipts - Parsed Receipt Data

 CREATE TABLE IF NOT EXISTS gmail_receipts (
     id SERIAL PRIMARY KEY,
     connection_id INTEGER NOT NULL REFERENCES gmail_connections(id) ON DELETE CASCADE,
     message_id VARCHAR(255) UNIQUE NOT NULL,    -- Increased from 100
     thread_id VARCHAR(255),
     sender_email VARCHAR(255) NOT NULL,
     sender_name VARCHAR(255),
     subject TEXT,
     received_at TIMESTAMP WITH TIME ZONE NOT NULL,

     -- Parsed receipt data
     merchant_name VARCHAR(255),
     merchant_name_normalized VARCHAR(255),      -- Lowercase, stripped
     merchant_domain VARCHAR(255),
     order_id VARCHAR(255),
     total_amount NUMERIC(12,2),
     currency_code VARCHAR(3) DEFAULT 'GBP',     -- ISO 4217
     receipt_date DATE,

     -- Item details
     line_items JSONB,                           -- [{name, quantity, unit_price, total}]

     -- Deduplication hash
     receipt_hash VARCHAR(64),                   -- SHA256(merchant+amount+date+order_id)

     -- Parsing metadata
     parse_method VARCHAR(20) NOT NULL,          -- schema_org, pattern, llm
     parse_confidence INTEGER NOT NULL,          -- 0-100
     raw_schema_data JSONB,
     llm_cost_cents INTEGER,                     -- Track LLM spend

     -- Status tracking
     parsing_status VARCHAR(20) DEFAULT 'pending',  -- pending, parsed, failed, matched, unparseable
     parsing_error TEXT,
     retry_count INTEGER DEFAULT 0,
     deleted_at TIMESTAMP WITH TIME ZONE,        -- Soft delete for GDPR

     created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
     updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
 );

 -- Optimized indices for common queries
 CREATE INDEX idx_gmail_receipts_connection ON gmail_receipts(connection_id);
 CREATE INDEX idx_gmail_receipts_connection_date ON gmail_receipts(connection_id, receipt_date);
 CREATE INDEX idx_gmail_receipts_amount_date ON gmail_receipts(total_amount, receipt_date);
 CREATE INDEX idx_gmail_receipts_pending ON gmail_receipts(parsing_status) WHERE parsing_status = 'pending';
 CREATE INDEX idx_gmail_receipts_merchant ON gmail_receipts(merchant_name_normalized);
 CREATE INDEX idx_gmail_receipts_hash ON gmail_receipts(receipt_hash);
 CREATE INDEX idx_gmail_receipts_not_deleted ON gmail_receipts(id) WHERE deleted_at IS NULL;

 gmail_transaction_matches - Many-to-Many Match Links

 CREATE TABLE IF NOT EXISTS gmail_transaction_matches (
     id SERIAL PRIMARY KEY,
     truelayer_transaction_id INTEGER NOT NULL REFERENCES truelayer_transactions(id) ON DELETE CASCADE,
     gmail_receipt_id INTEGER NOT NULL REFERENCES gmail_receipts(id) ON DELETE CASCADE,
     match_confidence INTEGER NOT NULL,          -- 0-100
     match_type VARCHAR(20) DEFAULT 'standard',  -- standard, split_payment, bundled_order
     match_method VARCHAR(30),                   -- amount_date, merchant_amount, fuzzy_merchant
     currency_converted BOOLEAN DEFAULT FALSE,
     conversion_rate NUMERIC(10,6),
     user_confirmed BOOLEAN DEFAULT FALSE,       -- Manual confirmation for low-confidence
     matched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

     CONSTRAINT gmail_match_unique UNIQUE (truelayer_transaction_id, gmail_receipt_id)
 );

 CREATE INDEX idx_gmail_matches_transaction ON gmail_transaction_matches(truelayer_transaction_id);
 CREATE INDEX idx_gmail_matches_receipt ON gmail_transaction_matches(gmail_receipt_id);
 CREATE INDEX idx_gmail_matches_unconfirmed ON gmail_transaction_matches(match_confidence)
     WHERE match_confidence < 80 AND user_confirmed = FALSE;

 gmail_merchant_aliases - Merchant Name Normalization

 CREATE TABLE IF NOT EXISTS gmail_merchant_aliases (
     id SERIAL PRIMARY KEY,
     bank_name VARCHAR(255) NOT NULL,           -- Name from bank statement
     receipt_name VARCHAR(255) NOT NULL,        -- Name from receipt
     normalized_name VARCHAR(255) NOT NULL,     -- Canonical form
     is_active BOOLEAN DEFAULT TRUE,
     usage_count INTEGER DEFAULT 0,
     created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
 );

 CREATE INDEX idx_merchant_aliases_bank ON gmail_merchant_aliases(LOWER(bank_name));
 CREATE INDEX idx_merchant_aliases_receipt ON gmail_merchant_aliases(LOWER(receipt_name));

 -- Seed common aliases
 INSERT INTO gmail_merchant_aliases (bank_name, receipt_name, normalized_name) VALUES
 ('AMAZON.CO.UK', 'Amazon', 'amazon'),
 ('AMAZON EU', 'Amazon', 'amazon'),
 ('AMZN MKTP', 'Amazon Marketplace', 'amazon'),
 ('PAYPAL *MERCHANT', 'PayPal', 'paypal'),
 ('UBER* TRIP', 'Uber', 'uber'),
 ('UBER EATS', 'Uber Eats', 'uber_eats'),
 ('DELIVEROO', 'Deliveroo', 'deliveroo'),
 ('JET2.COM', 'Jet2', 'jet2'),
 ('RYANAIR', 'Ryanair', 'ryanair');

 gmail_sender_patterns - Known Receipt Patterns

 CREATE TABLE IF NOT EXISTS gmail_sender_patterns (
     id SERIAL PRIMARY KEY,
     sender_domain VARCHAR(255) NOT NULL,
     sender_pattern VARCHAR(255),
     merchant_name VARCHAR(255) NOT NULL,
     normalized_name VARCHAR(255) NOT NULL,
     parse_type VARCHAR(20) NOT NULL,           -- schema_org, pattern, llm
     pattern_config JSONB,
     date_tolerance_days INTEGER DEFAULT 7,     -- Sender-specific tolerance
     is_active BOOLEAN DEFAULT TRUE,
     usage_count INTEGER DEFAULT 0,
     last_used_at TIMESTAMP WITH TIME ZONE,
     created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
 );

 -- Seed with common senders
 INSERT INTO gmail_sender_patterns (sender_domain, merchant_name, normalized_name, parse_type, date_tolerance_days, pattern_config) VALUES
 -- E-commerce
 ('amazon.co.uk', 'Amazon', 'amazon', 'schema_org', 14, '{"order_id_pattern": "Order #([0-9-]+)"}'),
 ('amazon.com', 'Amazon', 'amazon', 'schema_org', 14, '{}'),
 ('ebay.co.uk', 'eBay', 'ebay', 'pattern', 7, '{}'),
 ('apple.com', 'Apple', 'apple', 'schema_org', 5, '{}'),
 -- Payment providers
 ('paypal.com', 'PayPal', 'paypal', 'pattern', 3, '{"amount_pattern": "Total\\s*[£$]([\\d,.]+)"}'),
 -- Food delivery
 ('uber.com', 'Uber', 'uber', 'schema_org', 3, '{}'),
 ('deliveroo.com', 'Deliveroo', 'deliveroo', 'pattern', 3, '{}'),
 ('just-eat.co.uk', 'Just Eat', 'just_eat', 'pattern', 3, '{}'),
 -- Travel
 ('trainline.com', 'Trainline', 'trainline', 'schema_org', 14, '{}'),
 ('booking.com', 'Booking.com', 'booking', 'schema_org', 30, '{}'),
 ('hotels.com', 'Hotels.com', 'hotels', 'pattern', 30, '{}'),
 ('jet2.com', 'Jet2', 'jet2', 'pattern', 30, '{}'),
 ('ryanair.com', 'Ryanair', 'ryanair', 'pattern', 30, '{}'),
 ('easyjet.com', 'EasyJet', 'easyjet', 'pattern', 30, '{}'),
 -- Subscriptions
 ('netflix.com', 'Netflix', 'netflix', 'pattern', 3, '{}'),
 ('spotify.com', 'Spotify', 'spotify', 'pattern', 3, '{}'),
 ('adobe.com', 'Adobe', 'adobe', 'pattern', 3, '{}'),
 ('microsoft.com', 'Microsoft', 'microsoft', 'schema_org', 3, '{}'),
 -- UK Utilities
 ('britishgas.co.uk', 'British Gas', 'british_gas', 'pattern', 7, '{}'),
 ('edfenergy.com', 'EDF Energy', 'edf', 'pattern', 7, '{}'),
 ('thameswater.co.uk', 'Thames Water', 'thames_water', 'pattern', 7, '{}'),
 ('octopus.energy', 'Octopus Energy', 'octopus', 'pattern', 7, '{}'),
 -- UK Supermarkets
 ('tesco.com', 'Tesco', 'tesco', 'pattern', 3, '{}'),
 ('sainsburys.co.uk', 'Sainsburys', 'sainsburys', 'pattern', 3, '{}'),
 ('ocado.com', 'Ocado', 'ocado', 'schema_org', 3, '{}'),
 ('asda.com', 'Asda', 'asda', 'pattern', 3, '{}');

 ---
 Backend Modules

 | File                         | Purpose                                                           |
 |------------------------------|-------------------------------------------------------------------|
 | backend/mcp/gmail_auth.py    | OAuth2 flow, token encryption, refresh with error tracking        |
 | backend/mcp/gmail_client.py  | Gmail API wrapper, incremental sync with historyId, rate limiting |
 | backend/mcp/gmail_sync.py    | Receipt discovery, deduplication via receipt_hash                 |
 | backend/mcp/gmail_parser.py  | Schema.org + patterns + LLM, currency extraction                  |
 | backend/mcp/gmail_matcher.py | Fuzzy matching with merchant normalization, multi-currency        |
 | backend/tasks/gmail_tasks.py | Async Celery tasks with job status                                |

 ---
 Parsing Implementation Details

 Schema.org JSON-LD Extraction

 Many merchants (Amazon, Google, Uber) embed structured receipt data in emails:

 ```python
 from bs4 import BeautifulSoup
 import json

 def extract_schema_org(html_body: str) -> dict | None:
     """Extract Schema.org JSON-LD receipt data from email HTML."""
     soup = BeautifulSoup(html_body, 'lxml')
     scripts = soup.find_all('script', type='application/ld+json')

     for script in scripts:
         try:
             data = json.loads(script.string)
             # Handle both single object and array of objects
             items = data if isinstance(data, list) else [data]

             for item in items:
                 if item.get('@type') in ['Order', 'Invoice', 'Receipt', 'ConfirmAction']:
                     return parse_schema_org_order(item)
         except json.JSONDecodeError:
             continue

     return None

 def parse_schema_org_order(data: dict) -> dict:
     """Parse Schema.org Order/Invoice into our receipt format."""
     price_spec = data.get('acceptedOffer', {}).get('priceSpecification', {})

     return {
         'merchant_name': data.get('seller', {}).get('name'),
         'order_id': data.get('orderNumber'),
         'total_amount': price_spec.get('price') or data.get('totalPrice'),
         'currency': price_spec.get('priceCurrency', 'GBP'),
         'receipt_date': data.get('orderDate'),
         'line_items': [
             {
                 'name': item.get('name'),
                 'quantity': item.get('orderQuantity', 1),
                 'price': item.get('price')
             }
             for item in data.get('orderedItem', [])
         ],
         'parse_method': 'schema_org',
         'parse_confidence': 95
     }
 ```

 LLM Fallback Prompt Template

 When Schema.org and regex patterns fail, use LLM extraction:

 ```python
 LLM_RECEIPT_PROMPT = """
 Extract receipt details from this email. Return JSON only, no explanation.

 Required format:
 {
   "is_receipt": true,
   "merchant_name": "string - the company name",
   "total_amount": number - final total including tax/delivery,
   "currency": "GBP|USD|EUR",
   "order_id": "string or null",
   "receipt_date": "YYYY-MM-DD",
   "line_items": [
     {"name": "item description", "quantity": 1, "price": 9.99}
   ]
 }

 If this is NOT a receipt/order confirmation, return:
 {"is_receipt": false}

 Email content:
 ---
 Subject: {subject}
 From: {sender}
 Date: {date}

 {body_text}
 ---
 """
 ```

 ---
 Matching Algorithm (Improved)

 Tolerance Settings

 - Amount: ±2% OR ±£0.50, whichever is greater
 - Date: ±7 days default, configurable per sender (pre-orders get ±14 days)
 - Currency: Convert to transaction currency before comparison

 Timezone Handling

 - Store all timestamps as `TIMESTAMP WITH TIME ZONE` (UTC internally)
 - Parse email Date header with timezone awareness using `email.utils.parsedate_to_datetime()`
 - Convert to UTC for storage, user's local timezone for display/matching
 - Handle UK BST/GMT transitions (last Sunday March → last Sunday October)
 - Match date comparisons should use date-only (ignore time component)

 Merchant Normalization Pipeline

 Receipt: "Amazon.co.uk Order"
     ↓
 1. Lowercase: "amazon.co.uk order"
     ↓
 2. Remove common suffixes: "amazon.co.uk"
     ↓
 3. Check gmail_merchant_aliases: normalized_name = "amazon"
     ↓
 4. Compare with bank transaction merchant (also normalized)

 Bank: "AMZN MKTP UK"
     ↓
 1. Lowercase: "amzn mktp uk"
     ↓
 2. Check gmail_merchant_aliases: normalized_name = "amazon"
     ↓
 Match if normalized names equal

 Confidence Scoring

 | Match Type                                  | Base Score              |
 |---------------------------------------------|-------------------------|
 | Exact amount + same day + merchant match    | 100                     |
 | Exact amount + ±3 days + merchant match     | 90                      |
 | Amount within 2% + ±7 days + merchant match | 80                      |
 | Amount within 2% + ±7 days + no merchant    | 70                      |
 | Amount match only                           | 60 (needs confirmation) |

 Threshold: 70+ auto-match, 60-69 requires user confirmation

 ---
 Incremental Sync (Gmail historyId)

 Gmail Search Query (Comprehensive)

 ```python
 RECEIPT_QUERY = """
 from:(noreply OR no-reply OR orders OR receipts OR billing OR invoice OR confirmation)
 OR subject:(receipt OR "order confirmation" OR invoice OR "payment received"
    OR "your order" OR "purchase" OR "shipping confirmation" OR "delivery"
    OR "transaction" OR "statement" OR "booking confirmation")
 """
 ```

 Initial Sync with Pagination

 ```python
 def sync_all_receipts(service, connection_id):
     """Handle large mailboxes with pagination."""
     page_token = None
     total_processed = 0

     while True:
         response = service.users().messages().list(
             userId='me',
             q=RECEIPT_QUERY,
             maxResults=100,  # Smaller batches for reliability
             pageToken=page_token
         ).execute()

         messages = response.get('messages', [])
         process_messages(messages)
         total_processed += len(messages)

         # Update progress for UI
         update_job_progress(connection_id, total_processed)

         page_token = response.get('nextPageToken')
         if not page_token:
             break

     # Store latest historyId for incremental sync
     store_history_id(connection_id, response.get('historyId'))
     return total_processed
 ```

 Incremental Sync

 ```python
 # Use historyId for efficient delta sync
 response = service.users().history().list(
     userId='me',
     startHistoryId=stored_history_id,
     historyTypes=['messageAdded']
 ).execute()
 # Process only new messages, update historyId
 ```

 ---
 Rate Limiting

 # Per-user rate limiting
 GMAIL_RATE_LIMIT = 250 / 5  # 50 messages/second max
 rate_limiter = RateLimiter(50, per_second=True)

 # Exponential backoff on 429
 def fetch_with_backoff(request, max_retries=5):
     for attempt in range(max_retries):
         try:
             return request.execute()
         except HttpError as e:
             if e.resp.status == 429:
                 wait = (2 ** attempt) + random.uniform(0, 1)
                 time.sleep(wait)
             else:
                 raise

 ---
 Duplicate Receipt Detection

 def compute_receipt_hash(receipt):
     """Deduplicate order confirm + shipping confirm + delivery confirm."""
     key = f"{receipt['merchant_normalized']}|{receipt['amount']}|{receipt['date']}|{receipt['order_id'] or ''}"
     return hashlib.sha256(key.encode()).hexdigest()

 # On insert: check for existing receipt_hash
 # If found: keep highest confidence version

 ---
 Error Handling

 | Failure                   | Detection       | Recovery                                                                  |
 |---------------------------|-----------------|---------------------------------------------------------------------------|
 | OAuth token refresh fails | 401 response    | Set status='expired', increment error_count, alert user                   |
 | Gmail API 429             | HttpError 429   | Exponential backoff (2^n seconds), resume from last message_id            |
 | LLM timeout               | Request timeout | Add to retry queue, max 3 attempts, then mark 'unparseable'               |
 | No matches found          | Empty result    | UI shows "No bank transactions in date range. Try widening search dates." |
 | Parse error               | Exception       | Log error code (not content), mark 'failed', continue batch               |

 ---
 API Endpoints

 OAuth

 | Method | Endpoint              | Description                        |
 |--------|-----------------------|------------------------------------|
 | GET    | /api/gmail/authorize  | Initiate OAuth flow                |
 | GET    | /api/gmail/callback   | Handle OAuth callback              |
 | GET    | /api/gmail/connection | Get connection status + error info |
 | POST   | /api/gmail/disconnect | Disconnect + delete all data       |

 Sync (Async with Job IDs)

 | Method | Endpoint                        | Description                                    |
 |--------|---------------------------------|------------------------------------------------|
 | POST   | /api/gmail/sync                 | Start sync, returns {job_id, status: "queued"} |
 | GET    | /api/gmail/sync/status/<job_id> | Poll job status + progress                     |
 | DELETE | /api/gmail/sync/<job_id>        | Cancel running sync                            |

 Receipts (with Pagination)

 | Method | Endpoint                              | Description               |
 |--------|---------------------------------------|---------------------------|
 | GET    | /api/gmail/receipts?limit=50&offset=0 | List receipts (paginated) |
 | GET    | /api/gmail/receipts/<id>              | Single receipt details    |
 | DELETE | /api/gmail/receipts/<id>              | Soft delete receipt       |

 Matching

 | Method | Endpoint                            | Description                        |
 |--------|-------------------------------------|------------------------------------|
 | POST   | /api/gmail/match                    | Start matching job (async)         |
 | GET    | /api/gmail/matches                  | List all matches                   |
 | GET    | /api/gmail/receipts/<id>/candidates | Preview match candidates           |
 | POST   | /api/gmail/matches/<id>/confirm     | User confirms low-confidence match |
 | DELETE | /api/gmail/matches/<id>             | Remove a match                     |

 Statistics

 | Method | Endpoint              | Description                       |
 |--------|-----------------------|-----------------------------------|
 | GET    | /api/gmail/statistics | Counts, date range, parse methods |
 | GET    | /api/gmail/cost       | LLM spend tracking                |

 ---
 Testing Strategy

 Unit Tests

 - Parser tests with sample emails (redacted/anonymised fixtures)
 - Mock Gmail API responses for client tests
 - Merchant normalisation edge cases
 - Confidence scoring accuracy

 Integration Tests

 - Full OAuth flow (mock Google OAuth server)
 - End-to-end sync with test mailbox
 - Matching pipeline with known transaction pairs

 Test Fixtures

 - 10+ sample receipt emails per merchant type
 - Schema.org compliant and non-compliant examples
 - Multi-currency receipts (GBP, EUR, USD)
 - Edge cases: refunds, partial payments, split orders

 Success Metrics

 | Metric | Target |
 |--------|--------|
 | Parse success rate | ≥ 85% |
 | Schema.org extraction accuracy | ≥ 95% |
 | LLM extraction accuracy | ≥ 80% |
 | Match accuracy (known merchants) | ≥ 95% |
 | Match accuracy (unknown merchants) | ≥ 70% |

 ---
 Monitoring & Alerting

 | Metric | Threshold | Alert Level |
 |--------|-----------|-------------|
 | Parse success rate | < 80% | Warning |
 | Match rate | < 60% | Info |
 | Sync errors per day | > 10 | Critical |
 | LLM cost per day | > £10 | Warning |
 | OAuth token refresh failures | > 3/user | Critical |
 | API 429 rate limit hits | > 50/hour | Warning |

 Logging Requirements

 - All sync operations logged with job_id, user_id (not email content)
 - Parse failures logged with error code and message_id only
 - Match confidence scores logged for ML analysis
 - LLM costs tracked per request

 ---
 Implementation Phases (Revised)

 | Phase           | Tasks                                                                                            | Key Deliverables                   |
 |-----------------|--------------------------------------------------------------------------------------------------|------------------------------------|
 | 1. Foundation   | DB migration, OAuth flow, token encryption, error handling framework, connection status tracking | Users can connect/disconnect Gmail |
 | 2. Discovery    | Gmail client, incremental sync with historyId, rate limiting, exponential backoff                | Receipts discovered efficiently    |
 | 3. Parsing      | Schema.org + patterns, currency extraction, receipt_hash dedup                                   | Receipts parsed with confidence    |
 | 4. Matching     | Fuzzy matching, merchant normalization, multi-currency, wider tolerances                         | Transactions matched accurately    |
 | 5. Frontend     | Settings UI, async job polling, receipt table, match confirmation UI                             | Full user workflow                 |
 | 6. LLM Fallback | LLM extraction, cost tracking, result caching                                                    | Unstructured email support         |
 | 7. Polish       | Background tasks, monitoring/alerting, data retention jobs, scheduled sync                       | Production-ready                   |

 ---
 Critical Files to Modify

 | File                                                | Action                                  |
 |-----------------------------------------------------|-----------------------------------------|
 | postgres/init/11_gmail_integration.sql              | Create - All tables + indices + seeds   |
 | backend/mcp/gmail_auth.py                           | Create - OAuth with error tracking      |
 | backend/mcp/gmail_client.py                         | Create - API wrapper with rate limiting |
 | backend/mcp/gmail_sync.py                           | Create - Incremental sync               |
 | backend/mcp/gmail_parser.py                         | Create - Multi-tier parsing             |
 | backend/mcp/gmail_matcher.py                        | Create - Fuzzy matching + normalization |
 | backend/tasks/gmail_tasks.py                        | Create - Async Celery tasks             |
 | backend/database_postgres.py                        | Modify - Add Gmail database functions   |
 | backend/app.py                                      | Modify - Add Gmail endpoints            |
 | frontend/src/components/Settings/DataSourcesTab.tsx | Modify - Add Gmail vendor row           |

 ---
 Environment Variables

 # Gmail OAuth (Google Cloud Console)
 GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
 GOOGLE_CLIENT_SECRET=your_client_secret
 GOOGLE_REDIRECT_URI=http://localhost:5000/api/gmail/callback

 # Optional: LLM cost tracking
 GMAIL_LLM_MAX_COST_CENTS_PER_DAY=1000

 ---
 Dependencies

 Add to backend/requirements.txt:
 google-auth>=2.0.0
 google-auth-oauthlib>=1.0.0
 google-api-python-client>=2.0.0
 beautifulsoup4>=4.12.0
 lxml>=5.0.0

 ---
 Summary: Key Improvements from Review

 1. Currency handling - Added currency_code column and conversion tracking
 2. Incremental sync - Using Gmail historyId for efficiency
 3. Wider tolerances - ±2%/£0.50 amount, ±7 days date (configurable)
 4. Merchant normalization - Alias table + normalization pipeline
 5. Async sync - Job-based with status polling
 6. Many-to-many matches - Supports split payments and bundled orders
 7. Error tracking - error_count, last_error, retry logic
 8. Data retention - Soft deletes, 90-day auto-cleanup
 9. Deduplication - receipt_hash for order confirm + shipping + delivery
 10. Rate limiting - Exponential backoff on 429s
