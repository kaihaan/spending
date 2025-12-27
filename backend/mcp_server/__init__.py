"""
MCP Server for AI-Assisted Spending App Operations

Provides a Model Context Protocol (MCP) server that enables AI assistants
(Claude or future AI) to autonomously run spending app operations through
natural language interactions.

Key Features:
- High-level workflow tools (sync all, full pipeline)
- Low-level operation tools (individual sync operations)
- Matching operations (Amazon, Apple, Gmail)
- Enrichment operations (LLM categorization)
- Analytics and monitoring (health, logs, metrics)
- Status and connection tools

Architecture:
- Standalone Python process (separate from Flask backend)
- Communication: stdio (MCP protocol) with Claude Desktop/CLI
- HTTP client to Flask API (http://localhost:5000)
"""

__version__ = "1.0.0"
