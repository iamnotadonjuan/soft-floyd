"""SQLAlchemy 2.x typed models.

RiderProfile + Bike (exec-plan 0004) are the profile-side tables.
Activity/Lap/Record/GarminSyncState (exec-plan 0002) add real ride data.
See docs/design-docs/sensor-capability-model.md for why RiderProfile's
and Bike's sensor flags are a *planning* signal while Activity's
has_*_data columns are the *analysis* signal, derived independently from
each ride's own FIT data — never assume the two agree.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from sqlalchemy import JSON, ForeignKey, Index, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

Discipline = Literal["road", "mtb", "gravel"]
# BikeKind (Bike.kind, exec-plan 0004): what a rider says a bike *is*, declared
# at garage-setup time. Deliberately distinct from BikeType below — never
# merge the two, they answer different questions from different signals.
BikeKind = Literal["road", "gravel", "mtb", "tt", "indoor"]
# BikeType (Activity.bike_type): what a specific *ride* was classified as,
# derived from that activity's own FIT/summary data by
# activities/classify.py. A rider can own a BikeKind="gravel" bike whose
# rides still classify as BikeType="mtb" today — see exec-plan 0004's
# tech-debt entry; the classifier isn't garage-aware yet.
BikeType = Literal["road", "mtb", "indoor", "other"]
FitStatus = Literal["pending", "ok", "missing", "download_failed", "parse_failed"]
SyncStatus = Literal["never", "ok", "reauth_required", "rate_limited", "error"]
SelfRatedLevel = Literal["beginner", "recreational", "enthusiast", "competitive"]


class Base(DeclarativeBase):
    pass


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class RiderProfile(Base):
    """Single-row table: this app coaches one rider.

    Bike-mounted sensors (power/cadence/speed) live on Bike, not here —
    exec-plan 0004. has_hr_monitor stays here because a strap is
    body-worn, not bike-mounted. profile/service.py's capability_tier()
    unions this profile's HR flag with every Bike's sensors to derive
    what the coach may compute; per-activity analysis must still check
    the actual FIT stream — a flag here means "usually available," not
    "present in this ride."
    """

    __tablename__ = "rider_profile"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)

    # Volume + goals
    weekly_rides: Mapped[int] = mapped_column(default=0)
    weekly_hours: Mapped[float] = mapped_column(default=0.0)
    goal_text: Mapped[str] = mapped_column(default="")
    target_event_name: Mapped[str | None] = mapped_column(default=None)
    target_event_date: Mapped[dt.date | None] = mapped_column(default=None)
    # JSON list of focus tags, e.g. ["climbing", "endurance"] — see
    # docs/product-specs/new-user-onboarding.md for the fixed vocabulary.
    focus_areas: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Experience
    years_riding: Mapped[float | None] = mapped_column(default=None)
    longest_recent_ride_km: Mapped[float | None] = mapped_column(default=None)
    followed_plan_before: Mapped[bool | None] = mapped_column(default=None)
    self_rated_level: Mapped[str | None] = mapped_column(String(16), default=None)

    # Availability
    available_days: Mapped[list[str]] = mapped_column(JSON, default=list)  # ["mon", "wed", ...]
    weekday_max_minutes: Mapped[int | None] = mapped_column(default=None)
    weekend_max_minutes: Mapped[int | None] = mapped_column(default=None)

    # Body & health
    birth_year: Mapped[int | None] = mapped_column(default=None)
    weight_kg: Mapped[float | None] = mapped_column(default=None)
    max_hr: Mapped[int | None] = mapped_column(default=None)
    health_notes: Mapped[str | None] = mapped_column(default=None)

    # Body-worn sensor — see class docstring for why this isn't on Bike.
    has_hr_monitor: Mapped[bool] = mapped_column(default=True)

    # Anchors — only meaningful alongside the matching sensor flag
    ftp_watts: Mapped[int | None] = mapped_column(default=None)
    lthr: Mapped[int | None] = mapped_column(default=None)

    created_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class Bike(Base):
    """One bike in the rider's garage. Bike-mounted sensors (power,
    cadence, speed) live here rather than on RiderProfile so "power meter
    on the road bike, nothing on the gravel bike" is representable — see
    docs/design-docs/sensor-capability-model.md. An indoor trainer is
    just a bike with kind="indoor"; there is no separate trainer concept.

    Exactly one row has is_primary=True at all times — enforced by
    bikes/service.py, not by a DB constraint (SQLite has no partial
    unique index in the version this project targets).
    """

    __tablename__ = "bike"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nickname: Mapped[str] = mapped_column(default="")
    kind: Mapped[str] = mapped_column(String(16), default="road")
    is_primary: Mapped[bool] = mapped_column(default=False)

    has_power_meter: Mapped[bool] = mapped_column(default=False)
    has_cadence_sensor: Mapped[bool] = mapped_column(default=False)
    has_speed_sensor: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class Activity(Base):
    """One Garmin ride. `has_*_data` are derived from this activity's own
    parsed FIT records (soft_floyd_core.activities.sensors) — never from
    RiderProfile — and are only meaningful when `fit_status == "ok"`; a
    failed download/parse must not be read as "no sensors on this ride."
    """

    __tablename__ = "activity"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)  # Garmin activityId
    start_time: Mapped[dt.datetime]
    sport: Mapped[str] = mapped_column(String(64), default="")
    sub_sport: Mapped[str] = mapped_column(String(64), default="")
    is_indoor: Mapped[bool] = mapped_column(default=False)
    bike_type: Mapped[str] = mapped_column(String(16), default="other")

    distance_m: Mapped[float] = mapped_column(default=0.0)
    duration_s: Mapped[float] = mapped_column(default=0.0)
    elev_gain_m: Mapped[float] = mapped_column(default=0.0)
    avg_hr: Mapped[int | None] = mapped_column(default=None)
    max_hr: Mapped[int | None] = mapped_column(default=None)
    avg_power_w: Mapped[int | None] = mapped_column(default=None)
    max_power_w: Mapped[int | None] = mapped_column(default=None)
    avg_cadence: Mapped[int | None] = mapped_column(default=None)

    has_power_data: Mapped[bool] = mapped_column(default=False)
    has_hr_data: Mapped[bool] = mapped_column(default=False)
    has_cadence_data: Mapped[bool] = mapped_column(default=False)
    has_speed_data: Mapped[bool] = mapped_column(default=False)
    has_gps_data: Mapped[bool] = mapped_column(default=False)

    fit_status: Mapped[str] = mapped_column(String(16), default="pending")
    fit_path: Mapped[str | None] = mapped_column(default=None)
    record_count: Mapped[int] = mapped_column(default=0)
    records_stored: Mapped[bool] = mapped_column(default=False)
    raw_summary_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    ingested_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)

    laps: Mapped[list[Lap]] = relationship(
        back_populates="activity", cascade="all, delete-orphan", order_by="Lap.lap_index"
    )
    records: Mapped[list[Record]] = relationship(
        back_populates="activity", cascade="all, delete-orphan", order_by="Record.t_offset_s"
    )


class Lap(Base):
    __tablename__ = "lap"
    __table_args__ = (UniqueConstraint("activity_id", "lap_index"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activity.id", ondelete="CASCADE"))
    lap_index: Mapped[int]
    distance_m: Mapped[float] = mapped_column(default=0.0)
    duration_s: Mapped[float] = mapped_column(default=0.0)
    avg_hr: Mapped[int | None] = mapped_column(default=None)
    avg_speed_mps: Mapped[float | None] = mapped_column(default=None)
    avg_power_w: Mapped[int | None] = mapped_column(default=None)
    avg_cadence: Mapped[int | None] = mapped_column(default=None)
    elev_gain_m: Mapped[float] = mapped_column(default=0.0)

    activity: Mapped[Activity] = relationship(back_populates="laps")


class Record(Base):
    __tablename__ = "record"
    __table_args__ = (Index("ix_record_activity_t", "activity_id", "t_offset_s"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activity.id", ondelete="CASCADE"))
    t_offset_s: Mapped[float]
    hr: Mapped[int | None] = mapped_column(default=None)
    speed_mps: Mapped[float | None] = mapped_column(default=None)
    altitude_m: Mapped[float | None] = mapped_column(default=None)
    cadence: Mapped[int | None] = mapped_column(default=None)
    power_w: Mapped[int | None] = mapped_column(default=None)
    lat: Mapped[float | None] = mapped_column(default=None)
    lon: Mapped[float | None] = mapped_column(default=None)

    activity: Mapped[Activity] = relationship(back_populates="records")


class GarminSyncState(Base):
    """Single-row (id=1) durable sync health — not just a cursor.

    Answers "is sync healthy, and why not" for GET /api/sync/garmin/status
    without conflating "Garmin is down" with "the rider has no rides" (see
    docs/RELIABILITY.md). last_error is a human-readable message only —
    never a token, password, or raw upstream response body.
    """

    __tablename__ = "garmin_sync_state"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    last_seen_activity_id: Mapped[int | None] = mapped_column(default=None)
    last_sync_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    last_status: Mapped[str] = mapped_column(String(16), default="never")
    last_error: Mapped[str | None] = mapped_column(default=None)
    consecutive_errors: Mapped[int] = mapped_column(default=0)
    # Set by garmin.login.perform_login on a 429 during `garmin-login`;
    # cleared on a successful login. While in the future, `perform_login`
    # refuses locally without a network call — see exec-plan 0003.
    login_blocked_until: Mapped[dt.datetime | None] = mapped_column(default=None)


class Book(Base):
    """One locally imported PDF; the hash makes repeat imports idempotent."""

    __tablename__ = "book"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str]
    author: Mapped[str | None] = mapped_column(default=None)
    source_name: Mapped[str]
    imported_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)


class BookPassage(Base):
    """A cited, embedded passage from one PDF page."""

    __tablename__ = "book_passage"
    __table_args__ = (Index("ix_book_passage_book_id", "book_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("book.id", ondelete="CASCADE"))
    page_start: Mapped[int]
    page_end: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[bytes] = mapped_column(LargeBinary)


class LLMUsageRecord(Base):
    """One successful paid LLM request, including query embeddings."""

    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)
    model: Mapped[str]
    prompt_tokens: Mapped[int]
    cached_tokens: Mapped[int]
    completion_tokens: Mapped[int]
    cost_usd: Mapped[float]
