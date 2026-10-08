"""The reset keeps the complete shared training corpus and no rider data."""

from __future__ import annotations

import sqlite3

import pytest
from soft_floyd_core.book_copy import copy_books, merge_books
from soft_floyd_core.db import make_engine


def test_copy_books_preserves_complete_passages_only(tmp_path):
    source = tmp_path / "old.db"
    target = tmp_path / "accounts.db"
    make_engine(source)
    with sqlite3.connect(source) as conn:
        conn.execute(
            "INSERT INTO book (id, sha256, title, source_name, imported_at, import_status) "
            "VALUES (1, 'one', 'Complete', 'a.pdf', '2026-01-01', 'complete'), "
            "(2, 'two', 'Incomplete', 'b.pdf', '2026-01-01', 'importing')"
        )
        conn.execute(
            "INSERT INTO book_passage (book_id, ordinal, page_start, page_end, text, embedding) "
            "VALUES (1, 0, 3, 3, 'ride smarter', x'01020304'), "
            "(2, 0, 4, 4, 'unfinished', x'05060708')"
        )
    assert copy_books(source, target) == (1, 1)
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT title FROM book").fetchall() == [("Complete",)]
        assert conn.execute("SELECT text, embedding FROM book_passage").fetchall() == [
            ("ride smarter", b"\x01\x02\x03\x04")
        ]
        assert conn.execute("SELECT COUNT(*) FROM account").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM activity").fetchone()[0] == 0
    with pytest.raises(ValueError, match="not empty"):
        copy_books(source, target)


def _seed(path, books, passages):
    make_engine(path)
    with sqlite3.connect(path) as conn:
        conn.executemany(
            "INSERT INTO book (id, sha256, title, source_name, imported_at, import_status) "
            "VALUES (?, ?, ?, 'x.pdf', '2026-01-01', ?)",
            books,
        )
        conn.executemany(
            "INSERT INTO book_passage (book_id, ordinal, page_start, page_end, text, embedding) "
            "VALUES (?, ?, 1, 1, ?, ?)",
            passages,
        )


def test_merge_books_adds_missing_complete_books_with_fresh_ids(tmp_path):
    source = tmp_path / "local.db"
    target = tmp_path / "live.db"
    _seed(
        source,
        [
            (1, "aaa", "Shared", "complete"),
            (2, "bbb", "New", "complete"),
            (3, "ccc", "Half", "importing"),
        ],
        [
            (1, 0, "shared text", b"\x01"),
            (2, 0, "new zero", b"\x02"),
            (2, 1, "new one", b"\x03"),
            (3, 0, "half", b"\x04"),
        ],
    )
    # The live DB already holds "Shared" under another id plus its own book 2.
    _seed(
        target,
        [(1, "own", "Server only", "complete"), (2, "aaa", "Shared", "complete")],
        [(1, 0, "server text", b"\x09"), (2, 0, "shared text", b"\x01")],
    )
    with sqlite3.connect(target) as conn:
        conn.execute(
            "INSERT INTO account (google_sub, email, name, created_at) "
            "VALUES ('sub', 'me@example.com', 'Me', '2026-01-01')"
        )

    assert merge_books(source, target) == (1, 2, 1)

    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT id, title FROM book ORDER BY id").fetchall() == [
            (1, "Server only"),
            (2, "Shared"),
            (3, "New"),
        ]
        assert conn.execute(
            "SELECT book_id, ordinal, text, embedding FROM book_passage WHERE book_id = 3 "
            "ORDER BY ordinal"
        ).fetchall() == [(3, 0, "new zero", b"\x02"), (3, 1, "new one", b"\x03")]
        assert conn.execute("SELECT COUNT(*) FROM book_passage").fetchone()[0] == 4
        assert conn.execute("SELECT email FROM account").fetchall() == [("me@example.com",)]
    with sqlite3.connect(source) as conn:
        assert conn.execute("SELECT COUNT(*) FROM book").fetchone()[0] == 3


def test_merge_books_is_idempotent(tmp_path):
    source = tmp_path / "local.db"
    target = tmp_path / "live.db"
    _seed(source, [(1, "aaa", "One", "complete")], [(1, 0, "t", b"\x01")])
    make_engine(target)
    assert merge_books(source, target) == (1, 1, 0)
    assert merge_books(source, target) == (0, 0, 1)
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT COUNT(*) FROM book_passage").fetchone()[0] == 1


def test_merge_books_rejects_missing_or_same_database(tmp_path):
    db = tmp_path / "a.db"
    make_engine(db)
    with pytest.raises(ValueError, match="does not exist"):
        merge_books(tmp_path / "nope.db", db)
    with pytest.raises(ValueError, match="does not exist"):
        merge_books(db, tmp_path / "nope.db")
    with pytest.raises(ValueError, match="different"):
        merge_books(db, db)
