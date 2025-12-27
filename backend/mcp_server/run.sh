#!/bin/bash
# Wrapper script to run MCP server with virtual environment activated

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Activate virtual environment
source "$PROJECT_ROOT/backend/venv/bin/activate"

# Run MCP server
cd "$PROJECT_ROOT"
exec python3 -m backend.mcp_server.server
