"""soft_floyd_core.db's migration path — fresh DBs, idempotent re-runs,
legacy pre-Alembic databases, and a model/migration drift guard.
"""

from __future__ import annotations

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from soft_floyd_core.db import make_engine
from soft_floyd_core.models import Base, RiderProfile
from sqlalchemy import create_engine, inspect


def test_fresh_db_reaches_head_with_all_tables(tmp_path):
    db_path = tmp_path / "db.sqlite"
    make_engine(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    tables = set(inspect(engine).get_table_names())
    engine.dispose()

    expected = {
        "activity",
        "alembic_version",
        "garmin_sync_state",
        "lap",
        "record",
        "rider_profile",
    }
    assert expected <= tables


def test_running_twice_is_a_no_op(tmp_path):
    db_path = tmp_path / "db.sqlite"
    make_engine(db_path)
    make_engine(db_path)  # must not raise

    engine = create_engine(f"sqlite:///{db_path}")
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert "activity" in tables


def test_legacy_pre_alembic_db_is_stamped_and_upgraded(tmp_path):
    """Simulates a DB created by the old create_all()-only scaffold
    (rider_profile only, no alembic_version) — must gain the newer
    tables and end up at head, not fail on a duplicate CREATE TABLE.
    """
    db_path = tmp_path / "db.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine, tables=[RiderProfile.__table__])
    engine.dispose()

    make_engine(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert {"activity", "alembic_version", "garmin_sync_state", "lap", "record"} <= tables


def test_autogenerate_produces_no_diff_against_current_models(tmp_path):
    """The drift guard: if models.py and the migrations directory ever
    disagree, alembic's own diff comparison would report added/removed
    tables or columns. Uses the public compare_metadata API directly
    against a fresh head DB rather than generating a throwaway revision
    file (which would otherwise land in the real versions/ directory).
    """
    db_path = tmp_path / "db.sqlite"
    make_engine(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={"render_as_batch": True})
            diffs = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert diffs == [], f"model/migration drift detected: {diffs}"
