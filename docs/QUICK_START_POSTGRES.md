# Quick Start: PostgreSQL Migration

This is the fast-track guide for migrating to PostgreSQL. For detailed instructions, see [POSTGRES_MIGRATION.md](./POSTGRES_MIGRATION.md).

---

## Prerequisites
- Docker and Docker Compose installed
- Python virtual environment activated
- Existing SQLite database backed up

---

## Migration Steps (5 minutes)

### 1. Setup Environment
```bash
# Create .env file from example
cp .env.example .env

# Edit .env and set your PostgreSQL password
# Minimum required:
#   POSTGRES_PASSWORD=your_secure_password
```

### 2. Install Dependencies
```bash
cd backend
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Start PostgreSQL
```bash
cd ..
docker-compose up -d

# Wait for initialization (check logs)
docker-compose logs -f postgres
# Look for: "Database initialized successfully!"
# Press Ctrl+C to exit logs
```

### 4. Migrate Data
```bash
cd backend
python migrate_to_postgres.py
```

Expected output:
```
✅ Migration completed successfully!
🎉 All tables verified successfully!
```

### 5. Switch to PostgreSQL
```bash
# Backup SQLite version
mv database.py database_sqlite.py

# Use PostgreSQL version
mv database_postgres.py database.py
```

### 6. Test Application
```bash
# Terminal 1: Backend
cd backend
source venv/bin/activate
python app.py

# Terminal 2: Frontend
cd frontend
npm run dev
```

Visit http://localhost:5173 and verify all features work.

---

## Verification Checklist

- [ ] PostgreSQL container running: `docker-compose ps`
- [ ] Database initialized: `docker-compose logs postgres | grep "initialized"`
- [ ] Migration completed: All tables show "✅ Verification passed"
- [ ] Backend starts without errors
- [ ] Transactions visible in frontend
- [ ] All API endpoints functional

---

## Common Issues

**Container won't start:**
```bash
# Check if port 5432 is in use
netstat -an | grep 5432

# Stop local PostgreSQL if running
sudo systemctl stop postgresql
```

**Migration fails:**
```bash
# Ensure container is running first
docker-compose ps

# Check logs for errors
docker-compose logs postgres
```

**Backend connection error:**
```bash
# Verify .env file exists
cat .env | grep POSTGRES_

# Test connection manually
docker exec -it spending-postgres psql -U spending_user -d spending_db -c "SELECT 1;"
```

---

## Daily Usage

### Start Database
```bash
docker-compose up -d
```

### Stop Database (keeps data)
```bash
docker-compose down
```

### Backup Database
```bash
docker exec spending-postgres pg_dump -U spending_user spending_db > backup_$(date +%Y%m%d).sql
```

### View Data
```bash
docker exec -it spending-postgres psql -U spending_user -d spending_db
```

---

## Rollback to SQLite

If needed:
```bash
cd backend
mv database.py database_postgres.py
mv database_sqlite.py database.py
cp finance.db.backup finance.db
docker-compose down
```

---

## Next Steps

- ✅ Migrated to PostgreSQL
- 🔜 Implement TrueLayer integration (see research plan)
- 🔜 Set up automated backups
- 🔜 Configure production deployment

For detailed TrueLayer integration steps, see the TrueLayer API research documentation.

---

## File Structure

New files created:
```
spending/
├── docker-compose.yml              # PostgreSQL container config
├── .env.example                     # Environment template
├── POSTGRES_MIGRATION.md            # Detailed migration guide
├── QUICK_START_POSTGRES.md          # This file
├── postgres/
│   └── init/
│       ├── 01_schema.sql            # Database schema
│       └── 02_seed_data.sql         # Initial data
└── backend/
    ├── migrate_to_postgres.py       # Migration script
    ├── database_postgres.py         # PostgreSQL database layer
    └── requirements.txt             # Updated with psycopg2
```

---

**Questions?** See [POSTGRES_MIGRATION.md](./POSTGRES_MIGRATION.md) for comprehensive documentation.
