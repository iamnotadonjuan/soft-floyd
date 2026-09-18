"""garmin login cooldown

Revision ID: cfd4848eaf23
Revises: bd67396e9db5
Create Date: 2026-09-17 20:47:37.284247

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cfd4848eaf23"
down_revision: str | Sequence[str] | None = "bd67396e9db5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("garmin_sync_state", schema=None) as batch_op:
        batch_op.add_column(sa.Column("login_blocked_until", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("garmin_sync_state", schema=None) as batch_op:
        batch_op.drop_column("login_blocked_until")
