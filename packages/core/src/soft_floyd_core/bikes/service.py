"""The rider's garage: CRUD over Bike plus the "exactly one primary bike"
invariant. Both the MCP tools and the REST routes call these functions
directly — same rule as profile/service.py. See
docs/design-docs/sensor-capability-model.md for why bike-mounted sensors
live here rather than on RiderProfile.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from soft_floyd_core.models import Bike
from soft_floyd_core.profile.service import (
    CapabilityTier,
    capability_tier_for_bike,
    get_or_create_profile,
)


class BikeIn(BaseModel):
    """Partial update payload — unset fields are left untouched, same
    convention as ProfileIn. is_primary is settable here; setting it True
    demotes every other bike in the same call (see update_bike).
    """

    nickname: str | None = None
    kind: str | None = None
    is_primary: bool | None = None
    has_power_meter: bool | None = None
    has_cadence_sensor: bool | None = None
    has_speed_sensor: bool | None = None


class BikeOut(BaseModel):
    id: int
    nickname: str
    kind: str
    is_primary: bool
    has_power_meter: bool
    has_cadence_sensor: bool
    has_speed_sensor: bool
    capability_tier: CapabilityTier


def _to_out(bike: Bike, tier: CapabilityTier) -> BikeOut:
    return BikeOut(
        id=bike.id,
        nickname=bike.nickname,
        kind=bike.kind,
        is_primary=bike.is_primary,
        has_power_meter=bike.has_power_meter,
        has_cadence_sensor=bike.has_cadence_sensor,
        has_speed_sensor=bike.has_speed_sensor,
        capability_tier=tier,
    )


def _bike_out(session: Session, bike: Bike) -> BikeOut:
    profile = get_or_create_profile(session)
    return _to_out(bike, capability_tier_for_bike(bike, profile))


def list_bikes(session: Session) -> list[BikeOut]:
    profile = get_or_create_profile(session)
    bikes = session.scalars(select(Bike).order_by(Bike.id)).all()
    return [_to_out(b, capability_tier_for_bike(b, profile)) for b in bikes]


def _demote_other_bikes(session: Session, *, except_id: int | None) -> None:
    stmt = select(Bike).where(Bike.is_primary.is_(True))
    if except_id is not None:
        stmt = stmt.where(Bike.id != except_id)
    for other in session.scalars(stmt).all():
        other.is_primary = False


def add_bike(session: Session, data: BikeIn) -> BikeOut:
    """The very first bike a rider adds is always primary, regardless of
    what the request says — onboarding's GarageStep never has to think
    about the invariant for the common case of "I have one bike."
    """
    is_first = session.scalar(select(Bike.id).limit(1)) is None
    bike = Bike(
        nickname=data.nickname or "",
        kind=data.kind or "road",
        is_primary=True if is_first else bool(data.is_primary),
    )
    if data.has_power_meter is not None:
        bike.has_power_meter = data.has_power_meter
    if data.has_cadence_sensor is not None:
        bike.has_cadence_sensor = data.has_cadence_sensor
    if data.has_speed_sensor is not None:
        bike.has_speed_sensor = data.has_speed_sensor
    session.add(bike)
    session.flush()
    if bike.is_primary:
        _demote_other_bikes(session, except_id=bike.id)
    session.flush()
    return _bike_out(session, bike)


class BikeNotFoundError(Exception):
    pass


class LastBikeError(Exception):
    """Raised when a delete would leave the rider with zero bikes — never
    ask the coach to reason about a garage with nothing in it.
    """


def _get_bike(session: Session, bike_id: int) -> Bike:
    bike = session.get(Bike, bike_id)
    if bike is None:
        raise BikeNotFoundError(f"No bike with id {bike_id}")
    return bike


def update_bike(session: Session, bike_id: int, data: BikeIn) -> BikeOut:
    bike = _get_bike(session, bike_id)
    updates = data.model_dump(exclude_unset=True, exclude={"is_primary"})
    for field, value in updates.items():
        setattr(bike, field, value)
    bike.updated_at = dt.datetime.now(dt.UTC)

    if data.is_primary is True:
        bike.is_primary = True
        _demote_other_bikes(session, except_id=bike.id)
    elif data.is_primary is False and bike.is_primary:
        # Refuse to leave the garage with zero primaries — demoting the
        # current primary with no replacement named is almost certainly
        # not what a settings-screen click meant.
        raise ValueError("Cannot unset the only primary bike; set another bike as primary instead.")

    session.flush()
    return _bike_out(session, bike)


def delete_bike(session: Session, bike_id: int) -> None:
    bike = _get_bike(session, bike_id)
    remaining = list(session.scalars(select(Bike).where(Bike.id != bike_id)).all())
    if not remaining:
        raise LastBikeError("Cannot delete the only bike in the garage.")

    session.delete(bike)
    session.flush()

    if bike.is_primary and not any(b.is_primary for b in remaining):
        # Promote deterministically (oldest remaining bike) rather than
        # leaving the garage with no primary at all.
        promoted = min(remaining, key=lambda b: b.id)
        promoted.is_primary = True
        session.flush()
