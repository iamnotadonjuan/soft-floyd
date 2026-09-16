"""SQLAlchemy 2.x typed models.

Scaffold ships one table: RiderProfile. See
docs/design-docs/sensor-capability-model.md for why it carries sensor flags
alongside training volume and goals.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

Discipline = Literal["road", "mtb"]


class Base(DeclarativeBase):
    pass


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class RiderProfile(Base):
    """Single-row table: this app coaches one rider.

    Sensor flags declare what hardware the rider has; capability_tier()
    in profile/service.py derives what the coach may compute from them.
    Per-activity analysis must still check the actual FIT stream — a
    flag here means "usually available," not "present in this ride."
    """

    __tablename__ = "rider_profile"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)

    # Volume + goals
    weekly_rides: Mapped[int] = mapped_column(default=0)
    weekly_hours: Mapped[float] = mapped_column(default=0.0)
    primary_discipline: Mapped[str] = mapped_column(String(16), default="road")
    goal_text: Mapped[str] = mapped_column(default="")
    target_event_date: Mapped[dt.date | None] = mapped_column(default=None)

    # Sensors — what the rider actually rides with
    has_power_meter: Mapped[bool] = mapped_column(default=False)
    has_hr_monitor: Mapped[bool] = mapped_column(default=True)
    has_cadence_sensor: Mapped[bool] = mapped_column(default=False)
    has_speed_sensor: Mapped[bool] = mapped_column(default=False)

    # Anchors — only meaningful alongside the matching sensor flag
    ftp_watts: Mapped[int | None] = mapped_column(default=None)
    lthr: Mapped[int | None] = mapped_column(default=None)

    created_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)
