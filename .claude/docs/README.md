# Claude Documentation Index

**Documentation Location:** `.claude/docs/` (as per CLAUDE.md specifications)

This documentation is organized into the following categories:

---

## 📁 Folder Structure

### 🏗️ **architecture/**
System design, architecture diagrams, and integration patterns.

- **TRUELAYER_INTEGRATION.md** - TrueLayer OAuth integration, API design, and implementation guide

### 🗄️ **database/**
Database schemas, migrations, and data model documentation.

- **DATABASE_SCHEMA.md** ⭐ - **START HERE** - Complete database schema reference for all 21 tables
  - Column definitions, data types, constraints
  - Foreign key relationships
  - Best practices for working with the database
  - Migration procedures

- **SCHEMA_ENFORCEMENT.md** - Rules for ensuring code adheres to schema
  - Pre-commit checklist
  - Common schema violations and solutions
  - Code review guidelines
  - Migration workflow

- **SCHEMA_CRITICAL_FIXES.md** - Documentation of 6 critical bugs fixed in TrueLayer sync
  - Running balance dict vs scalar
  - JSON serialization issues
  - Column name typos
  - Timezone-aware datetime handling
  - Missing imports
  - Token expiry checks
  - Testing strategies to prevent regressions

- **POSTGRES_MIGRATION.md** - SQLite to PostgreSQL migration guide
  - Migration procedures
  - Verification steps
  - Troubleshooting

### 🧑‍💻 **development/**
Local development environment setup and guides.

#### development/setup/
- **QUICK_START_POSTGRES.md** - Quick start guide for PostgreSQL setup
  - Docker PostgreSQL container setup
  - Database initialization
  - Connection verification

### 📋 **reference/**
User guides, troubleshooting, and operational reference materials.

- **BANK_INTEGRATION_TROUBLESHOOTING.md** - TrueLayer bank integration troubleshooting
  - Common issues and solutions
  - Debugging techniques
  - Error messages explained

- **SETTINGS_BANK_INTEGRATION_GUIDE.md** - User guide for TrueLayer integration
  - Step-by-step integration instructions
  - Feature walkthrough
  - FAQ and common issues

### 📦 **project/**
Project planning, roadmap, and meta information.

- **DEVELOPMENT_PLAN.md** - Project development plan and roadmap
  - Feature development timeline
  - Technical decisions
  - Implementation strategy

---

## 📖 Where to Find What

### I want to... → Read this

| Task | Document | Location |
|------|----------|----------|
| Understand the database schema | DATABASE_SCHEMA.md | database/ |
| Add a new database column | DATABASE_SCHEMA.md + SCHEMA_ENFORCEMENT.md | database/ |
| Fix a "column does not exist" error | SCHEMA_CRITICAL_FIXES.md (Issue #3) | database/ |
| Fix a "can't adapt type 'dict'" error | SCHEMA_CRITICAL_FIXES.md (Issues #1, #2) | database/ |
| Set up PostgreSQL locally | QUICK_START_POSTGRES.md | development/setup/ |
| Review code that touches the database | SCHEMA_ENFORCEMENT.md (Code Review Checklist) | database/ |
| Understand TrueLayer integration | TRUELAYER_INTEGRATION.md | architecture/ |
| Troubleshoot TrueLayer connection issues | BANK_INTEGRATION_TROUBLESHOOTING.md | reference/ |
| Guide a user through bank integration | SETTINGS_BANK_INTEGRATION_GUIDE.md | reference/ |
| Migrate from SQLite to PostgreSQL | POSTGRES_MIGRATION.md | database/ |
| See development roadmap | DEVELOPMENT_PLAN.md | project/ |

---

## 🎯 Quick Navigation by Topic

### Database Work
1. Start: `database/DATABASE_SCHEMA.md`
2. Before coding: Check `database/SCHEMA_ENFORCEMENT.md` (pre-commit checklist)
3. If errors: `database/SCHEMA_CRITICAL_FIXES.md`
4. Code review: `database/SCHEMA_ENFORCEMENT.md` (code review section)

### TrueLayer Integration
1. Architecture: `architecture/TRUELAYER_INTEGRATION.md`
2. Troubleshooting: `reference/BANK_INTEGRATION_TROUBLESHOOTING.md`
3. User guide: `reference/SETTINGS_BANK_INTEGRATION_GUIDE.md`

### Local Development
1. PostgreSQL setup: `development/setup/QUICK_START_POSTGRES.md`
2. Database migration: `database/POSTGRES_MIGRATION.md`
3. Schema reference: `database/DATABASE_SCHEMA.md`

### Troubleshooting
1. TrueLayer issues: `reference/BANK_INTEGRATION_TROUBLESHOOTING.md`
2. Database errors: `database/SCHEMA_CRITICAL_FIXES.md`
3. PostgreSQL setup: `development/setup/QUICK_START_POSTGRES.md`

---

## 📊 Documentation Statistics

| Folder | Files | Purpose |
|--------|-------|---------|
| architecture/ | 1 | System design & integration patterns |
| database/ | 4 | Schema, migrations, enforcement, fixes |
| development/ | 1 | Local development setup |
| reference/ | 2 | User guides, troubleshooting |
| project/ | 1 | Planning & roadmap |

**Total:** 9 documentation files

---

## ✍️ Adding New Documentation

### Choosing the Right Folder

- **architecture/** - System design, major components, integration patterns
- **database/** - Schema, migrations, data models, SQL-related docs
- **design/** - UI/UX design, technical design decisions
- **development/** - Development setup, tools, workflows
- **operations/** - Deployment, monitoring, production operations
- **reference/** - Guides, troubleshooting, API references
- **releases/** - Release notes, changelogs
- **project/** - Project planning, roadmap, meta information

### Folder-Specific Guidelines

**database/ folder:**
- Always include a "Schema Changes" section if modifying tables
- Link to other database docs
- Include examples of correct usage
- Document common pitfalls

**development/ folder:**
- Step-by-step instructions
- Include prerequisites
- Add verification steps
- Provide troubleshooting

**reference/ folder:**
- Organize by feature/component
- Include FAQs
- Provide links to related docs
- Use practical examples

---

## 🔄 Documentation Maintenance

### Update When:
- Adding new database tables or columns
- Changing API endpoints
- Fixing significant bugs
- Modifying architecture
- Updating development setup

### How to Update:
1. Find the appropriate document in the folder structure
2. Update the relevant section
3. Add entry to "Schema Changes" or equivalent section
4. Update this README if folder structure changes
5. Commit changes with documentation

### Example Commit Message:
```
docs: Update DATABASE_SCHEMA.md with new transaction_metadata column

- Added new column definition to truelayer_transactions table
- Updated SCHEMA_CRITICAL_FIXES.md with examples
- Updated SCHEMA_ENFORCEMENT.md checklist
```

---

## 🎓 Documentation Standards

All documentation should follow these standards:

- ✅ Clear section headings with emoji icons
- ✅ Code examples for technical docs
- ✅ Tables for quick reference
- ✅ Links between related documents
- ✅ "When to use" sections for guidance
- ✅ Practical examples over theory
- ✅ Version dates when applicable

---

## 📝 Last Updated

- **2025-11-27** - Reorganized docs per CLAUDE.md specification
  - Created folder structure: project/, architecture/, design/, database/, containers/, development/, operations/, reference/, releases/
  - Moved existing docs to appropriate folders
  - Added comprehensive database schema documentation
  - Added schema enforcement guidelines
  - Added critical fixes documentation
  - Created this README

---

## 🔗 Related Files

- `.claude/CLAUDE.md` - Development rules and project overview
- `docs/` - Legacy documentation location (being migrated to .claude/docs/)
