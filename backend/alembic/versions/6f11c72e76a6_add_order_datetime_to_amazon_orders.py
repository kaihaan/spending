"""add_order_datetime_to_amazon_orders

Revision ID: 6f11c72e76a6
Revises: 73633fa666de
Create Date: 2025-12-31 20:08:49.229245

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6f11c72e76a6"
down_revision: str | None = "73633fa666de"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add order_datetime column to amazon_orders for grouped order matching.

    This column stores the full ISO timestamp from Amazon CSV exports
    (e.g., '2025-08-30T18:05:43Z') to enable matching multiple orders
    placed at the exact same time to a single bank transaction.
    """
    # Add the order_datetime column (nullable for existing records)
    op.add_column(
        "amazon_orders",
        sa.Column("order_datetime", sa.DateTime(timezone=True), nullable=True),
    )

    # Create index for efficient grouped order queries
    op.create_index(
        "idx_amazon_orders_datetime", "amazon_orders", ["order_datetime"], unique=False
    )

    # Backfill existing records: set order_datetime to order_date at midnight UTC
    op.execute(
        """
        UPDATE amazon_orders
        SET order_datetime = order_date::timestamp AT TIME ZONE 'UTC'
        WHERE order_datetime IS NULL
        """
    )


def downgrade() -> None:
    """Remove order_datetime column."""
    op.drop_index("idx_amazon_orders_datetime", table_name="amazon_orders")
    op.drop_column("amazon_orders", "order_datetime")
