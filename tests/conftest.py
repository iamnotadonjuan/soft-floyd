from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient against a fresh SQLite file per test."""
    monkeypatch.setenv("SOFT_FLOYD_DB_PATH", str(tmp_path / "test.db"))

    from soft_floyd_server import runtime

    runtime.get_session_factory.cache_clear()

    from soft_floyd_server.main import app

    with TestClient(app) as test_client:
        yield test_client

    runtime.get_session_factory.cache_clear()
