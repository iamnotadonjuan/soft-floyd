"""Checkpoint book passages so interrupted imports can resume.

Revision ID: b7219a2ed815
Revises: a93d827f6c10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7219a2ed815"
down_revision: str | Sequence[str] | None = "a93d827f6c10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "book",
        sa.Column("import_status", sa.String(), server_default="complete", nullable=False),
    )
    op.add_column("book_passage", sa.Column("ordinal", sa.Integer(), nullable=True))
    op.create_index(
        "ix_book_passage_book_ordinal", "book_passage", ["book_id", "ordinal"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_book_passage_book_ordinal", table_name="book_passage")
    op.drop_column("book_passage", "ordinal")
    op.drop_column("book", "import_status")
