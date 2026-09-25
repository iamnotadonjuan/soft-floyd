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


class Account(Base):
    __tablename__ = "account"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str]
    name: Mapped[str]
    picture_url: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)


class AuthSession(Base):
    __tablename__ = "auth_session"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"))
    expires_at: Mapped[dt.datetime]
    revoked_at: Mapped[dt.datetime | None] = mapped_column(default=None)


class RiderProfile(Base):
    """One row per account for the rider's training profile.

    Bike-mounted sensors (power/cadence/speed) live on Bike, not here —
    exec-plan 0004. has_hr_monitor stays here because a strap is
    body-worn, not bike-mounted. profile/service.py's capability_tier()
    unions this profile's HR flag with every Bike's sensors to derive
    what the coach may compute; per-activity analysis must still check
    the actual FIT stream — a flag here means "usually available," not
    "present in this ride."
    """

    __tablename__ = "rider_profile"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), unique=True)

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
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), index=True)
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

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), index=True)
    garmin_id: Mapped[int] = mapped_column()
    __table_args__ = (UniqueConstraint("account_id", "garmin_id"),)
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
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), index=True)
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
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), index=True)
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
    """One row per account for durable sync health — not just a cursor.

    Answers "is sync healthy, and why not" for GET /api/sync/garmin/status
    without conflating "Garmin is down" with "the rider has no rides" (see
    docs/RELIABILITY.md). last_error is a human-readable message only —
    never a token, password, or raw upstream response body.
    """

    __tablename__ = "garmin_sync_state"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), unique=True)
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
    import_status: Mapped[str] = mapped_column(default="complete", server_default="complete")


class BookPassage(Base):
    """A cited, embedded passage from one PDF page."""

    __tablename__ = "book_passage"
    __table_args__ = (
        Index("ix_book_passage_book_id", "book_id"),
        Index("ix_book_passage_book_ordinal", "book_id", "ordinal", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("book.id", ondelete="CASCADE"))
    ordinal: Mapped[int | None] = mapped_column(default=None)
    page_start: Mapped[int]
    page_end: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[bytes] = mapped_column(LargeBinary)


class LLMUsageRecord(Base):
    """One successful paid LLM request, including query embeddings."""

    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("account.id"), default=None)
    occurred_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)
    model: Mapped[str]
    prompt_tokens: Mapped[int]
    cached_tokens: Mapped[int]
    completion_tokens: Mapped[int]
    cost_usd: Mapped[float]


class CoachConversation(Base):
    """One coach chat thread (exec-plan 0007). Title is the first user
    message, truncated — no extra LLM call to name it."""

    __tablename__ = "coach_conversation"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), index=True)
    title: Mapped[str] = mapped_column(String(120), default="New conversation")
    created_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)

    messages: Mapped[list[CoachMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="CoachMessage.id",
    )


class CoachMessage(Base):
    """A user or assistant turn. Tool traffic is not persisted — each turn
    rebuilds it from live data, so stale ride numbers never replay."""

    __tablename__ = "coach_message"
    __table_args__ = (Index("ix_coach_message_conversation_id", "conversation_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), index=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("coach_conversation.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(16))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    # Book citations shown under an assistant reply: [{title, page_start, ...}]
    sources: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)

    conversation: Mapped[CoachConversation] = relationship(back_populates="messages")


class CoachMemoryNote(Base):
    """A durable fact the coach saved about the rider (injury, preference,
    constraint). Injected into every coach turn; the rider can delete any."""

    __tablename__ = "coach_memory_note"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), index=True)
    text: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)
