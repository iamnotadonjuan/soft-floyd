"""Rider profile CRUD plus the sensor capability model.

This module is the single place that decides what the coach may compute.
Both the MCP tools and the REST routes call these functions directly —
neither adapter re-implements the tier logic. See
docs/design-docs/sensor-capability-model.md for the rules this encodes.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from soft_floyd_core.models import RiderProfile

CapabilityTier = Literal["power", "hr", "cadence", "basic"]

# Single-rider app: the profile is always row id 1.
PROFILE_ROW_ID = 1

# Metric name -> which tier(s) may show it. Order is display order, not priority.
# HR-derived metrics stay available at the "power" tier because a power meter
# rider still (almost always) wears a strap; nothing here is ever removed by
# gaining a sensor, only added.
METRICS_BY_TIER: dict[CapabilityTier, list[str]] = {
    "power": [
        "ftp",
        "normalized_power",
        "intensity_factor",
        "training_stress_score",
        "power_curve",
        "hr_zones",
        "hr_drift",
        "decoupling",
        "trimp",
        "gap",
        "vam",
    ],
    "hr": ["hr_zones", "hr_drift", "decoupling", "trimp", "gap", "vam"],
    "cadence": ["cadence_distribution", "duration", "distance", "elevation_gain"],
    "basic": ["duration", "distance", "elevation_gain", "avg_speed"],
}


def capability_tier(profile: RiderProfile) -> CapabilityTier:
    """Derive the coaching tier from declared hardware.

    This reads the *profile's* declared sensors — the planning signal.
    Per-activity analysis must additionally check the FIT stream for that
    ride before using a metric; a profile flag means "usually available,"
    not "present in this ride." See design-docs/sensor-capability-model.md
    rule 1.
    """
    if profile.has_power_meter:
        return "power"
    if profile.has_hr_monitor:
        return "hr"
    if profile.has_cadence_sensor or profile.has_speed_sensor:
        return "cadence"
    return "basic"


def available_metrics(tier: CapabilityTier) -> list[str]:
    return list(METRICS_BY_TIER[tier])


class ProfileIn(BaseModel):
    """Partial update payload — unset fields are left untouched."""

    weekly_rides: int | None = None
    weekly_hours: float | None = None
    primary_discipline: Literal["road", "mtb"] | None = None
    goal_text: str | None = None
    target_event_date: dt.date | None = None
    has_power_meter: bool | None = None
    has_hr_monitor: bool | None = None
    has_cadence_sensor: bool | None = None
    has_speed_sensor: bool | None = None
    ftp_watts: int | None = None
    lthr: int | None = None


class ProfileOut(BaseModel):
    weekly_rides: int
    weekly_hours: float
    primary_discipline: str
    goal_text: str
    target_event_date: dt.date | None
    has_power_meter: bool
    has_hr_monitor: bool
    has_cadence_sensor: bool
    has_speed_sensor: bool
    ftp_watts: int | None
    lthr: int | None
    capability_tier: CapabilityTier
    available_metrics: list[str]


def _to_out(profile: RiderProfile) -> ProfileOut:
    tier = capability_tier(profile)
    return ProfileOut(
        weekly_rides=profile.weekly_rides,
        weekly_hours=profile.weekly_hours,
        primary_discipline=profile.primary_discipline,
        goal_text=profile.goal_text,
        target_event_date=profile.target_event_date,
        has_power_meter=profile.has_power_meter,
        has_hr_monitor=profile.has_hr_monitor,
        has_cadence_sensor=profile.has_cadence_sensor,
        has_speed_sensor=profile.has_speed_sensor,
        ftp_watts=profile.ftp_watts,
        lthr=profile.lthr,
        capability_tier=tier,
        available_metrics=available_metrics(tier),
    )


def _get_or_create(session: Session) -> RiderProfile:
    profile = session.get(RiderProfile, PROFILE_ROW_ID)
    if profile is None:
        profile = RiderProfile(id=PROFILE_ROW_ID)
        session.add(profile)
        session.flush()
    return profile


def get_profile(session: Session) -> ProfileOut:
    return _to_out(_get_or_create(session))


def upsert_profile(session: Session, data: ProfileIn) -> ProfileOut:
    profile = _get_or_create(session)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    session.flush()
    return _to_out(profile)
