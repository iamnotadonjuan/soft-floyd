"""Copy the shared training corpus into a fresh account-era database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic.script import ScriptDirectory

from soft_floyd_core.db import _alembic_config, run_migrations


def _current_head() -> str:
    """The migrations directory's head revision, resolved dynamically so
    this check doesn't go stale every time a new migration lands (it did
    once already — see the git history of this line)."""
    return ScriptDirectory.from_config(_alembic_config(Path("unused"))).get_current_head()


def copy_books(source: Path, target: Path) -> tuple[int, int]:
    source = source.resolve()
    target = target.resolve()
    if not source.is_file():
        raise ValueError(f"Source database does not exist: {source}")
    if target == source:
        raise ValueError("Source and target must be different database paths")
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.exists()
    staging = target if existing else target.with_name(target.name + ".staging")
    if not existing:
        if staging.exists():
            raise ValueError(f"Remove or inspect existing staging database: {staging}")
        run_migrations(staging)
    try:
        with sqlite3.connect(staging, uri=True) as conn:
            if existing:
                version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
                if version != (_current_head(),):
                    raise ValueError("Existing target is not an account-era database")
                for table in (
                    "account",
                    "auth_session",
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
                    "book",
                    "book_passage",
                ):
                    if conn.execute(f'SELECT EXISTS(SELECT 1 FROM "{table}")').fetchone()[0]:
                        raise ValueError("Existing target is not empty")
            conn.execute("ATTACH DATABASE ? AS legacy", (f"file:{source}?mode=ro",))
            conn.execute(
                "INSERT INTO book "
                "(id, sha256, title, author, source_name, imported_at, import_status) "
                "SELECT id, sha256, title, author, source_name, imported_at, import_status "
                "FROM legacy.book WHERE import_status = 'complete'"
            )
            conn.execute(
                "INSERT INTO book_passage "
                "(id, book_id, ordinal, page_start, page_end, text, embedding) "
                "SELECT p.id, p.book_id, p.ordinal, p.page_start, p.page_end, p.text, p.embedding "
                "FROM legacy.book_passage p JOIN book b ON b.id = p.book_id"
            )
            books = conn.execute("SELECT COUNT(*) FROM book").fetchone()[0]
            passages = conn.execute("SELECT COUNT(*) FROM book_passage").fetchone()[0]
            expected_books = conn.execute(
                "SELECT COUNT(*) FROM legacy.book WHERE import_status = 'complete'"
            ).fetchone()[0]
            expected_passages = conn.execute(
                "SELECT COUNT(*) FROM legacy.book_passage p "
                "JOIN legacy.book b ON b.id = p.book_id WHERE b.import_status = 'complete'"
            ).fetchone()[0]
            if (books, passages) != (expected_books, expected_passages):
                raise RuntimeError("Book copy verification failed")
        if not existing:
            staging.replace(target)
        return books, passages
    except Exception:
        # Leave the staging DB for inspection; never alter the source.
        raise
