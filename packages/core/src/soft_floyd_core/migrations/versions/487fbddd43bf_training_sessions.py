"""training sessions

Revision ID: 487fbddd43bf
Revises: 6767c65736c0
Create Date: 2026-09-24 22:01:34.685333

Adds `training_session` (exec-plan 0010) and `rider_profile.workout_devices`.
`workout_devices` gets a temporary server_default so SQLite can backfill
NOT NULL onto any existing row, dropped again once added — same pattern
as `efb567af688f`'s `focus_areas`/`available_days`; future rows rely on
the ORM-level `default=list` instead.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "487fbddd43bf"
down_revision: str | Sequence[str] | None = "6767c65736c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "training_session",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("planned_date", sa.Date(), nullable=False),
        sa.Column("bike_id", sa.Integer(), nullable=True),
        sa.Column("setting", sa.String(length=16), nullable=False),
        sa.Column("discipline", sa.String(length=16), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("intent", sa.JSON(), nullable=False),
        sa.Column("workout", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("adjustments", sa.Text(), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("garmin_workout_id", sa.String(), nullable=True),
        sa.Column("sent_to_garmin_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.ForeignKeyConstraint(["bike_id"], ["bike.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("training_session", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_training_session_account_id"), ["account_id"], unique=False
        )

    with op.batch_alter_table("rider_profile", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("workout_devices", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )
    with op.batch_alter_table("rider_profile", schema=None) as batch_op:
        batch_op.alter_column("workout_devices", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("rider_profile", schema=None) as batch_op:
        batch_op.drop_column("workout_devices")

    with op.batch_alter_table("training_session", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_training_session_account_id"))

    op.drop_table("training_session")
