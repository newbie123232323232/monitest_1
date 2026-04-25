"""migrate probe_region csv to monitor_regions table

Revision ID: a2b3c4d5e6f7
Revises: f0e1d2c3b4a5
Create Date: 2026-04-25 12:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "f0e1d2c3b4a5"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "monitor_regions",
        sa.Column("monitor_id", sa.Uuid(), nullable=False),
        sa.Column("region_code", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["monitor_id"], ["monitors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["region_code"], ["probe_regions.code"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("monitor_id", "region_code"),
    )

    bind = op.get_bind()
    rows = bind.execute(sa.text("select id, probe_region from monitors")).fetchall()
    for monitor_id, raw in rows:
        tokens = []
        for token in (raw or "").split(","):
            cleaned = token.strip().lower()
            if cleaned and cleaned not in tokens:
                tokens.append(cleaned)
        if not tokens:
            tokens = ["global"]
        for idx, code in enumerate(tokens):
            name = " ".join(part.capitalize() for part in code.split("-"))
            bind.execute(
                sa.text(
                    """
                    insert into probe_regions (code, name, sort_order, is_active)
                    values (:code, :name, :sort_order, true)
                    on conflict (code) do nothing
                    """
                ),
                {"code": code, "name": name or code, "sort_order": 100 + idx},
            )
            bind.execute(
                sa.text(
                    """
                    insert into monitor_regions (monitor_id, region_code)
                    values (:monitor_id, :region_code)
                    on conflict (monitor_id, region_code) do nothing
                    """
                ),
                {"monitor_id": monitor_id, "region_code": code},
            )

    op.drop_column("monitors", "probe_region")


def downgrade() -> None:
    op.add_column("monitors", sa.Column("probe_region", sa.String(length=64), nullable=False, server_default="global"))

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            select monitor_id, string_agg(region_code, ',' order by region_code) as regions
            from monitor_regions
            group by monitor_id
            """
        )
    ).fetchall()
    for monitor_id, regions in rows:
        bind.execute(
            sa.text("update monitors set probe_region = :regions where id = :monitor_id"),
            {"monitor_id": monitor_id, "regions": regions or "global"},
        )

    op.drop_table("monitor_regions")
