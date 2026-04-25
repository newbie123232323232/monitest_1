"""add probe_region to check_runs

Revision ID: d4e5f6a7b8c9
Revises: c9d8e7f6a5b4
Create Date: 2026-04-24 16:25:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c9d8e7f6a5b4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "check_runs",
        sa.Column("probe_region", sa.String(length=64), nullable=False, server_default="global"),
    )
    op.alter_column("check_runs", "probe_region", server_default=None)


def downgrade() -> None:
    op.drop_column("check_runs", "probe_region")
