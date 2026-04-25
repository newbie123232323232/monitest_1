"""add monitor_expiry_status table

Revision ID: a9b8c7d6e5f4
Revises: f4a3b2c1d0e9
Create Date: 2026-04-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, None] = "f4a3b2c1d0e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "monitor_expiry_status",
        sa.Column("monitor_id", sa.Uuid(), nullable=False),
        sa.Column("ssl_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ssl_days_left", sa.Integer(), nullable=True),
        sa.Column("ssl_state", sa.String(length=32), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("domain_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("domain_days_left", sa.Integer(), nullable=True),
        sa.Column("domain_state", sa.String(length=32), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["monitor_id"], ["monitors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("monitor_id"),
    )


def downgrade() -> None:
    op.drop_table("monitor_expiry_status")
