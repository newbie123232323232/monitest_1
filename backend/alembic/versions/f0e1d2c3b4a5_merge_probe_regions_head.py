"""merge probe_regions with latest head

Revision ID: f0e1d2c3b4a5
Revises: d4e5f6a7b8c9, e7f8a9b0c1d2
Create Date: 2026-04-25 12:02:00.000000
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "f0e1d2c3b4a5"
down_revision: tuple[str, str] = ("d4e5f6a7b8c9", "e7f8a9b0c1d2")
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
