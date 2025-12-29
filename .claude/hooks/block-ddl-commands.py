#!/usr/bin/env python3
"""
Database DDL Protection Hook for Claude Code

Blocks dangerous SQL DDL commands (ALTER TABLE, DROP TABLE, CREATE TABLE, etc.)
in Bash tool calls, requiring the use of the database-migration skill instead.

This hook intercepts PreToolUse events for Bash commands and validates that they
don't contain schema-altering SQL operations.
"""
import json
import sys
import re

# SQL DDL keywords that require database-migration skill
DDL_KEYWORDS = [
    # Table operations
    r'\bCREATE\s+TABLE\b',
    r'\bDROP\s+TABLE\b',
    r'\bALTER\s+TABLE\b',
    r'\bRENAME\s+TABLE\b',
    r'\bTRUNCATE\s+TABLE\b',

    # Column operations
    r'\bADD\s+COLUMN\b',
    r'\bDROP\s+COLUMN\b',
    r'\bALTER\s+COLUMN\b',
    r'\bMODIFY\s+COLUMN\b',
    r'\bRENAME\s+COLUMN\b',

    # Index operations
    r'\bCREATE\s+INDEX\b',
    r'\bDROP\s+INDEX\b',
    r'\bCREATE\s+UNIQUE\s+INDEX\b',

    # Constraint operations
    r'\bADD\s+CONSTRAINT\b',
    r'\bDROP\s+CONSTRAINT\b',
    r'\bADD\s+PRIMARY\s+KEY\b',
    r'\bADD\s+FOREIGN\s+KEY\b',

    # Database operations
    r'\bCREATE\s+DATABASE\b',
    r'\bDROP\s+DATABASE\b',
    r'\bALTER\s+DATABASE\b',

    # Schema operations
    r'\bCREATE\s+SCHEMA\b',
    r'\bDROP\s+SCHEMA\b',
    r'\bALTER\s+SCHEMA\b',

    # Sequence operations
    r'\bCREATE\s+SEQUENCE\b',
    r'\bDROP\s+SEQUENCE\b',
]

def contains_ddl_keywords(command: str) -> tuple[bool, str]:
    """
    Check if command contains SQL DDL keywords.

    Returns:
        Tuple of (contains_ddl, matched_keyword)
    """
    for pattern in DDL_KEYWORDS:
        if re.search(pattern, command, re.IGNORECASE):
            match = re.search(pattern, command, re.IGNORECASE)
            return True, match.group(0)
    return False, ""

def main():
    """
    Main hook handler for PreToolUse event.

    Receives JSON input via stdin containing:
    - tool_name: The tool being called (e.g., "Bash")
    - tool_input: Input parameters (e.g., {"command": "..."})

    Returns:
        Exit code 0: Allow tool execution
        Exit code 2: Block tool execution with error message in stderr
    """
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Only validate Bash commands
    if tool_name != "Bash":
        sys.exit(0)

    command = tool_input.get("command", "")

    if not command:
        sys.exit(0)

    # Check for DDL keywords
    contains_ddl, keyword = contains_ddl_keywords(command)

    if contains_ddl:
        error_message = (
            f"\n"
            f"╔══════════════════════════════════════════════════════════════════╗\n"
            f"║  DATABASE SCHEMA CHANGE BLOCKED                                  ║\n"
            f"╠══════════════════════════════════════════════════════════════════╣\n"
            f"║  Direct DDL commands are not allowed for database safety.        ║\n"
            f"║                                                                  ║\n"
            f"║  Detected: {keyword:<53}║\n"
            f"║                                                                  ║\n"
            f"║  REQUIRED ACTION:                                                ║\n"
            f"║  1. Use /database-migration skill to plan the change             ║\n"
            f"║  2. Create an Alembic migration with proper rollback             ║\n"
            f"║  3. Update DATABASE_SCHEMA.md documentation                      ║\n"
            f"║  4. Run tests to verify the migration                            ║\n"
            f"║                                                                  ║\n"
            f"║  See: .claude/docs/database/SCHEMA_ENFORCEMENT.md                ║\n"
            f"╚══════════════════════════════════════════════════════════════════╝\n"
        )
        print(error_message, file=sys.stderr)
        sys.exit(2)

    # Allow the command to proceed
    sys.exit(0)

if __name__ == "__main__":
    main()
