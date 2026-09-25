"""Rider profile CRUD plus the sensor capability model.

This module is the single place that decides what the coach may compute.
Both the MCP tools and the REST routes call these functions directly —
neither adapter re-implements the tier logic. See
docs/design-docs/sensor-capability-model.md for the rules this encodes.

Bike-mounted sensors (power/cadence/speed) live on Bike, not RiderProfile
(exec-plan 0004) — capability_tier() unions RiderProfile.has_hr_monitor
with every Bike's sensors, so the four `has_*` fields and
`primary_discipline` on ProfileOut are *derived*, not stored. Writes to
those fields go through bikes/service.py instead; ProfileIn no longer
accepts them.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from soft_floyd_core.account_scope import account_id
from soft_floyd_core.models import Bike, RiderProfile

CapabilityTier = Literal["power", "hr", "cadence", "basic"]

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


def _tier_from_flags(
    *, has_power: bool, has_hr: bool, has_cadence_or_speed: bool
) -> CapabilityTier:
    """Shared priority order: power > hr > cadence/speed > basic. Gaining a
    sensor only ever adds metrics — see
    test_power_tier_still_includes_hr_metrics.
    """
    if has_power:
        return "power"
    if has_hr:
        return "hr"
    if has_cadence_or_speed:
        return "cadence"
    return "basic"


def capability_tier(profile: RiderProfile, bikes: list[Bike]) -> CapabilityTier:
    """Derive the coaching tier from declared hardware across the whole
    garage, unioned with the rider's body-worn HR monitor.

    This reads *declared* sensors — the planning signal. Per-activity
    analysis must additionally check the FIT stream for that ride before
    using a metric; a profile/bike flag means "usually available," not
    "present in this ride." See design-docs/sensor-capability-model.md
    rule 1. `ftp_watts`/`lthr` are anchors, never gates — rule 3.
    """
    return _tier_from_flags(
        has_power=any(b.has_power_meter for b in bikes),
        has_hr=profile.has_hr_monitor,
        has_cadence_or_speed=any(b.has_cadence_sensor or b.has_speed_sensor for b in bikes),
    )


def capability_tier_for_bike(bike: Bike, profile: RiderProfile) -> CapabilityTier:
    """The tier for a ride on this one bike specifically — its own
    power/cadence/speed sensors, plus the rider's body-worn HR monitor
    (the strap comes along regardless of which bike is ridden). Lets the
    coach say "power on the road bike, heart rate only on the MTB" rather
    than collapsing the whole garage into one number — core belief 4.
    """
    return _tier_from_flags(
        has_power=bike.has_power_meter,
        has_hr=profile.has_hr_monitor,
        has_cadence_or_speed=bike.has_cadence_sensor or bike.has_speed_sensor,
    )


def available_metrics(tier: CapabilityTier) -> list[str]:
    return list(METRICS_BY_TIER[tier])


class ProfileIn(BaseModel):
    """Partial update payload — unset fields are left untouched.

    No has_power_meter/has_cadence_sensor/has_speed_sensor/
    primary_discipline here — those are derived from the garage; update
    them via the bikes endpoints (bikes/service.py), not this one.
    extra="forbid" so a client that still sends one of those four gets a
    clear 422 instead of the value being silently dropped.
    """

    model_config = ConfigDict(extra="forbid")

    # Legacy callers may still send this when no usual days have been set.
    # Once available_days is supplied, its distinct day count wins.
    weekly_rides: int | None = None
    weekly_hours: float | None = None
    goal_text: str | None = None
    target_event_name: str | None = None
    target_event_date: dt.date | None = None
    focus_areas: list[str] | None = None

    years_riding: float | None = None
    longest_recent_ride_km: float | None = None
    followed_plan_before: bool | None = None
    self_rated_level: Literal["beginner", "recreational", "enthusiast", "competitive"] | None = None

    available_days: list[str] | None = None
    weekday_max_minutes: int | None = None
    weekend_max_minutes: int | None = None

    birth_year: int | None = None
    weight_kg: float | None = None
    max_hr: int | None = None
    health_notes: str | None = None

    has_hr_monitor: bool | None = None
    ftp_watts: int | None = None
    lthr: int | None = None


class ProfileOut(BaseModel):
    weekly_rides: int
    weekly_hours: float
    goal_text: str
    target_event_name: str | None
    target_event_date: dt.date | None
    focus_areas: list[str]

    years_riding: float | None
    longest_recent_ride_km: float | None
    followed_plan_before: bool | None
    self_rated_level: str | None

    available_days: list[str]
    weekday_max_minutes: int | None
    weekend_max_minutes: int | None

    birth_year: int | None
    weight_kg: float | None
    max_hr: int | None
    health_notes: str | None

    has_hr_monitor: bool
    ftp_watts: int | None
    lthr: int | None

    # Derived from the garage — see module docstring. Kept under these
    # field names for backward compatibility with every consumer written
    # against the pre-0004 flat profile (available_metrics_for_activity,
    # the MCP tools, CapabilitySummary.tsx).
    has_power_meter: bool
    has_cadence_sensor: bool
    has_speed_sensor: bool
    primary_discipline: str | None

    capability_tier: CapabilityTier
    available_metrics: list[str]


def _to_out(profile: RiderProfile, bikes: list[Bike]) -> ProfileOut:
    tier = capability_tier(profile, bikes)
    primary = next((b for b in bikes if b.is_primary), bikes[0] if bikes else None)
    return ProfileOut(
        weekly_rides=profile.weekly_rides,
        weekly_hours=profile.weekly_hours,
        goal_text=profile.goal_text,
        target_event_name=profile.target_event_name,
        target_event_date=profile.target_event_date,
        focus_areas=list(profile.focus_areas or []),
        years_riding=profile.years_riding,
        longest_recent_ride_km=profile.longest_recent_ride_km,
        followed_plan_before=profile.followed_plan_before,
        self_rated_level=profile.self_rated_level,
        available_days=list(profile.available_days or []),
        weekday_max_minutes=profile.weekday_max_minutes,
        weekend_max_minutes=profile.weekend_max_minutes,
        birth_year=profile.birth_year,
        weight_kg=profile.weight_kg,
        max_hr=profile.max_hr,
        health_notes=profile.health_notes,
        has_hr_monitor=profile.has_hr_monitor,
        ftp_watts=profile.ftp_watts,
        lthr=profile.lthr,
        has_power_meter=any(b.has_power_meter for b in bikes),
        has_cadence_sensor=any(b.has_cadence_sensor for b in bikes),
        has_speed_sensor=any(b.has_speed_sensor for b in bikes),
        primary_discipline=primary.kind if primary is not None else None,
        capability_tier=tier,
        available_metrics=available_metrics(tier),
    )


def get_or_create_profile(session: Session) -> RiderProfile:
    """Public: bikes/service.py also needs the raw RiderProfile row (for
    its has_hr_monitor flag, to compute a per-bike tier) without going
    through the ProfileOut serialization here.
    """
    owner = account_id(session)
    profile = session.scalar(select(RiderProfile).where(RiderProfile.account_id == owner))
    if profile is None:
        profile = RiderProfile(account_id=owner)
        session.add(profile)
        session.flush()
    return profile


def _list_bikes(session: Session) -> list[Bike]:
    return list(session.scalars(select(Bike).order_by(Bike.id)).all())


def get_profile(session: Session) -> ProfileOut:
    return _to_out(get_or_create_profile(session), _list_bikes(session))


def upsert_profile(session: Session, data: ProfileIn) -> ProfileOut:
    profile = get_or_create_profile(session)
    changes = data.model_dump(exclude_unset=True)
    if "available_days" in changes and changes["available_days"] is not None:
        # The selected usual riding days are the source of truth for this
        # count. Preserve legacy weekly_rides-only updates until days have
        # been selected for the first time.
        changes["available_days"] = list(dict.fromkeys(changes["available_days"]))
        changes["weekly_rides"] = len(changes["available_days"])
    elif profile.available_days and "weekly_rides" in changes:
        del changes["weekly_rides"]
    for field, value in changes.items():
        setattr(profile, field, value)
    session.flush()
    return _to_out(profile, _list_bikes(session))
