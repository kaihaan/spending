# PostgreSQL Migration Guide

This guide walks you through migrating your Personal Finance Tracker from SQLite to PostgreSQL with Docker, including TrueLayer bank integration support.

---

## Why PostgreSQL?

**Benefits over SQLite:**
- ✅ Better concurrency for multi-user scenarios
- ✅ ACID compliance with proper transaction isolation
- ✅ JSONB support for flexible schema (TrueLayer metadata)
- ✅ Better performance for large datasets
- ✅ Proper data types (NUMERIC for money, TIMESTAMPTZ for timestamps)
- ✅ Production-ready for scaling
- ✅ Support for TrueLayer integration (multiple bank connections)

---

## Prerequisites

Before starting, ensure you have:

- [x] **Docker** and **Docker Compose** installed
- [x] **Python 3.8+** with pip
- [x] Existing SQLite database (`finance.db`) in `backend/` directory
- [x] Basic familiarity with command line

---

## Step-by-Step Migration

### Step 1: Create Environment Configuration

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` and configure your credentials:
```bash
# PostgreSQL Configuration
POSTGRES_USER=spending_user
POSTGRES_PASSWORD=your_secure_password_here
POSTGRES_DB=spending_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# TrueLayer API (optional - for bank integration)
TRUELAYER_CLIENT_ID=your_client_id
TRUELAYER_CLIENT_SECRET=your_client_secret
TRUELAYER_REDIRECT_URI=http://localhost:5000/api/truelayer/callback
TRUELAYER_ENVIRONMENT=sandbox

# Flask Configuration
FLASK_ENV=development
FLASK_SECRET_KEY=your_flask_secret_key

# Encryption Key (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
ENCRYPTION_KEY=your_fernet_key_here
```

3. Generate encryption key for OAuth tokens:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy the output into `ENCRYPTION_KEY` in `.env`.

---

### Step 2: Install Python Dependencies

```bash
cd backend
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

This will install:
- `psycopg2-binary` - PostgreSQL adapter
- `python-dotenv` - Environment variable management
- `cryptography` - Encryption for OAuth tokens
- `requests` - HTTP client for TrueLayer API

---

### Step 3: Start PostgreSQL with Docker

1. Start the PostgreSQL container:
```bash
cd ..  # Back to project root
docker-compose up -d
```

2. Verify the container is running:
```bash
docker-compose ps
```

You should see:
```
NAME                  STATUS              PORTS
spending-postgres     Up X seconds        0.0.0.0:5432->5432/tcp
```

3. Check logs to ensure initialization completed:
```bash
docker-compose logs postgres
```

Look for:
```
PostgreSQL init process complete; ready for start up.
Database initialized successfully!
```

---

### Step 4: Verify Database Schema

Connect to the database and verify tables were created:

```bash
docker exec -it spending-postgres psql -U spending_user -d spending_db
```

Inside PostgreSQL shell:
```sql
-- List all tables
\dt

-- View transactions table structure
\d transactions

-- Check seed data
SELECT * FROM categories;

-- Exit
\q
```

You should see tables:
- Existing: `transactions`, `categories`, `category_keywords`, `account_mappings`, `amazon_orders`, etc.
- New: `users`, `bank_connections`, `truelayer_accounts`, `truelayer_transactions`, `webhook_events`, etc.

---

### Step 5: Migrate Data from SQLite

**IMPORTANT:** Backup your SQLite database first:
```bash
cd backend
cp finance.db finance.db.backup
```

Run the migration script:
```bash
python migrate_to_postgres.py
```

You should see output like:
```
======================================================================
SQLite to PostgreSQL Migration
======================================================================

📡 Connecting to databases...
  ✅ Connected to SQLite
  ✅ Connected to PostgreSQL

📦 Starting data migration...

🔄 Migrating categories...
  ✅ Migrated 9 rows to categories

🔄 Migrating transactions...
  ✅ Migrated 1,234 rows to transactions

...

✅ Migration completed successfully! Total rows migrated: X,XXX

🔍 Verifying migration...
  ✅ Verification passed: transactions (1,234 rows)
  ✅ Verification passed: categories (9 rows)
  ...

🎉 All tables verified successfully!
======================================================================
```

---

### Step 6: Update Application to Use PostgreSQL

**Option A: Replace existing database.py (recommended for clean migration)**

```bash
cd backend
mv database.py database_sqlite.py  # Backup SQLite version
mv database_postgres.py database.py
```

**Option B: Use environment variable to switch (for gradual migration)**

You can modify `app.py` to import conditionally based on an environment variable.

---

### Step 7: Test the Application

1. Start the backend:
```bash
cd backend
source venv/bin/activate
python app.py
```

2. In another terminal, start the frontend:
```bash
cd frontend
npm run dev
```

3. Open http://localhost:5173 and verify:
- [ ] Transactions are visible
- [ ] Categories display correctly
- [ ] All API endpoints work
- [ ] No errors in backend logs

---

### Step 8: Verify Data Integrity

Run some verification queries:

```bash
docker exec -it spending-postgres psql -U spending_user -d spending_db
```

```sql
-- Check transaction count
SELECT COUNT(*) FROM transactions;

-- Check date range
SELECT MIN(date), MAX(date) FROM transactions;

-- Check categories distribution
SELECT category, COUNT(*) FROM transactions GROUP BY category ORDER BY COUNT(*) DESC;

-- Verify foreign key relationships
SELECT COUNT(*) FROM amazon_transaction_matches atm
JOIN transactions t ON atm.transaction_id = t.id;
```

---

## Docker Management Commands

### Start/Stop PostgreSQL

```bash
# Start PostgreSQL
docker-compose up -d

# Stop PostgreSQL (keeps data)
docker-compose down

# Stop and remove data (DESTRUCTIVE!)
docker-compose down -v
```

### View Logs

```bash
# Follow logs
docker-compose logs -f postgres

# View last 50 lines
docker-compose logs --tail=50 postgres
```

### Database Backup

```bash
# Create backup
docker exec spending-postgres pg_dump -U spending_user spending_db > backup_$(date +%Y%m%d).sql

# Restore from backup
docker exec -i spending-postgres psql -U spending_user spending_db < backup_20250101.sql
```

### Access PostgreSQL Shell

```bash
# Interactive shell
docker exec -it spending-postgres psql -U spending_user -d spending_db

# Run single query
docker exec -it spending-postgres psql -U spending_user -d spending_db -c "SELECT COUNT(*) FROM transactions;"
```

---

## TrueLayer Integration Setup (Optional)

After migrating to PostgreSQL, you can enable TrueLayer bank synchronization:

### 1. Get TrueLayer Credentials

1. Sign up at [TrueLayer Console](https://console.truelayer.com)
2. Create a new application
3. Enable "Data API" product
4. Note your `client_id` and `client_secret`
5. Add redirect URI: `http://localhost:5000/api/truelayer/callback`

### 2. Configure Environment

Update `.env`:
```bash
TRUELAYER_CLIENT_ID=your_actual_client_id
TRUELAYER_CLIENT_SECRET=your_actual_client_secret
TRUELAYER_REDIRECT_URI=http://localhost:5000/api/truelayer/callback
TRUELAYER_ENVIRONMENT=sandbox  # Use 'production' for live banks
```

### 3. Database Schema Already Supports TrueLayer

The migration created these tables automatically:
- `bank_connections` - OAuth connections
- `truelayer_accounts` - Bank account details
- `truelayer_transactions` - Synced transactions
- `truelayer_balances` - Balance history
- `webhook_events` - Asynchronous event processing

### 4. Implementation Tasks

You'll need to implement:
- OAuth authorization flow (see TrueLayer research plan)
- Token refresh mechanism
- Transaction sync service
- Webhook handler (optional)

Refer to the TrueLayer API research documentation for detailed implementation steps.

---

## Troubleshooting

### Container Won't Start

```bash
# Check if port 5432 is already in use
netstat -an | grep 5432

# If PostgreSQL is installed locally, stop it
sudo systemctl stop postgresql  # Linux
brew services stop postgresql   # macOS
```

### Migration Script Errors

**Error: "Connection refused"**
- Ensure Docker container is running: `docker-compose ps`
- Wait a few seconds for PostgreSQL to initialize

**Error: "Duplicate key value violates unique constraint"**
- You might be running migration twice
- Drop and recreate database:
```bash
docker-compose down -v
docker-compose up -d
```

**Error: "NUMERIC out of range"**
- Check for very large transaction amounts in SQLite
- Adjust NUMERIC precision in schema if needed

### Application Connection Errors

**Error: "psycopg2.OperationalError: could not connect"**

Check:
1. `.env` file exists and has correct credentials
2. `POSTGRES_HOST=localhost` (not `127.0.0.1`)
3. Container is running: `docker-compose ps`
4. Port 5432 is accessible: `nc -zv localhost 5432`

---

## Rollback to SQLite (If Needed)

If you encounter issues, you can roll back:

```bash
cd backend

# Restore original database.py
mv database.py database_postgres.py
mv database_sqlite.py database.py

# Restore SQLite database from backup
cp finance.db.backup finance.db

# Stop PostgreSQL
cd ..
docker-compose down
```

---

## Performance Tuning

For large datasets (100k+ transactions), consider:

### Indexes (already created in schema)
- Date-based queries: `idx_transactions_date`
- Merchant filtering: `idx_transactions_merchant`
- Category filtering: `idx_transactions_category`

### Connection Pooling
The `database_postgres.py` already uses connection pooling (1-10 connections).

For high traffic, adjust pool size:
```python
connection_pool = psycopg2.pool.SimpleConnectionPool(
    5,   # Minimum connections
    20,  # Maximum connections
    **DB_CONFIG
)
```

### Query Optimization

Use EXPLAIN ANALYZE to profile slow queries:
```sql
EXPLAIN ANALYZE
SELECT * FROM transactions
WHERE date >= '2024-01-01' AND category = 'Groceries';
```

---

## Next Steps

After successful migration:

- [ ] Update `README.md` with PostgreSQL instructions
- [ ] Implement TrueLayer OAuth flow
- [ ] Set up automated database backups
- [ ] Configure monitoring (optional)
- [ ] Plan for production deployment

---

## Additional Resources

- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Docker Compose Reference](https://docs.docker.com/compose/)
- [psycopg2 Documentation](https://www.psycopg.org/docs/)
- [TrueLayer API Docs](https://docs.truelayer.com)
- [TrueLayer Integration Plan](./TRUELAYER_INTEGRATION.md) (from earlier research)

---

## Support

If you encounter issues not covered in this guide, check:
1. Docker container logs: `docker-compose logs postgres`
2. Backend application logs
3. PostgreSQL query logs (if enabled)

For TrueLayer-specific questions, refer to the comprehensive research plan generated earlier.
