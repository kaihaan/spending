#!/usr/bin/env python3
"""
Fix bare except clauses by replacing them with 'except Exception:'

This is safer because it allows SystemExit, KeyboardInterrupt, and
GeneratorExit to propagate normally.
"""

import re
import sys
from pathlib import Path


def fix_bare_except(file_path: Path) -> tuple[bool, int]:
    """
    Fix bare except clauses in a Python file.

    Returns:
        (changed, count) - Whether file was modified and number of fixes
    """
    content = file_path.read_text()
    original = content

    # Pattern: except: with optional whitespace
    # We need to be careful to only match actual bare except, not "except SomeError:"
    pattern = r'(\s+)except\s*:\s*(?:#.*)?$'
    replacement = r'\1except Exception:  # Fixed: was bare except'

    content, count = re.subn(pattern, replacement, content, flags=re.MULTILINE)

    if content != original:
        file_path.write_text(content)
        return True, count

    return False, 0


def main():
    # Navigate to backend directory from scripts/
    backend_dir = Path(__file__).parent.parent / "backend"

    # Files with bare except clauses
    files = [
        "database/gmail.py",
        "mcp/amazon_matcher.py",
        "mcp/amazon_returns_matcher.py",
        "mcp/amazon_sp_client.py",
        "mcp/apple_browser_import.py",
        "mcp/apple_matcher.py",
        "mcp/apple_matcher_truelayer.py",
        "mcp/gmail_matcher.py",
        "mcp/gmail_parser.py",
        "mcp/gmail_parsing/orchestrator.py",
        "mcp/gmail_sync.py",
        "mcp/truelayer_client.py",
        "mcp_server/tools/status.py",
    ]

    total_fixes = 0
    files_changed = 0

    for file_path_str in files:
        file_path = backend_dir / file_path_str
        if not file_path.exists():
            print(f"⚠️  Not found: {file_path_str}")
            continue

        changed, count = fix_bare_except(file_path)
        if changed:
            files_changed += 1
            total_fixes += count
            print(f"✅ Fixed {count:2d} bare except in {file_path_str}")

    print(f"\n📊 Summary: {total_fixes} bare except clauses fixed in {files_changed} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
