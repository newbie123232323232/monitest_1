"""add accepted_status_codes to monitors

Revision ID: d9e8f7a6b5c4
Revises: c1d2e3f4a5b6
Create Date: 2026-04-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d9e8f7a6b5c4"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "monitors",
        sa.Column(
            "accepted_status_codes",
            sa.String(length=255),
            nullable=False,
            server_default=sa.text("'200-399'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("monitors", "accepted_status_codes")
