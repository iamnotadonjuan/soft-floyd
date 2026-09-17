from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _refuse_to_connect(self, *args, **kwargs) -> None:
    raise AssertionError(
        "A test tried to construct a real garminconnect.Garmin. "
        "Pass an explicit client_factory instead."
    )


@pytest.fixture(autouse=True)
def _no_real_garmin(monkeypatch):
    """Patches garminconnect.Garmin.__init__ itself, not the name imported
    into soft_floyd_core.garmin.client — GarminClient's client_factory
    default argument is bound to the class object at import time, so
    patching only the module-level alias would silently miss it (default
    arguments capture a value once, at def time; __init__ lookup happens
    on the class at call time, which this does reach).
    """
    monkeypatch.setattr("garminconnect.Garmin.__init__", _refuse_to_connect)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient against a fresh SQLite file per test, with the
    background poller and any real Garmin auth disabled.
    """
    monkeypatch.setenv("SOFT_FLOYD_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SOFT_FLOYD_GARMIN_TOKEN_DIR", str(tmp_path / "garmin"))
    monkeypatch.setenv("SOFT_FLOYD_FIT_DIR", str(tmp_path / "fit"))
    monkeypatch.setenv("SOFT_FLOYD_GARMIN_POLL_ENABLED", "0")

    from soft_floyd_server import runtime

    runtime.get_session_factory.cache_clear()
    runtime.get_sync_runner.cache_clear()

    from soft_floyd_server.main import app

    with TestClient(app) as test_client:
        yield test_client

    runtime.get_session_factory.cache_clear()
    runtime.get_sync_runner.cache_clear()


@pytest.fixture
def road_fit_path() -> Path:
    """Full sensor rider: GPS + HR + cadence + power."""
    return FIXTURES_DIR / "sample_road.fit"


@pytest.fixture
def mtb_fit_path() -> Path:
    """GPS + HR only — no power meter, no cadence sensor."""
    return FIXTURES_DIR / "sample_mtb.fit"


@pytest.fixture
def indoor_fit_path() -> Path:
    """HR only — no GPS, no power, no cadence."""
    return FIXTURES_DIR / "sample_indoor.fit"
