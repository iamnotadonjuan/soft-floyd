"""Start one independent Garmin poller per registered account."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from soft_floyd_core.config import get_settings
from soft_floyd_core.db import session_scope
from soft_floyd_core.models import Account
from sqlalchemy import select

from soft_floyd_server.runtime import get_session_factory, get_sync_runner


@asynccontextmanager
async def poller_lifespan(app: FastAPI) -> AsyncIterator[None]:
    if not get_settings().garmin_poll_enabled:
        yield
        return

    stop = asyncio.Event()
    tasks: dict[int, asyncio.Task[None]] = {}

    async def supervise() -> None:
        while not stop.is_set():
            with session_scope(get_session_factory()) as session:
                owners = session.scalars(select(Account.id)).all()
            for owner in owners:
                if owner not in tasks or tasks[owner].done():
                    tasks[owner] = asyncio.create_task(
                        get_sync_runner(owner).run_forever(), name=f"garmin-poller-{owner}"
                    )
            try:
                await asyncio.wait_for(stop.wait(), timeout=30)
            except TimeoutError:
                pass

    supervisor = asyncio.create_task(supervise(), name="garmin-supervisor")
    try:
        yield
    finally:
        stop.set()
        supervisor.cancel()
        with suppress(asyncio.CancelledError):
            await supervisor
        for owner, task in tasks.items():
            get_sync_runner(owner).request_stop()
            task.cancel()
        for task in tasks.values():
            with suppress(asyncio.CancelledError):
                await task
