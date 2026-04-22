"""add probe_region and http metrics

Revision ID: c1d2e3f4a5b6
Revises: b8c1d2e3f4a5
Create Date: 2026-04-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "b8c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "monitors",
        sa.Column("probe_region", sa.String(length=64), nullable=False, server_default=sa.text("'global'")),
    )

    op.add_column("check_runs", sa.Column("dns_resolve_ms", sa.Integer(), nullable=True))
    op.add_column("check_runs", sa.Column("tcp_connect_ms", sa.Integer(), nullable=True))
    op.add_column("check_runs", sa.Column("tls_handshake_ms", sa.Integer(), nullable=True))
    op.add_column("check_runs", sa.Column("ttfb_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("check_runs", "ttfb_ms")
    op.drop_column("check_runs", "tls_handshake_ms")
    op.drop_column("check_runs", "tcp_connect_ms")
    op.drop_column("check_runs", "dns_resolve_ms")
    op.drop_column("monitors", "probe_region")
