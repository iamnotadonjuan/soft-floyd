"""Shared runtime wiring: one DB session factory for both adapters.

mcp_server.py and http_api.py both import get_session_factory() rather
than constructing their own engine — there is exactly one database
connection path in this process.
"""

from __future__ import annotations

from functools import lru_cache

from soft_floyd_core.config import get_settings
from soft_floyd_core.db import make_engine, make_session_factory
from sqlalchemy.orm import Session, sessionmaker


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    settings = get_settings()
    engine = make_engine(settings.db_path)
    return make_session_factory(engine)
