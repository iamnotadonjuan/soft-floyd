"""soft_floyd_core.db's migration path — fresh DBs, idempotent re-runs,
legacy pre-Alembic databases, and a model/migration drift guard.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from soft_floyd_core.db import make_engine
from soft_floyd_core.models import Base, RiderProfile
from sqlalchemy import create_engine, inspect, text

_MIGRATIONS_DIR = Path(__file__).parent.parent / "packages/core/src/soft_floyd_core/migrations"


def _alembic_config(db_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


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


def test_0004_seeds_one_bike_from_the_pre_garage_profile_row(tmp_path):
    """exec-plan 0004's data migration: a rider who already had a profile
    with sensor flags set directly on rider_profile must end up with
    exactly one bike carrying those same flags, not an empty garage.
    """
    db_path = tmp_path / "db.sqlite"
    cfg = _alembic_config(db_path)

    # Land at the revision immediately before 0004's, with the pre-garage
    # rider_profile schema (has_power_meter etc. still columns on it).
    command.upgrade(cfg, "cfd4848eaf23")

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO rider_profile "
                    "(id, weekly_rides, weekly_hours, primary_discipline, goal_text, "
                    " has_power_meter, has_hr_monitor, has_cadence_sensor, has_speed_sensor, "
                    " created_at, updated_at) "
                    "VALUES (1, 4, 6.5, 'mtb', 'get faster', 1, 1, 1, 0, "
                    " '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
                )
            )
    finally:
        engine.dispose()

    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as conn:
            bikes = conn.execute(
                text(
                    "SELECT kind, is_primary, has_power_meter, has_cadence_sensor, "
                    "has_speed_sensor FROM bike"
                )
            ).all()
            profile_columns = {c["name"] for c in inspect(engine).get_columns("rider_profile")}
    finally:
        engine.dispose()

    assert bikes == [("mtb", 1, 1, 1, 0)]
    # The seeded fields no longer live on rider_profile at all.
    assert "has_power_meter" not in profile_columns
    assert "has_cadence_sensor" not in profile_columns
    assert "has_speed_sensor" not in profile_columns
    assert "primary_discipline" not in profile_columns


def test_0004_seeds_nothing_for_a_fresh_database(tmp_path):
    """No pre-existing rider_profile row -> no bike is fabricated; the
    rider adds their first bike through onboarding's GarageStep instead.
    """
    db_path = tmp_path / "db.sqlite"
    cfg = _alembic_config(db_path)
    command.upgrade(cfg, "cfd4848eaf23")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM bike")).scalar_one()
    finally:
        engine.dispose()

    assert count == 0


def test_existing_books_migrate_as_complete(tmp_path):
    db_path = tmp_path / "db.sqlite"
    cfg = _alembic_config(db_path)
    command.upgrade(cfg, "a93d827f6c10")
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO book (sha256, title, source_name, imported_at) "
                    "VALUES (:sha256, 'Existing', 'existing.pdf', '2026-01-01 00:00:00')"
                ),
                {"sha256": "a" * 64},
            )
    finally:
        engine.dispose()

    command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as conn:
            status = conn.execute(text("SELECT import_status FROM book")).scalar_one()
    finally:
        engine.dispose()
    assert status == "complete"


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
