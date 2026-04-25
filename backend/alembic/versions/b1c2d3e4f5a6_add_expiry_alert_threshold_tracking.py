"""add expiry alert threshold tracking

Revision ID: b1c2d3e4f5a6
Revises: a9b8c7d6e5f4
Create Date: 2026-04-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a9b8c7d6e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "monitor_expiry_status",
        sa.Column("ssl_alerted_thresholds", sa.String(length=128), nullable=False, server_default=sa.text("''")),
    )
    op.add_column(
        "monitor_expiry_status",
        sa.Column("domain_alerted_thresholds", sa.String(length=128), nullable=False, server_default=sa.text("''")),
    )
    op.execute("ALTER TYPE alert_event_type ADD VALUE IF NOT EXISTS 'ssl_expiry_warning'")
    op.execute("ALTER TYPE alert_event_type ADD VALUE IF NOT EXISTS 'domain_expiry_warning'")


def downgrade() -> None:
    op.drop_column("monitor_expiry_status", "domain_alerted_thresholds")
    op.drop_column("monitor_expiry_status", "ssl_alerted_thresholds")
