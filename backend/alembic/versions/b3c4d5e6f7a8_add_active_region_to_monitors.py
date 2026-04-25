"""add active_region to monitors

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-04-25 12:55:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "monitors",
        sa.Column("active_region", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_monitors_active_region", "monitors", ["active_region"], unique=False)
    op.create_foreign_key(
        "fk_monitors_active_region_probe_regions",
        "monitors",
        "probe_regions",
        ["active_region"],
        ["code"],
        ondelete="RESTRICT",
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            select m.id, min(mr.region_code) as active_region
            from monitors m
            left join monitor_regions mr on mr.monitor_id = m.id
            group by m.id
            """
        )
    ).fetchall()
    for monitor_id, active_region in rows:
        bind.execute(
            sa.text("update monitors set active_region = :active_region where id = :monitor_id"),
            {"monitor_id": monitor_id, "active_region": active_region or "global"},
        )

    op.alter_column("monitors", "active_region", nullable=False)


def downgrade() -> None:
    op.drop_constraint("fk_monitors_active_region_probe_regions", "monitors", type_="foreignkey")
    op.drop_index("ix_monitors_active_region", table_name="monitors")
    op.drop_column("monitors", "active_region")
