"""Pytest fixtures for Alembic migration tests."""

import pytest
from alembic import command
from alembic.config import Config


@pytest.fixture(scope="session")
def alembic_config():
    """Load Alembic configuration for migration tests.

    Returns:
        Config: Alembic configuration object pointing to alembic.ini
    """
    return Config("backend/alembic.ini")


@pytest.fixture
def clean_migration_state(alembic_config):
    """Ensure clean migration state for each test.

    This fixture:
    - Downgrades to base before the test
    - Yields control to the test
    - Downgrades to base after the test (cleanup)

    Args:
        alembic_config: Alembic configuration fixture

    Yields:
        None: Control to the test function
    """
    # Clean up before test
    command.downgrade(alembic_config, "base")
    yield
    # Clean up after test
    command.downgrade(alembic_config, "base")
