from __future__ import annotations

import sqlite3
from collections.abc import Generator
from pathlib import Path

import sqlite_vec
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from coach.store.models import Base


def _load_sqlite_vec(dbapi_conn: sqlite3.Connection, _connection_record: object) -> None:
    dbapi_conn.enable_load_extension(True)
    sqlite_vec.load(dbapi_conn)
    dbapi_conn.enable_load_extension(False)


def make_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _load_sqlite_vec)
    return engine


def create_tables(engine: Engine) -> None:
    Base.metadata.create_all(engine)


_SessionLocal: sessionmaker | None = None


def init_db(db_path: Path) -> Engine:
    global _SessionLocal
    engine = make_engine(db_path)
    create_tables(engine)
    _SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return engine


def get_session() -> Generator[Session, None, None]:
    if _SessionLocal is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_sync_session() -> Session:
    if _SessionLocal is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    return _SessionLocal()
