"""add maintenance_notes to status_pages

Revision ID: c9d8e7f6a5b4
Revises: b1c2d3e4f5a6
Create Date: 2026-04-24 15:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d8e7f6a5b4"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("status_pages", sa.Column("maintenance_notes", sa.String(length=2000), nullable=True))


def downgrade() -> None:
    op.drop_column("status_pages", "maintenance_notes")
