"""Core test fixtures for integration tests.

Provides reusable fixtures for Flask test client, database cleanup,
API mocking, and test data loading.

CRITICAL: All tests use a separate TEST database to prevent data loss.

The test database is automatically created as a mirror of production schema
but with isolated data. Tests NEVER touch the production database.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import responses
from dotenv import load_dotenv
from flask import Flask
from sqlalchemy import URL, create_engine, text
from sqlalchemy.orm import sessionmaker

# Load environment variables
load_dotenv()

# Database credentials
POSTGRES_USER = os.getenv("POSTGRES_USER", "spending_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "spending_password")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5433"))
PRODUCTION_DB = os.getenv("POSTGRES_DB", "spending_db")
TEST_DB = os.getenv("POSTGRES_TEST_DB", "spending_db_test")

# CRITICAL: Set test mode BEFORE importing database modules
os.environ["TESTING"] = "true"
os.environ["POSTGRES_DB"] = TEST_DB


# ============================================================================
# TEST DATABASE SETUP
# ============================================================================


@pytest.fixture(scope="session")
def test_database_url():
    """Get test database URL.

    Returns:
        URL: SQLAlchemy URL for test database
    """
    return URL.create(
        "postgresql",
        username=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=TEST_DB,
    )


@pytest.fixture(scope="session")
def production_database_url():
    """Get production database URL (for schema copying only).

    Returns:
        URL: SQLAlchemy URL for production database
    """
    return URL.create(
        "postgresql",
        username=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=PRODUCTION_DB,
    )


@pytest.fixture(scope="session")
def test_engine(test_database_url):
    """Create test database engine.

    Uses a PERSISTENT test database that is only created if it doesn't exist.
    This allows test data to persist between test runs for faster iteration.

    The test database is a complete copy of production schema and data at creation time.
    Tests run against this copy, ensuring production data is never touched.

    To reset the test database to fresh state from production, manually run:
        DROP DATABASE spending_db_test;
    Then the next pytest run will recreate it from production.

    Yields:
        Engine: SQLAlchemy engine connected to test database
    """
    # Connect to postgres database to manage test database
    postgres_url = URL.create(
        "postgresql",
        username=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database="postgres",
    )
    postgres_engine = create_engine(postgres_url, isolation_level="AUTOCOMMIT")

    # Check if test database already exists
    with postgres_engine.connect() as conn:
        result = conn.execute(
            text(f"""
            SELECT 1 FROM pg_database WHERE datname = '{TEST_DB}'
        """)
        )
        db_exists = result.scalar() is not None

    if db_exists:
        print(f"\n✓ Test database exists: {TEST_DB} (persistent mode)")
        print("  Using existing test database - data persists between runs")
        print(f"  To reset: DROP DATABASE {TEST_DB}; then run pytest again")
    else:
        print("\n✓ Test database not found, creating from production template...")
        print(f"  Production: {PRODUCTION_DB}")
        print(f"  Test:       {TEST_DB}")

        # Use PostgreSQL's CREATE DATABASE WITH TEMPLATE to clone production
        # This copies both schema and data in a single atomic operation
        postgres_engine = create_engine(postgres_url, isolation_level="AUTOCOMMIT")

        try:
            with postgres_engine.connect() as conn:
                # First, ensure no one is connected to production (for template copy)
                conn.execute(
                    text(f"""
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = '{PRODUCTION_DB}'
                      AND pid <> pg_backend_pid()
                """)
                )

                # Create test database as a template copy of production
                conn.execute(
                    text(f"CREATE DATABASE {TEST_DB} WITH TEMPLATE {PRODUCTION_DB}")
                )
                print(
                    "✓ Test database created (mirrored schema + data from production)\n"
                )

        except Exception as e:
            print(f"✗ Failed to create test database from template: {e}")
            print("  Falling back to pg_dump/restore method...")

            # Fallback: Use pg_dump to copy production to test
            postgres_engine.dispose()

            # Create empty test database
            postgres_engine = create_engine(postgres_url, isolation_level="AUTOCOMMIT")
            with postgres_engine.connect() as conn:
                conn.execute(text(f"CREATE DATABASE {TEST_DB}"))

            # Dump production and restore to test
            dump_file = f"/tmp/{PRODUCTION_DB}_dump.sql"

            try:
                # Dump production database
                dump_cmd = [
                    "pg_dump",
                    f"--host={POSTGRES_HOST}",
                    f"--port={POSTGRES_PORT}",
                    f"--username={POSTGRES_USER}",
                    f"--dbname={PRODUCTION_DB}",
                    f"--file={dump_file}",
                    "--no-owner",
                    "--no-acl",
                ]
                env = os.environ.copy()
                env["PGPASSWORD"] = POSTGRES_PASSWORD
                subprocess.run(dump_cmd, check=True, env=env, capture_output=True)
                print(f"  ✓ Dumped production database to {dump_file}")

                # Restore to test database
                restore_cmd = [
                    "psql",
                    f"--host={POSTGRES_HOST}",
                    f"--port={POSTGRES_PORT}",
                    f"--username={POSTGRES_USER}",
                    f"--dbname={TEST_DB}",
                    f"--file={dump_file}",
                ]
                subprocess.run(restore_cmd, check=True, env=env, capture_output=True)
                print("  ✓ Restored data to test database")

                # Clean up dump file
                os.remove(dump_file)
                print("✓ Test database mirrored successfully (fallback method)\n")

            except subprocess.CalledProcessError as e:
                print(f"✗ Failed to mirror database: {e}")
                raise RuntimeError(f"Could not create test database mirror: {e}") from e

    postgres_engine.dispose()

    # Create engine for test database
    engine = create_engine(test_database_url, echo=False)

    # Verify the copy worked
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'"
            )
        )
        table_count = result.scalar()
        print(f"✓ Test database ready: {table_count} tables available")

    yield engine

    # DON'T drop the database - keep it persistent between runs
    # Users can manually drop it to reset: DROP DATABASE spending_db_test;
    engine.dispose()
    print(f"\n✓ Test session complete - database {TEST_DB} persists for next run")


@pytest.fixture(scope="session")
def test_session_local(test_engine):
    """Create session factory for test database.

    Args:
        test_engine: Test database engine fixture

    Returns:
        sessionmaker: Session factory bound to test database
    """
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


# ============================================================================
# FLASK TEST CLIENT FIXTURES
# ============================================================================


@pytest.fixture(scope="session")
def app() -> Flask:
    """Flask app with test configuration.

    Creates a Flask app instance configured for testing:
    - TESTING=True (disables error catching during request handling)
    - CELERY_ALWAYS_EAGER=True (run tasks synchronously)
    - WTF_CSRF_ENABLED=False (disable CSRF for easier testing)

    Returns:
        Flask: Configured Flask application instance
    """
    # Import app from app module (relative to backend directory)
    from app import app as flask_app

    # Override configuration for testing
    flask_app.config["TESTING"] = True
    flask_app.config["CELERY_ALWAYS_EAGER"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    flask_app.config["SERVER_NAME"] = "localhost:5000"

    return flask_app


@pytest.fixture
def client(app: Flask):
    """Flask test client for making HTTP requests.

    Provides a test client that can make requests to the Flask app
    without starting a real server.

    Args:
        app: Flask application fixture

    Returns:
        FlaskClient: Test client for making HTTP requests

    Example:
        def test_health_endpoint(client):
            response = client.get('/api/health')
            assert response.status_code == 200
    """
    return app.test_client()


@pytest.fixture
def app_context(app: Flask):
    """Flask application context.

    Provides an application context for tests that need access to
    Flask globals like current_app, g, etc.

    Args:
        app: Flask application fixture

    Yields:
        None: Application context is active during test
    """
    with app.app_context():
        yield


# ============================================================================
# DATABASE FIXTURES
# ============================================================================


@pytest.fixture
def db_session(test_session_local):
    """Create a fresh database session for each test.

    CRITICAL: Uses TEST database session (not production).
    All test operations are isolated from production data.

    Provides a database session that is rolled back after the test
    to ensure test isolation.

    Args:
        test_session_local: Test database session factory fixture

    Yields:
        Session: SQLAlchemy database session (connected to TEST database)

    Example:
        def test_create_user(db_session):
            user = User(email="test@example.com")
            db_session.add(user)
            db_session.commit()
            assert user.id is not None
    """
    session = test_session_local()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def clean_db(db_session):
    """Clean database state for each test.

    CRITICAL SAFETY: This fixture ONLY operates on the TEST database.
    Production database is never touched because db_session is connected
    to the test database via test_session_local.

    Truncates all tables in reverse dependency order to avoid
    foreign key constraint violations. Provides a fresh database
    state for each test.

    Args:
        db_session: Database session fixture (connected to TEST database)

    Returns:
        Session: Clean database session

    Note:
        Tables are truncated in reverse dependency order to avoid
        FK violations. Add new tables at the appropriate position
        in the list based on their dependencies.
    """
    # SAFETY CHECK: Verify we're operating on test database
    current_db = db_session.execute(text("SELECT current_database()")).scalar()
    if current_db != TEST_DB:
        raise RuntimeError(
            f"CRITICAL SAFETY VIOLATION: Attempting to truncate tables in '{current_db}' "
            f"but expected test database '{TEST_DB}'. "
            f"This fixture must ONLY operate on the test database to prevent production data loss."
        )

    # Tables in reverse dependency order (children before parents)
    tables = [
        # Matching tables (depend on transactions + receipts)
        "truelayer_amazon_business_matches",  # SP-API matches
        "truelayer_amazon_transaction_matches",  # Legacy consumer matches
        "truelayer_apple_transaction_matches",
        # Enrichment tables
        "llm_enrichment_cache",
        "transaction_enrichment_sources",
        # Gmail tables
        "pdf_attachments",
        "gmail_email_content",
        "gmail_receipts",
        "gmail_connections",
        # Amazon tables
        "amazon_business_line_items",
        "amazon_business_orders",
        "amazon_business_connections",
        "amazon_returns",
        "amazon_orders",
        # Apple tables
        "apple_transactions",
        # TrueLayer tables
        "truelayer_balances",
        "truelayer_transactions",
        "truelayer_accounts",
        "bank_connections",
        # Category tables
        "category_keywords",
        "categories",
        # Account mapping
        "account_mappings",
        # Users (parent of almost everything)
        "users",
    ]

    # Truncate all tables (suppress errors for non-existent tables)
    import contextlib

    for table in tables:
        with contextlib.suppress(Exception):
            db_session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))

    db_session.commit()

    return db_session


# ============================================================================
# API MOCKING FIXTURES
# ============================================================================


@pytest.fixture
def mock_responses():
    """Enable HTTP request mocking.

    Provides a responses.RequestsMock context manager that intercepts
    all HTTP requests made with the requests library. Use this to mock
    external API calls.

    Yields:
        RequestsMock: HTTP request mocking context manager

    Example:
        def test_api_call(mock_responses):
            mock_responses.add(
                responses.GET,
                'https://api.example.com/data',
                json={'result': 'success'},
                status=200
            )
            # Make request - will be intercepted
            response = requests.get('https://api.example.com/data')
            assert response.json()['result'] == 'success'
    """
    with responses.RequestsMock() as rsps:
        yield rsps


@pytest.fixture
def mock_truelayer_api(mock_responses):
    """Mock TrueLayer API responses.

    Pre-configured mocks for common TrueLayer API endpoints using
    fixture data from api_responses/truelayer/*.json.

    Args:
        mock_responses: HTTP mocking fixture

    Yields:
        RequestsMock: Configured with TrueLayer API mocks
    """
    # Load fixture data
    fixtures_dir = Path(__file__).parent / "api_responses" / "truelayer"

    # Mock accounts endpoint
    accounts_file = fixtures_dir / "accounts.json"
    if accounts_file.exists():
        with open(accounts_file) as f:
            accounts_data = json.load(f)
        mock_responses.add(
            responses.GET,
            "https://api.truelayer.com/data/v1/accounts",
            json=accounts_data,
            status=200,
        )

    # Mock transactions endpoint
    transactions_file = fixtures_dir / "transactions_page1.json"
    if transactions_file.exists():
        with open(transactions_file) as f:
            transactions_data = json.load(f)
        mock_responses.add(
            responses.GET,
            "https://api.truelayer.com/data/v1/accounts/*/transactions",
            json=transactions_data,
            status=200,
        )

    return mock_responses


# ============================================================================
# CELERY TESTING FIXTURES
# ============================================================================


@pytest.fixture(scope="session")
def celery_config():
    """Celery test configuration.

    Provides Celery configuration for testing with eager mode enabled.
    Tasks run synchronously in the same process for easier testing.

    Returns:
        dict: Celery configuration dictionary
    """
    return {
        "broker_url": os.getenv("REDIS_URL", "redis://localhost:6380/0"),
        "result_backend": os.getenv("REDIS_URL", "redis://localhost:6380/0"),
        "task_always_eager": True,  # Run tasks synchronously
        "task_eager_propagates": True,  # Propagate exceptions
        "task_ignore_result": False,  # Store results
    }


# ============================================================================
# TEST DATA HELPERS
# ============================================================================


def load_fixture(fixture_path: str) -> Any:
    """Load JSON fixture data from fixtures directory.

    Args:
        fixture_path: Relative path to fixture file (e.g., 'truelayer/accounts.json')

    Returns:
        Any: Parsed JSON data from fixture file

    Example:
        data = load_fixture('truelayer/accounts.json')
        assert 'results' in data
    """
    fixtures_dir = Path(__file__).parent / "api_responses"
    file_path = fixtures_dir / fixture_path

    if not file_path.exists():
        raise FileNotFoundError(f"Fixture file not found: {file_path}")

    with open(file_path) as f:
        return json.load(f)


def load_email_fixture(fixture_name: str) -> str:
    """Load email HTML fixture from sample_emails directory.

    Args:
        fixture_name: Name of email fixture file (e.g., 'amazon_fresh.html')

    Returns:
        str: HTML content of email fixture

    Example:
        html = load_email_fixture('amazon_fresh.html')
        assert 'Amazon Fresh' in html
    """
    fixtures_dir = Path(__file__).parent / "sample_emails"
    file_path = fixtures_dir / fixture_name

    if not file_path.exists():
        raise FileNotFoundError(f"Email fixture not found: {file_path}")

    with open(file_path) as f:
        return f.read()
