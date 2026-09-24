"""Merge the independent book RAG and rider garage migration branches.

Revision ID: a93d827f6c10
Revises: 5960dbb7533a, efb567af688f
"""

from collections.abc import Sequence

revision: str = "a93d827f6c10"
down_revision: str | Sequence[str] | None = ("5960dbb7533a", "efb567af688f")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
