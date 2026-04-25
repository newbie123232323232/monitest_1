"""add status pages tables

Revision ID: f4a3b2c1d0e9
Revises: e2f1d0c9b8a7
Create Date: 2026-04-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4a3b2c1d0e9"
down_revision: Union[str, None] = "e2f1d0c9b8a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "status_pages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_status_pages_user_id"), "status_pages", ["user_id"], unique=False)
    op.create_index(op.f("ix_status_pages_slug"), "status_pages", ["slug"], unique=True)

    op.create_table(
        "status_page_monitors",
        sa.Column("status_page_id", sa.Uuid(), nullable=False),
        sa.Column("monitor_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["monitor_id"], ["monitors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["status_page_id"], ["status_pages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("status_page_id", "monitor_id"),
    )


def downgrade() -> None:
    op.drop_table("status_page_monitors")
    op.drop_index(op.f("ix_status_pages_slug"), table_name="status_pages")
    op.drop_index(op.f("ix_status_pages_user_id"), table_name="status_pages")
    op.drop_table("status_pages")
