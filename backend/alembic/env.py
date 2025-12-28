# backend/alembic/env.py
import os
import sys

from dotenv import load_dotenv

# Add backend to Python path so we can import database package
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Load environment
load_dotenv(override=False)

from logging.config import fileConfig  # noqa: E402

from alembic import context  # noqa: E402
from sqlalchemy import engine_from_config, pool  # noqa: E402

# this is the Alembic Config object
config = context.config

# Update config with env vars
config.set_main_option(
    "sqlalchemy.url",
    f"postgresql://{os.getenv('POSTGRES_USER', 'spending_user')}:"
    f"{os.getenv('POSTGRES_PASSWORD', 'spending_password')}@"
    f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
    f"{os.getenv('POSTGRES_PORT', '5433')}/"
    f"{os.getenv('POSTGRES_DB', 'spending_db')}",
)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import Base and all models for autogenerate support
from database.base import Base  # noqa: E402

# Models will be imported here as we create them in Phase 1:
# from database.models.user import User
# from database.models.category import Category, CategoryKeyword
# from database.models.truelayer import BankConnection, TrueLayerAccount, TrueLayerTransaction
# etc.

# Set target metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
