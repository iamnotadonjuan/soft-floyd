"""Build a concise rider-profile string for prompt injection."""

from __future__ import annotations

from sqlalchemy.orm import Session

from coach.store.models import RiderProfile

_GOAL_LABELS: dict[str, str] = {
    "climbing": "climbing",
    "descending": "descending/technical terrain",
    "endurance": "endurance",
    "sprinting": "sprinting",
    "intervals": "structured intervals",
    "recovery": "base/recovery",
}


def build_profile_summary(session: Session) -> str | None:
    """Return a one-paragraph profile string, or None if no profile is set."""
    row = session.get(RiderProfile, 1)
    if row is None:
        return None

    parts: list[str] = [f"Discipline: {row.discipline}."]

    if row.city:
        loc = row.city
        if row.country:
            loc += f", {row.country}"
        parts.append(f"Trains in {loc}.")

    if row.terrain_notes:
        parts.append(f"Terrain: {row.terrain_notes}.")

    if row.goals:
        goal_labels = [_GOAL_LABELS.get(g, g) for g in row.goals]
        parts.append(f"Training goals: {', '.join(goal_labels)}.")

    if row.freeform_notes:
        parts.append(f"Notes: {row.freeform_notes}.")

    return " ".join(parts)
