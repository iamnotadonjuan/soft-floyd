"""Google accounts; fresh rider tables, shared book corpus.

Revision ID: 6767c65736c0
Revises: c2dbf4b4e115
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6767c65736c0"
down_revision: str | Sequence[str] | None = "c2dbf4b4e115"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OWNER_TABLES = (
    "rider_profile",
    "bike",
    "activity",
    "lap",
    "record",
    "garmin_sync_state",
    "coach_conversation",
    "coach_message",
    "coach_memory_note",
    "llm_usage",
)
_INDEXED = (
    "activity",
    "bike",
    "coach_conversation",
    "coach_memory_note",
    "coach_message",
    "lap",
    "record",
)


def upgrade() -> None:
    # Deliberately refuse to assign old single-rider data to a random Google
    # account. The reset command copies only books into a fresh DB.
    bind = op.get_bind()
    for table in _OWNER_TABLES:
        if bind.scalar(sa.text(f'SELECT EXISTS(SELECT 1 FROM "{table}" LIMIT 1)')):
            raise RuntimeError(
                "Account migration requires a fresh rider database. "
                "Use the documented book-copy command; the old DB stays untouched."
            )

    op.create_table(
        "account",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("google_sub", sa.String(255), nullable=False, unique=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("picture_url", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "auth_session",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )
    for table in _OWNER_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("account_id", sa.Integer(), nullable=table == "llm_usage"))
            batch.create_foreign_key(f"fk_{table}_account", "account", ["account_id"], ["id"])
            if table in _INDEXED:
                batch.create_index(f"ix_{table}_account_id", ["account_id"])
            if table in {"rider_profile", "garmin_sync_state"}:
                batch.create_unique_constraint(f"uq_{table}_account_id", ["account_id"])
    with op.batch_alter_table("activity") as batch:
        batch.add_column(sa.Column("garmin_id", sa.Integer(), nullable=False))
        batch.create_unique_constraint("uq_activity_account_garmin", ["account_id", "garmin_id"])


def downgrade() -> None:
    raise RuntimeError("The account-era database cannot be downgraded to a single rider")
