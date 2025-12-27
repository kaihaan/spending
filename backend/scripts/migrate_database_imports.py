#!/usr/bin/env python3
"""
Script to migrate database_postgres imports to the new modular database package.

Replaces:
- import database_postgres as database → import database
- import database_postgres as db → import database as db
- import database_postgres → import database
- from database_postgres import ... → from database import ...
"""

import re
from pathlib import Path

# Patterns to replace
PATTERNS = [
    # Pattern 1: import database_postgres as database
    (r"^(\s*)import\s+database_postgres\s+as\s+database(\s*)$", r"\1import database\2"),
    # Pattern 2: import database_postgres as db
    (r"^(\s*)import\s+database_postgres\s+as\s+db(\s*)$", r"\1import database as db\2"),
    # Pattern 3: import database_postgres (no alias)
    (r"^(\s*)import\s+database_postgres(\s*)$", r"\1import database\2"),
    # Pattern 4: from database_postgres import ...
    (r"^(\s*)from\s+database_postgres\s+import\s+", r"\1from database import "),
]

# Files to exclude from migration
EXCLUDE_FILES = {
    "database_postgres.py",  # The old monolithic file itself
    "migrate_database_imports.py",  # This script
}

# Directories to exclude
EXCLUDE_DIRS = {
    "__pycache__",
    ".git",
    "venv",
}


def should_process_file(file_path):
    """Check if file should be processed."""
    # Must be a Python file
    if file_path.suffix != ".py":
        return False

    # Check if in excluded directories
    if any(excluded in file_path.parts for excluded in EXCLUDE_DIRS):
        return False

    # Check if in excluded files
    if file_path.name in EXCLUDE_FILES:
        return False

    return True


def migrate_imports_in_file(file_path):
    """Migrate database_postgres imports in a single file."""
    with open(file_path) as f:
        original_content = f.read()

    modified_content = original_content
    lines_changed = 0

    # Apply each pattern
    for pattern, replacement in PATTERNS:
        modified_content, count = re.subn(
            pattern, replacement, modified_content, flags=re.MULTILINE
        )
        lines_changed += count

    # Only write if changes were made
    if modified_content != original_content:
        with open(file_path, "w") as f:
            f.write(modified_content)
        return lines_changed

    return 0


def main():
    """Main migration function."""
    backend_dir = Path(__file__).parent.parent

    files_processed = 0
    total_changes = 0

    print("=" * 60)
    print("Database Import Migration")
    print("=" * 60)
    print()

    # Find all Python files in backend/
    for file_path in backend_dir.rglob("*.py"):
        if not should_process_file(file_path):
            continue

        # Check if file contains database_postgres import
        with open(file_path) as f:
            content = f.read()
            if "database_postgres" not in content:
                continue

        # Migrate the file
        changes = migrate_imports_in_file(file_path)

        if changes > 0:
            rel_path = file_path.relative_to(backend_dir)
            print(f"✓ {rel_path} ({changes} change{'s' if changes > 1 else ''})")
            files_processed += 1
            total_changes += changes

    print()
    print("=" * 60)
    print("Migration complete!")
    print(f"  Files processed: {files_processed}")
    print(f"  Total changes: {total_changes}")
    print("=" * 60)


if __name__ == "__main__":
    main()
