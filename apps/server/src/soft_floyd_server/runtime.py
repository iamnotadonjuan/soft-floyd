"""Shared runtime wiring: one DB session factory, one Garmin SyncRunner —
each an `lru_cache`d singleton both adapters import rather than
constructing their own. There is exactly one database connection path
and exactly one place holding a Garmin session in this process.
"""

from __future__ import annotations

from functools import lru_cache

from soft_floyd_core.account_scope import account_id
from soft_floyd_core.config import get_settings
from soft_floyd_core.db import make_engine, make_session_factory
from soft_floyd_core.garmin.sync import SyncRunner
from sqlalchemy.orm import Session, sessionmaker


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    settings = get_settings()
    engine = make_engine(settings.db_path)
    return make_session_factory(engine)


@lru_cache
def get_sync_runner(owner: int) -> SyncRunner:
    settings = get_settings()
    per_account = settings.model_copy(
        update={"garmin_token_dir": settings.garmin_token_dir / str(owner)}
    )
    return SyncRunner(get_session_factory(), per_account, account_id=owner)


def current_sync_runner() -> SyncRunner:
    return get_sync_runner(account_id())
