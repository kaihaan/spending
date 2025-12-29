## Skill 2: Database Migration, Evolution & Documentation (Operational Skill)

### Purpose

Used **after schemas exist**, often under production constraints.

### Responsibilities

* Schema evolution strategies
* Alembic migration authoring
* Zero-downtime migration planning
* Backfill strategies
* Data shape transformations
* Rollbacks & safety checks
* Schema documentation & changelogs

### Typical inputs

* Existing schema
* Target schema
* Environment constraints (prod traffic, replicas, etc.)

### Outputs

* Alembic migration scripts
* Ordered migration plans
* Rollback procedures
* Schema change documentation
* Release notes for DB changes

### Why it should be isolated

This skill needs:

* paranoia
* stepwise thinking
* production awareness
* tooling fluency

Mixing it with design abstraction dilutes its defensive posture.

---

## How they should **interact** (important)

Even though they are separate skills, they should share **artifacts**:

### Shared contract

* Canonical schema description format (e.g. markdown + DDL)
* Naming conventions
* Constraint semantics
* Documentation templates

### Typical flow

1. **Design skill** produces:

   * target schema + rationale
2. **Migration skill** consumes:

   * current schema
   * target schema
   * operational constraints
3. Migration skill generates:

   * safe transition path
   * documentation

This mirrors how senior engineers actually work.

---

## Optional: a thin “orchestration” meta-skill

If you want polish later, add a **lightweight coordinator** skill that:

* detects whether a task is *design* or *evolution*
* routes to the correct skill
* enforces shared conventions

This should stay thin — no real logic inside.

---

## Practical naming suggestion

* `db_design_planner`
* `db_schema_migration_manager`

Or, if you want explicit tooling emphasis:

* `relational_schema_architect`
* `alembic_migration_and_schema_docs`

---

Below is a **clean, professional reference table** summarizing **expert-level database design & management resources**, including **patterns/cookbooks** and **SQLAlchemy + Alembic-specific sources**.

---

### 📚 Professional Database Design & Management — Curated Web Resources

| Subject Area                         | Overview                                                                                       | URL                                                                                                                                                                                        |
| ------------------------------------ | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Relational Database Design Patterns  | Classic enterprise-grade relational design patterns, schema structure, and modeling concepts   | [https://www.odbms.org/wp-content/uploads/2013/11/PP2.pdf](https://www.odbms.org/wp-content/uploads/2013/11/PP2.pdf)                                                                       |
| Database Normalization & Refactoring | Principles for evolving schemas safely and maintaining data integrity                          | [https://en.wikipedia.org/wiki/Database_refactoring](https://en.wikipedia.org/wiki/Database_refactoring)                                                                                   |
| Orthogonal Database Design           | Advanced design principle that complements normalization and reduces redundancy                | [https://en.wikipedia.org/wiki/Principle_of_orthogonal_design](https://en.wikipedia.org/wiki/Principle_of_orthogonal_design)                                                               |
| Advanced Data Modeling Techniques    | Modern relational and hybrid modeling strategies used in large systems                         | [https://dataengineeracademy.com/blog/advanced-data-modeling-techniques/](https://dataengineeracademy.com/blog/advanced-data-modeling-techniques/)                                         |
| Modern Data Modeling Best Practices  | Contemporary modeling approaches for scalable systems                                          | [https://coalesce.io/data-insights/modern-data-modeling-techniques-tools-and-best-practices/](https://coalesce.io/data-insights/modern-data-modeling-techniques-tools-and-best-practices/) |
| Anchor Modeling                      | Agile and temporal database modeling methodology                                               | [https://en.wikipedia.org/wiki/Anchor_modeling](https://en.wikipedia.org/wiki/Anchor_modeling)                                                                                             |
| SQL Anti-Patterns                    | Research-driven analysis of common relational and SQL design mistakes                          | [https://pragprog.com/titles/bksap/sql-antipatterns/](https://pragprog.com/titles/bksap/sql-antipatterns/)                                                                                 |
| System Design – Relational Patterns  | Practical relational database patterns used in system design interviews and production systems | [https://hackernoon.com/the-system-design-cheat-sheet-relational-databases-part-1](https://hackernoon.com/the-system-design-cheat-sheet-relational-databases-part-1)                       |

---

### 🐍 SQLAlchemy — Expert & Architectural Resources

| Subject Area                         | Overview                                                                      | URL                                                                                                                                                      |
| ------------------------------------ | ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SQLAlchemy Official Documentation    | Authoritative reference for Core, ORM, async usage, and advanced patterns     | [https://docs.sqlalchemy.org](https://docs.sqlalchemy.org)                                                                                               |
| SQLAlchemy Architectural Patterns    | Deep dive into patterns implemented by SQLAlchemy (Data Mapper, Unit of Work) | [https://techspot.zzzeek.org/2012/02/07/patterns-implemented-by-sqlalchemy/](https://techspot.zzzeek.org/2012/02/07/patterns-implemented-by-sqlalchemy/) |
| SQLAlchemy Learning Library          | Curated talks, articles, and deep technical resources                         | [https://www.sqlalchemy.org/library.html](https://www.sqlalchemy.org/library.html)                                                                       |
| SQLAlchemy Performance & ORM Mastery | Practical guide to advanced ORM usage and performance considerations          | [https://deepnote.com/blog/ultimate-guide-to-sqlalchemy-library-in-python](https://deepnote.com/blog/ultimate-guide-to-sqlalchemy-library-in-python)     |

---

### 🔧 Alembic — Schema Migrations & Cookbooks

| Subject Area                     | Overview                                                   | URL                                                                                                                                                                                                                      |
| -------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Alembic Official Documentation   | Core reference for migrations, environments, and workflows | [https://alembic.sqlalchemy.org](https://alembic.sqlalchemy.org)                                                                                                                                                         |
| Alembic Cookbook                 | Practical migration recipes for real-world scenarios       | [https://alembic.sqlalchemy.org/en/latest/cookbook.html](https://alembic.sqlalchemy.org/en/latest/cookbook.html)                                                                                                         |
| Alembic Migration Best Practices | Production-grade schema migration strategies               | [https://www.pingcap.com/article/best-practices-alembic-schema-migration/](https://www.pingcap.com/article/best-practices-alembic-schema-migration/)                                                                     |
| Alembic Developer Guide          | End-to-end migration workflows and tips                    | [https://medium.com/@tejpal.abhyuday/alembic-database-migrations-the-complete-developers-guide-d3fc852a6a9e](https://medium.com/@tejpal.abhyuday/alembic-database-migrations-the-complete-developers-guide-d3fc852a6a9e) |
| Alembic + Versioning Patterns    | Advanced schema versioning and history tables              | [https://sqlalchemy-continuum.readthedocs.io/en/latest/alembic.html](https://sqlalchemy-continuum.readthedocs.io/en/latest/alembic.html)                                                                                 |
