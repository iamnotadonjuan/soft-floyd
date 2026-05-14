from __future__ import annotations

import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Activity(Base):
    __tablename__ = "activity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # Garmin activityId
    start_time: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sport: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    sub_sport: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    is_indoor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bike_type: Mapped[str] = mapped_column(String(16), nullable=False, default="other")
    distance_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    duration_s: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    elev_gain_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_hr: Mapped[int | None] = mapped_column(Integer)
    max_hr: Mapped[int | None] = mapped_column(Integer)
    tss_proxy: Mapped[float | None] = mapped_column(Float)
    fit_path: Mapped[str | None] = mapped_column(Text)
    raw_summary_json: Mapped[dict | None] = mapped_column(JSON)
    ingested_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.datetime.now,
    )

    laps: Mapped[list[Lap]] = relationship(
        "Lap", back_populates="activity", cascade="all, delete-orphan"
    )
    records: Mapped[list[Record]] = relationship(
        "Record", back_populates="activity", cascade="all, delete-orphan"
    )
    metrics: Mapped[Metrics | None] = relationship(
        "Metrics", back_populates="activity", uselist=False, cascade="all, delete-orphan"
    )


class Lap(Base):
    __tablename__ = "lap"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("activity.id", ondelete="CASCADE"), nullable=False
    )
    lap_index: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    duration_s: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_hr: Mapped[int | None] = mapped_column(Integer)
    avg_speed: Mapped[float | None] = mapped_column(Float)
    elev_gain_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    gap_speed: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (UniqueConstraint("activity_id", "lap_index"),)

    activity: Mapped[Activity] = relationship("Activity", back_populates="laps")


class Record(Base):
    __tablename__ = "record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("activity.id", ondelete="CASCADE"), nullable=False
    )
    t_offset_s: Mapped[float] = mapped_column(Float, nullable=False)
    hr: Mapped[int | None] = mapped_column(Integer)
    speed_mps: Mapped[float | None] = mapped_column(Float)
    altitude_m: Mapped[float | None] = mapped_column(Float)
    cadence: Mapped[int | None] = mapped_column(Integer)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)

    activity: Mapped[Activity] = relationship("Activity", back_populates="records")


class Metrics(Base):
    __tablename__ = "metrics"

    activity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("activity.id", ondelete="CASCADE"), primary_key=True
    )
    decoupling_pct: Mapped[float | None] = mapped_column(Float)
    hr_drift_pct: Mapped[float | None] = mapped_column(Float)
    time_in_z1: Mapped[float | None] = mapped_column(Float)
    time_in_z2: Mapped[float | None] = mapped_column(Float)
    time_in_z3: Mapped[float | None] = mapped_column(Float)
    time_in_z4: Mapped[float | None] = mapped_column(Float)
    time_in_z5: Mapped[float | None] = mapped_column(Float)
    vam_best_20min: Mapped[float | None] = mapped_column(Float)
    gap_normalized: Mapped[float | None] = mapped_column(Float)

    activity: Mapped[Activity] = relationship("Activity", back_populates="metrics")


class WellnessDaily(Base):
    __tablename__ = "wellness_daily"

    date: Mapped[datetime.date] = mapped_column(DateTime, primary_key=True)
    hrv_overnight: Mapped[float | None] = mapped_column(Float)
    sleep_score: Mapped[int | None] = mapped_column(Integer)
    body_battery_low: Mapped[int | None] = mapped_column(Integer)
    body_battery_high: Mapped[int | None] = mapped_column(Integer)
    resting_hr: Mapped[int | None] = mapped_column(Integer)
    acute_load: Mapped[float | None] = mapped_column(Float)
    chronic_load: Mapped[float | None] = mapped_column(Float)
    acwr: Mapped[float | None] = mapped_column(Float)


class PollCursor(Base):
    __tablename__ = "poll_cursor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_seen_activity_id: Mapped[int | None] = mapped_column(Integer)
    last_poll_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    last_poll_status: Mapped[str | None] = mapped_column(String(32))


class GarthToken(Base):
    __tablename__ = "garth_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    encrypted_blob: Mapped[bytes] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.datetime.now,
    )


class Embedding(Base):
    """One text chunk + its vector (vector stored in embedding_vec via rowid)."""

    __tablename__ = "embedding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("activity.id", ondelete="CASCADE"), nullable=True
    )
    chunk_type: Mapped[str] = mapped_column(String(16), nullable=False)  # summary|lap|wellness
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.datetime.now,
    )


class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("activity.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.datetime.now,
    )

    messages: Mapped[list[Message]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.id",
    )


class Message(Base):
    __tablename__ = "message"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user|assistant
    content_json: Mapped[dict | list | None] = mapped_column(JSON)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    cache_read: Mapped[int | None] = mapped_column(Integer)
    cache_write: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.datetime.now,
    )

    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="messages")
