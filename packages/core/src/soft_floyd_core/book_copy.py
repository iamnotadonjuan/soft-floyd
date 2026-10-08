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


def merge_books(source: Path, target: Path) -> tuple[int, int, int]:
    """Add the source's complete books that the live target lacks.

    Unlike `copy_books` this works on a database that already has rider
    data: nothing but `book` and `book_passage` is touched. Books are matched
    by `sha256`, so reruns add nothing, and new rows get fresh ids because
    the target may hold books of its own. Returns (books_added,
    passages_added, books_skipped).
    """
    source = source.resolve()
    target = target.resolve()
    if not source.is_file():
        raise ValueError(f"Source database does not exist: {source}")
    if not target.is_file():
        raise ValueError(f"Target database does not exist: {target}")
    if target == source:
        raise ValueError("Source and target must be different database paths")
    run_migrations(target)
    conn = sqlite3.connect(target, timeout=30, uri=True)
    try:
        conn.execute("ATTACH DATABASE ? AS legacy", (f"file:{source}?mode=ro",))
        with conn:
            wanted = conn.execute(
                "SELECT id, sha256, title, author, source_name, imported_at, import_status "
                "FROM legacy.book WHERE import_status = 'complete' ORDER BY id"
            ).fetchall()
            known = {row[0] for row in conn.execute("SELECT sha256 FROM main.book")}
            books_added = passages_added = 0
            expected_passages = 0
            for old_id, sha256, title, author, source_name, imported_at, status in wanted:
                if sha256 in known:
                    continue
                new_id = conn.execute(
                    "INSERT INTO main.book "
                    "(sha256, title, author, source_name, imported_at, import_status) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (sha256, title, author, source_name, imported_at, status),
                ).lastrowid
                expected_passages += conn.execute(
                    "SELECT COUNT(*) FROM legacy.book_passage WHERE book_id = ?", (old_id,)
                ).fetchone()[0]
                passages_added += conn.execute(
                    "INSERT INTO main.book_passage "
                    "(book_id, ordinal, page_start, page_end, text, embedding) "
                    "SELECT ?, ordinal, page_start, page_end, text, embedding "
                    "FROM legacy.book_passage WHERE book_id = ? ORDER BY ordinal, id",
                    (new_id, old_id),
                ).rowcount
                books_added += 1
            if passages_added != expected_passages:
                raise RuntimeError("Book merge verification failed")
        return books_added, passages_added, len(wanted) - books_added
    finally:
        conn.close()
