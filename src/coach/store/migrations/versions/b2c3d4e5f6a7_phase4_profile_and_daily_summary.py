"""phase4 rider_profile and daily_summary tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-20
"""

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rider_profile",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("discipline", sa.Text, nullable=False),
        sa.Column("city", sa.Text),
        sa.Column("country", sa.Text),
        sa.Column("terrain_notes", sa.Text),
        sa.Column("goals_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("freeform_notes", sa.Text),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("id = 1", name="single_rider"),
    )
    op.create_table(
        "daily_summary",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("date", sa.Date, nullable=False, unique=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("tokens_in", sa.Integer),
        sa.Column("tokens_out", sa.Integer),
        sa.Column("cache_read", sa.Integer),
        sa.Column("cost_usd", sa.Float),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("daily_summary")
    op.drop_table("rider_profile")
