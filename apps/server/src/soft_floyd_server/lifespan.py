"""Starts/stops the background Garmin poller alongside the app.

This is the first feature needing our own startup/shutdown hook —
combined with FastMCP's own lifespan in main.py via `combine_lifespans`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from soft_floyd_core.config import get_settings

from soft_floyd_server.runtime import get_sync_runner


@asynccontextmanager
async def poller_lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if not settings.garmin_poll_enabled:
        yield
        return

    runner = get_sync_runner()
    task = asyncio.create_task(runner.run_forever(), name="garmin-poller")
    try:
        yield
    finally:
        runner.request_stop()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
