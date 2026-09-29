"""coach training sessions

Revision ID: 9d2c41b7a6e3
Revises: 487fbddd43bf
Create Date: 2026-09-28 10:00:00.000000

Adds `coach_message.training_session_ids` (exec-plan 0011). Temporary
server_default so SQLite can backfill NOT NULL onto existing rows, dropped
again once added — same pattern as `487fbddd43bf`'s `workout_devices`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d2c41b7a6e3"
down_revision: str | Sequence[str] | None = "487fbddd43bf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("coach_message") as batch:
        batch.add_column(
            sa.Column("training_session_ids", sa.JSON(), nullable=False, server_default="[]")
        )
    with op.batch_alter_table("coach_message") as batch:
        batch.alter_column("training_session_ids", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("coach_message") as batch:
        batch.drop_column("training_session_ids")
