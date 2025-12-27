"""
MCP Server for AI-Assisted Spending App Operations

Main entry point for the MCP server that exposes spending app operations
to AI assistants (Claude, future AI tools) via the Model Context Protocol.

Features:
- 29 MCP tools across 7 categories
- Smart defaults (90% of calls work with no parameters)
- Comprehensive error handling
- Health monitoring and analytics
- Both high-level workflows and low-level operations
- Transaction search and query capabilities

Usage:
    # Standalone mode (for testing)
    python -m backend.mcp_server.server

    # Via Claude Desktop (automatic)
    # Configure in ~/Library/Application Support/Claude/claude_desktop_config.json

Architecture:
    - Standalone Python process (separate from Flask backend)
    - Communication: stdio (MCP protocol) with Claude Desktop/CLI
    - HTTP client to Flask API (http://localhost:5000)
"""

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from .client.flask_client import FlaskAPIClient
from .config import config

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
        *([] if not config.LOG_FILE else [logging.FileHandler(config.LOG_FILE)]),
    ],
)

logger = logging.getLogger(__name__)

# Global Flask API client
# This will be initialized on server startup
flask_client: FlaskAPIClient = None


def get_flask_client() -> FlaskAPIClient:
    """Get Flask API client (lazy initialization)."""
    global flask_client
    if flask_client is None:
        flask_client = FlaskAPIClient()
        logger.info("Flask API client initialized")
    return flask_client


# ============================================================================
# Server Lifecycle Management
# ============================================================================


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[dict]:
    """
    Server lifecycle management.

    Handles:
    - Resource initialization on startup
    - Cleanup on shutdown
    - Health check verification
    """
    logger.info("MCP Server starting...")

    # Validate configuration
    is_valid, error = config.validate()
    if not is_valid:
        logger.error(f"Invalid configuration: {error}")
        raise ValueError(f"Configuration error: {error}")

    logger.info(f"Configuration: {config.get_summary()}")

    # Initialize Flask client
    client = get_flask_client()

    # Health check
    if not client.health_check():
        logger.warning("Flask API health check failed - server may not be running")
        logger.warning(f"Ensure Flask backend is running at {config.FLASK_API_URL}")
    else:
        logger.info("Flask API health check passed")

    logger.info("MCP Server started successfully")

    # Yield control (server runs here)
    try:
        yield {}
    finally:
        # Cleanup on shutdown
        logger.info("MCP Server shutting down...")
        if flask_client:
            flask_client.close()
        logger.info("MCP Server stopped")


# Create MCP server instance with lifespan
mcp = FastMCP(
    name="spending-app",
    dependencies=["requests>=2.31.0", "python-dateutil>=2.8.2"],
    lifespan=app_lifespan,
)


# ============================================================================
# Import Tool Implementations
# ============================================================================

# Tool implementations are imported from their respective modules
# Each module contains a category of tools:

if config.ENABLE_HIGH_LEVEL_TOOLS:
    logger.info("High-level workflow tools enabled")

if config.ENABLE_LOW_LEVEL_TOOLS:
    logger.info("Low-level operation tools enabled")

if config.ENABLE_ANALYTICS_TOOLS:
    logger.info("Analytics, monitoring, search, and Gmail debugging tools enabled")


# ============================================================================
# Server Entry Point
# ============================================================================


def main():
    """
    Main entry point for MCP server.

    Runs the server in stdio mode for communication with Claude Desktop/CLI.
    """
    logger.info("Starting MCP server in stdio mode...")

    # Run server with stdio transport
    # This enables communication with Claude Desktop/CLI via stdin/stdout
    asyncio.run(mcp.run())


if __name__ == "__main__":
    main()
