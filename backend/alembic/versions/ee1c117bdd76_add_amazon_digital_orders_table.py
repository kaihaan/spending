"""Add amazon_digital_orders table

Revision ID: ee1c117bdd76
Revises: b2c6ccfa452a
Create Date: 2025-12-30 17:00:32.151904

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ee1c117bdd76"
down_revision: str | None = "b2c6ccfa452a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create amazon_digital_orders table."""
    op.create_table(
        "amazon_digital_orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("asin", sa.String(length=20), nullable=False),
        sa.Column("product_name", sa.String(length=500), nullable=False),
        sa.Column("order_id", sa.String(length=50), nullable=False),
        sa.Column("digital_order_item_id", sa.String(length=100), nullable=False),
        sa.Column("order_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fulfilled_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("price_tax", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("publisher", sa.String(length=255), nullable=True),
        sa.Column("seller_of_record", sa.String(length=255), nullable=True),
        sa.Column("marketplace", sa.String(length=100), nullable=True),
        sa.Column("source_file", sa.String(length=255), nullable=True),
        sa.Column("matched_transaction_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("digital_order_item_id"),
    )
    op.create_index(
        "idx_amazon_digital_matched_txn",
        "amazon_digital_orders",
        ["matched_transaction_id"],
        unique=False,
    )
    op.create_index(
        "idx_amazon_digital_order_date",
        "amazon_digital_orders",
        ["order_date"],
        unique=False,
    )
    op.create_index(
        "idx_amazon_digital_order_id",
        "amazon_digital_orders",
        ["order_id"],
        unique=False,
    )
    op.create_index(
        "idx_amazon_digital_user_id", "amazon_digital_orders", ["user_id"], unique=False
    )


def downgrade() -> None:
    """Drop amazon_digital_orders table."""
    op.drop_index("idx_amazon_digital_user_id", table_name="amazon_digital_orders")
    op.drop_index("idx_amazon_digital_order_id", table_name="amazon_digital_orders")
    op.drop_index("idx_amazon_digital_order_date", table_name="amazon_digital_orders")
    op.drop_index("idx_amazon_digital_matched_txn", table_name="amazon_digital_orders")
    op.drop_table("amazon_digital_orders")
