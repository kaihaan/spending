# Task Completion Checklist

## Before ANY Database Work
- [ ] Read `.claude/docs/database/DATABASE_SCHEMA.md`
- [ ] Check `.claude/docs/database/SCHEMA_ENFORCEMENT.md` for patterns
- [ ] Review `.claude/docs/database/SCHEMA_CRITICAL_FIXES.md` for past bugs
- [ ] Verify column names match documentation exactly

## Before ANY TrueLayer Work
- [ ] Read `.claude/docs/architecture/TRUELAYER_INTEGRATION.md`
- [ ] Check relevant JSON spec in `.claude/docs/api/True Layer API/`
- [ ] Review troubleshooting guide if debugging

## Before ANY Feature Implementation
- [ ] Check `.claude/docs/requirements/` for spec
- [ ] If no spec exists, create one and get approval
- [ ] Clarify any ambiguous requirements with user
- [ ] Only then begin implementation

## Code Quality Checks
- [ ] Run linting: `ruff check .` (fix issues)
- [ ] Run type checking: `pyright`
- [ ] Format code: `ruff format .`
- [ ] Check for unused imports/variables
- [ ] Verify explicit return types for public functions
- [ ] Ensure no security vulnerabilities (XSS, SQL injection, etc.)

## Testing
- [ ] Run tests: `pytest`
- [ ] Verify all tests pass
- [ ] Add new tests for new functionality
- [ ] Check test coverage if applicable

## Docker-Specific Checks
- [ ] If Celery code changed: `docker-compose build celery && docker-compose up -d celery`
- [ ] If backend code changed: `docker-compose restart backend` (auto-reloads)
- [ ] Test changes in Docker environment
- [ ] Check logs: `docker-compose logs -f [service]`

## Documentation Updates
- [ ] Update relevant documentation if schema/API changed
- [ ] Add entry to schema change log if applicable
- [ ] Verify code matches documentation
- [ ] Update type hints and docstrings

## Final Verification
- [ ] Test the feature end-to-end
- [ ] Check for edge cases
- [ ] Verify error handling
- [ ] Review code for over-engineering (keep it simple!)
- [ ] Ensure backward compatibility or update all references

## Git Workflow
- [ ] Stage changes: `git add .`
- [ ] Commit with clear message: `git commit -m "feat: description"`
- [ ] Push to remote if ready: `git push`
