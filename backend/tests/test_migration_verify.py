"""Test migration completeness - verify SQLAlchemy models work."""

from sqlalchemy import text

from database.base import engine, get_session
from database.models.amazon import (
    AmazonBusinessConnection,
    AmazonBusinessLineItem,
    AmazonBusinessOrder,
    AmazonOrder,
    AmazonReturn,
    TrueLayerAmazonTransactionMatch,
)
from database.models.apple import (
    AppleTransaction,
    TrueLayerAppleTransactionMatch,
)
from database.models.category import Category
from database.models.enrichment import (
    EnrichmentCache,
    TransactionEnrichmentSource,
)
from database.models.gmail import (
    GmailConnection,
    GmailEmailContent,
    GmailReceipt,
    PDFAttachment,
)
from database.models.truelayer import (
    BankConnection,
    TrueLayerAccount,
    TrueLayerBalance,
    TrueLayerTransaction,
)
from database.models.user import User


def test_database_connection():
    """Test that SQLAlchemy can connect to the database."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


def test_all_tables_exist():
    """Test that all SQLAlchemy model tables exist in the database."""
    from sqlalchemy import inspect

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    # Expected tables from our SQLAlchemy models (22 tables)
    expected_tables = {
        "users",
        "account_mappings",
        "categories",
        "category_keywords",
        "bank_connections",
        "truelayer_accounts",
        "truelayer_transactions",
        "truelayer_balances",
        "amazon_orders",
        "amazon_returns",
        "amazon_business_connections",
        "amazon_business_orders",
        "amazon_business_line_items",
        "truelayer_amazon_transaction_matches",
        "apple_transactions",
        "truelayer_apple_transaction_matches",
        "gmail_connections",
        "gmail_receipts",
        "gmail_email_content",
        "pdf_attachments",
        "transaction_enrichment_sources",
        "llm_enrichment_cache",
    }

    # All expected tables should exist
    assert expected_tables.issubset(
        existing_tables
    ), f"Missing tables: {expected_tables - existing_tables}"


def test_user_model_query():
    """Test that User model can query the database."""
    with get_session() as session:
        # Should not raise an error (table may be empty)
        users = session.query(User).all()
        assert isinstance(users, list)


def test_category_model_query():
    """Test that Category model can query the database."""
    with get_session() as session:
        categories = session.query(Category).all()
        assert isinstance(categories, list)


def test_truelayer_models_query():
    """Test that TrueLayer models can query the database."""
    with get_session() as session:
        connections = session.query(BankConnection).all()
        accounts = session.query(TrueLayerAccount).all()
        transactions = session.query(TrueLayerTransaction).all()
        balances = session.query(TrueLayerBalance).all()

        assert isinstance(connections, list)
        assert isinstance(accounts, list)
        assert isinstance(transactions, list)
        assert isinstance(balances, list)


def test_amazon_models_query():
    """Test that Amazon models can query the database."""
    with get_session() as session:
        orders = session.query(AmazonOrder).all()
        returns = session.query(AmazonReturn).all()
        biz_conns = session.query(AmazonBusinessConnection).all()
        biz_orders = session.query(AmazonBusinessOrder).all()
        line_items = session.query(AmazonBusinessLineItem).all()
        matches = session.query(TrueLayerAmazonTransactionMatch).all()

        assert isinstance(orders, list)
        assert isinstance(returns, list)
        assert isinstance(biz_conns, list)
        assert isinstance(biz_orders, list)
        assert isinstance(line_items, list)
        assert isinstance(matches, list)


def test_apple_models_query():
    """Test that Apple models can query the database."""
    with get_session() as session:
        transactions = session.query(AppleTransaction).all()
        matches = session.query(TrueLayerAppleTransactionMatch).all()

        assert isinstance(transactions, list)
        assert isinstance(matches, list)


def test_gmail_models_query():
    """Test that Gmail models can query the database."""
    with get_session() as session:
        connections = session.query(GmailConnection).all()
        receipts = session.query(GmailReceipt).all()
        content = session.query(GmailEmailContent).all()
        pdfs = session.query(PDFAttachment).all()

        assert isinstance(connections, list)
        assert isinstance(receipts, list)
        assert isinstance(content, list)
        assert isinstance(pdfs, list)


def test_enrichment_models_query():
    """Test that Enrichment models can query the database."""
    with get_session() as session:
        sources = session.query(TransactionEnrichmentSource).all()
        cache = session.query(EnrichmentCache).all()

        assert isinstance(sources, list)
        assert isinstance(cache, list)


def test_session_context_manager():
    """Test that get_session() context manager works correctly."""
    # Normal flow
    with get_session() as session:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1

    # Error handling
    try:
        with get_session() as session:
            # Force an error
            session.execute(text("SELECT * FROM nonexistent_table"))
    except Exception:
        # Should handle error and close session
        pass


def test_alembic_version_tracking():
    """Test that Alembic version table exists and is tracking migrations."""
    with engine.connect() as conn:
        # Check alembic_version table exists
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        version = result.scalar()

        # Should have our migration version (baseline from re-baseline operation)
        assert version == "b2c6ccfa452a"
