"""The combined lifespan (poller_lifespan + mcp_app.lifespan via
FastMCP's combine_lifespans) actually works — the failure mode if this
regresses is a silent hang on /mcp, not an exception, so this is worth
testing explicitly rather than trusting the wiring by inspection alone.
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient


def test_poller_task_starts_and_stops_with_the_app(monkeypatch, tmp_path):
    """A fake SyncRunner whose run_forever() just marks an event, so this
    doesn't need a real Garmin client or database round-trip — it only
    proves the lifespan actually starts and cleanly cancels the task.

    Patches soft_floyd_server.lifespan's own get_sync_runner binding, not
    runtime.get_sync_runner — lifespan.py did `from runtime import
    get_sync_runner`, a separate binding resolved once at that module's
    first import. Patching only `runtime.get_sync_runner` works only by
    accident of import order (whether lifespan.py had already been
    imported by an earlier test) — this caused exactly that flake: an
    unpatched real SyncRunner ran for real and fired a live desktop
    notification. Patch lifespan.py's own name so this can't happen.
    """
    monkeypatch.setenv("SOFT_FLOYD_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SOFT_FLOYD_GARMIN_POLL_ENABLED", "1")

    from soft_floyd_server import lifespan, runtime

    runtime.get_session_factory.cache_clear()

    started = asyncio.Event()
    stopped = asyncio.Event()

    class FakeRunner:
        def request_stop(self):
            stopped.set()

        async def run_forever(self):
            started.set()
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                raise

    monkeypatch.setattr(lifespan, "get_sync_runner", lambda: FakeRunner())

    from soft_floyd_server.main import app

    with TestClient(app):
        # TestClient's __enter__ runs the app's startup; give the poller
        # task a moment to actually schedule and set the event.
        import time

        for _ in range(50):
            if started.is_set():
                break
            time.sleep(0.02)
        assert started.is_set(), "poller task never started"

    assert stopped.is_set(), "poller was never asked to stop on shutdown"

    runtime.get_session_factory.cache_clear()


def test_no_poller_task_when_disabled(monkeypatch, tmp_path):
    """garmin_poll_enabled=False must short-circuit before ever calling
    get_sync_runner() — proven by making that call raise if it happens,
    rather than by racing a fake task's counter.
    """
    monkeypatch.setenv("SOFT_FLOYD_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SOFT_FLOYD_GARMIN_POLL_ENABLED", "0")

    from soft_floyd_server import lifespan, runtime

    runtime.get_session_factory.cache_clear()

    def _must_not_be_called():
        raise AssertionError("get_sync_runner() was called despite garmin_poll_enabled=0")

    monkeypatch.setattr(lifespan, "get_sync_runner", _must_not_be_called)

    from soft_floyd_server.main import app

    with TestClient(app):
        pass  # if get_sync_runner() had been called, the AssertionError above would propagate here

    runtime.get_session_factory.cache_clear()


def test_mcp_endpoint_responds_after_combined_lifespan(client):
    """The hang guard: confirms mcp_app.lifespan actually ran (its session
    manager initialized) after being wrapped in combine_lifespans, by
    checking the MCP endpoint responds instead of hanging. `client` here
    disables the poller (SOFT_FLOYD_GARMIN_POLL_ENABLED=0 from
    conftest.py), isolating this to the MCP half of the combined lifespan.
    """
    response = client.post(
        "/mcp/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
        headers={"Accept": "application/json, text/event-stream"},
    )
    assert response.status_code != 404
    assert response.status_code < 500
