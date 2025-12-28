# tests/conftest.py
"""
Pytest configuration for SQLAlchemy model tests.
"""
import sys
from pathlib import Path

# Add backend directory to Python path
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))
