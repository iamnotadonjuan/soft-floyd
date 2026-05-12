from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from coach.ingest.fit_parser import ParsedFit

BikeType = Literal["road", "mtb", "indoor", "other"]

_MTB_SUB_SPORTS = {"mountain", "gravel_cycling", "cyclocross"}
# fitdecode returns 'virtual_activity' for FIT sub_sport=58; Garmin API uses 'virtual_ride'
_ROAD_SUB_SPORTS = {"road", "virtual_ride", "virtual_activity"}


def classify(activity_summary: dict, parsed_fit: ParsedFit) -> BikeType:
    """Classify bike type using rules in strict priority order (PLAN.md §1.6)."""
    is_indoor: bool = activity_summary.get("is_indoor", False) or parsed_fit.session.is_indoor

    # Rule 1: indoor flag
    if is_indoor:
        return "indoor"

    sub_sport = (parsed_fit.session.sub_sport or "").lower().replace(" ", "_")

    # Rule 2: MTB sub-sports
    if sub_sport in _MTB_SUB_SPORTS:
        return "mtb"

    # Rule 3: road / virtual
    if sub_sport in _ROAD_SUB_SPORTS:
        if sub_sport in {"virtual_ride", "virtual_activity"}:
            has_gps = any(r.lat is not None for r in parsed_fit.records)
            return "road" if has_gps else "indoor"
        return "road"

    # Rule 4: heuristic
    distance_m = parsed_fit.session.total_distance_m
    elev_gain_m = parsed_fit.session.total_ascent_m
    duration_s = parsed_fit.session.total_elapsed_s

    if duration_s > 0:
        avg_speed_kmh = (distance_m / duration_s) * 3.6
        elev_gain_per_km = (elev_gain_m / distance_m * 1000.0) if distance_m > 0 else 0.0

        if avg_speed_kmh > 22.0 and elev_gain_per_km < 15.0:
            return "road"
        elif avg_speed_kmh > 0:
            return "mtb"

    return "other"
