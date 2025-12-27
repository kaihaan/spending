# Python Code Quality Setup

This project uses **ruff** and **pyright** for maintaining code quality.

## Quick Start

### Install Tools (Already Done!)

Development dependencies are installed in `backend/venv`:

```bash
source backend/venv/bin/activate
pip install -r backend/requirements-dev.txt
```

### Check Code Quality

```bash
# Run all checks
./scripts/check-code-quality.sh

# Or manually:
source backend/venv/bin/activate
cd backend
ruff check .              # Lint code
ruff format --check .     # Check formatting
pyright                   # Type check
```

### Auto-Fix Issues

```bash
# Auto-fix formatting and linting issues
./scripts/fix-code-quality.sh

# Or manually:
source backend/venv/bin/activate
cd backend
ruff format .         # Format all code
ruff check --fix .    # Fix linting issues
```

## What Gets Checked

### Ruff (Linter + Formatter)

Ruff combines the functionality of:
- **black** (code formatting)
- **isort** (import sorting)
- **flake8** (linting)
- **pyupgrade** (Python upgrade patterns)
- **flake8-bugbear** (bug detection)

Current status: **1828 errors found** (1355 auto-fixable)

Common issues found:
- Import sorting (520 files)
- Module imports not at top (27 occurrences)
- Unused variables (22 occurrences)
- Timezone handling (27 occurrences)
- Collapsible if statements (24 occurrences)

### Pyright (Type Checker)

Static type checking for Python:
- Catches type errors before runtime
- Improves code documentation
- Better IDE autocomplete

## Configuration Files

- **`pyproject.toml`** - Ruff configuration
- **`pyrightconfig.json`** - Pyright type checking settings
- **`.pre-commit-config.yaml`** - Git pre-commit hooks
- **`.vscode/settings.json`** - VSCode integration

## Pre-commit Hooks (Optional)

Install pre-commit hooks to automatically check code before commits:

```bash
source backend/venv/bin/activate
pre-commit install
```

Now ruff will run automatically on every commit!

To run manually on all files:
```bash
pre-commit run --all-files
```

## VSCode Integration

Install the **Ruff extension** for real-time linting and auto-formatting:

1. Open VSCode
2. Install extension: `charliermarsh.ruff`
3. Settings are already configured in `.vscode/settings.json`

Features enabled:
- ✅ Format on save
- ✅ Auto-fix imports
- ✅ Real-time linting
- ✅ Type checking with Pyright

## CI/CD Integration (Future)

Add to GitHub Actions workflow:

```yaml
- name: Check code quality
  run: |
    pip install ruff pyright
    ruff check backend/
    ruff format --check backend/
    pyright
```

## Customizing Rules

### Disable Specific Rules

```python
# Disable for entire file
# ruff: noqa: E501

# Disable for single line
x = very_long_line()  # noqa: E501

# Type ignore
result = external_api()  # type: ignore
```

### Modify Configuration

Edit `pyproject.toml` to change rules:

```toml
[tool.ruff.lint]
ignore = [
    "E501",  # line too long (already ignored)
    "N802",  # function name lowercase (Flask routes)
]
```

## Next Steps

1. ✅ Tools installed and configured
2. 🔄 **Run `./scripts/fix-code-quality.sh`** to auto-fix 1355 issues
3. ⚙️ Install pre-commit hooks (optional): `pre-commit install`
4. 🔧 Install VSCode Ruff extension (optional)
5. 📊 Review remaining issues and fix manually

## Statistics

Initial scan results:
- **Total issues:** 1828
- **Auto-fixable:** 1355 (74%)
- **Manual fixes needed:** 473
- **Files analyzed:** 520+

Run `ruff check . --statistics` to see detailed breakdown.

## Resources

- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Pyright Documentation](https://microsoft.github.io/pyright/)
- [Pre-commit Hooks](https://pre-commit.com/)
