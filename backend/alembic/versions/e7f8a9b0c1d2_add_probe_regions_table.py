"""add probe_regions table

Revision ID: e7f8a9b0c1d2
Revises: c9d8e7f6a5b4
Create Date: 2026-04-25 11:58:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "c9d8e7f6a5b4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "probe_regions",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("code"),
    )
    op.bulk_insert(
        sa.table(
            "probe_regions",
            sa.column("code", sa.String(length=64)),
            sa.column("name", sa.String(length=120)),
            sa.column("sort_order", sa.Integer()),
            sa.column("is_active", sa.Boolean()),
        ),
        [
            {"code": "global", "name": "Global", "sort_order": 10, "is_active": True},
            {"code": "us-east", "name": "US East", "sort_order": 20, "is_active": True},
            {"code": "eu-west", "name": "EU West", "sort_order": 30, "is_active": True},
        ],
    )


def downgrade() -> None:
    op.drop_table("probe_regions")
