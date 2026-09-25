"""The reset keeps the complete shared training corpus and no rider data."""

from __future__ import annotations

import sqlite3

import pytest
from soft_floyd_core.book_copy import copy_books
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
