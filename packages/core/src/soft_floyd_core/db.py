"""Engine + session factory. SQLite only, single local file.

Schema is managed by Alembic (exec-plan 0002 introduced it — see
docs/exec-plans/tech-debt-tracker.md), not `Base.metadata.create_all()`
directly. `run_migrations` is idempotent and restart-safe: a fresh file
gets `upgrade head`; a database this app already created via the old
`create_all()` path (recognizable as having `rider_profile` but no
`alembic_version` table) gets the newer tables created once and is then
stamped to head, rather than failing on a `CREATE TABLE rider_profile`
collision.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from soft_floyd_core.models import Base

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _alembic_config(db_path: Path) -> Config:
    """Built entirely in Python, not by locating the repo's `alembic.ini` —
    `script_location` is set relative to this file, so this works
    regardless of where the package is installed from. `alembic.ini` at
    the repo root exists only for `uv run alembic ...` CLI convenience.
    """
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def run_migrations(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    alembic_cfg = _alembic_config(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        existing_tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    if "alembic_version" in existing_tables:
        command.upgrade(alembic_cfg, "head")
        return

    if "rider_profile" in existing_tables:
        # Legacy create_all()'d DB, predating this migration's baseline.
        # Create only the tables that baseline adds beyond rider_profile,
        # then stamp — re-running CREATE TABLE rider_profile would fail.
        engine = create_engine(f"sqlite:///{db_path}")
        try:
            new_tables = [t for name, t in Base.metadata.tables.items() if name != "rider_profile"]
            Base.metadata.create_all(engine, tables=new_tables)
        finally:
            engine.dispose()
        command.stamp(alembic_cfg, "head")
        return

    command.upgrade(alembic_cfg, "head")


def make_engine(db_path: Path) -> Engine:
    run_migrations(db_path)
    return create_engine(f"sqlite:///{db_path}")


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
