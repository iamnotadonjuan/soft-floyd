"""Read-only OpenAI tool schemas and executor for CoachSession."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from coach.store.models import Activity, Lap, Metrics, WellnessDaily

if TYPE_CHECKING:
    pass

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "fetch_ride_detail",
            "description": (
                "Get full lap breakdown and computed metrics for a specific activity. "
                "Use when the rider asks about a particular past ride not already in context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "activity_id": {
                        "type": "integer",
                        "description": "Garmin activity ID",
                    }
                },
                "required": ["activity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_to_ride",
            "description": (
                "Compare two activities side-by-side: HR metrics, duration, distance, zone distribution."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "activity_id_a": {"type": "integer", "description": "First activity ID"},
                    "activity_id_b": {"type": "integer", "description": "Second activity ID"},
                },
                "required": ["activity_id_a", "activity_id_b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_load",
            "description": (
                "Return ACWR and per-day TRIMP for the past N days. Useful for assessing training load."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default 28)",
                        "default": 28,
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_wellness_window",
            "description": "Return HRV, sleep score, and resting HR for the past N days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default 14)",
                        "default": 14,
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_similar_routes",
            "description": (
                "Find past activities with similar distance and bike type. "
                "Useful for route-level comparisons."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "activity_id": {
                        "type": "integer",
                        "description": "Reference activity ID",
                    }
                },
                "required": ["activity_id"],
            },
        },
    },
]


def _activity_dict(activity: Activity | None) -> dict | None:
    if activity is None:
        return None
    return {
        "id": activity.id,
        "date": activity.start_time.strftime("%Y-%m-%d"),
        "bike_type": activity.bike_type,
        "distance_km": round(activity.distance_m / 1000, 2),
        "duration_min": round(activity.duration_s / 60, 1),
        "elev_gain_m": round(activity.elev_gain_m),
        "avg_hr": activity.avg_hr,
        "max_hr": activity.max_hr,
        "tss_proxy": round(activity.tss_proxy, 1) if activity.tss_proxy else None,
    }


def _metrics_dict(metrics: Metrics | None) -> dict:
    if metrics is None:
        return {}
    return {
        "decoupling_pct": metrics.decoupling_pct,
        "hr_drift_pct": metrics.hr_drift_pct,
        "time_in_z1_min": round((metrics.time_in_z1 or 0) / 60, 1),
        "time_in_z2_min": round((metrics.time_in_z2 or 0) / 60, 1),
        "time_in_z3_min": round((metrics.time_in_z3 or 0) / 60, 1),
        "time_in_z4_min": round((metrics.time_in_z4 or 0) / 60, 1),
        "time_in_z5_min": round((metrics.time_in_z5 or 0) / 60, 1),
        "vam_best_20min": metrics.vam_best_20min,
        "gap_normalized_mps": metrics.gap_normalized,
    }


def execute_tool(session: Session, name: str, inputs: dict[str, Any]) -> dict:
    if name == "fetch_ride_detail":
        return _fetch_ride_detail(session, inputs["activity_id"])
    if name == "compare_to_ride":
        return _compare_to_ride(session, inputs["activity_id_a"], inputs["activity_id_b"])
    if name == "get_recent_load":
        return _get_recent_load(session, inputs.get("days", 28))
    if name == "get_wellness_window":
        return _get_wellness_window(session, inputs.get("days", 14))
    if name == "find_similar_routes":
        return _find_similar_routes(session, inputs["activity_id"])
    return {"error": f"Unknown tool: {name}"}


def _fetch_ride_detail(session: Session, activity_id: int) -> dict:
    activity = session.get(Activity, activity_id)
    if activity is None:
        return {"error": f"Activity {activity_id} not found"}
    metrics = session.get(Metrics, activity_id)
    laps = list(
        session.execute(
            select(Lap).where(Lap.activity_id == activity_id).order_by(Lap.lap_index)
        ).scalars()
    )
    return {
        "activity": _activity_dict(activity),
        "metrics": _metrics_dict(metrics),
        "laps": [
            {
                "lap_index": lap.lap_index,
                "distance_km": round(lap.distance_m / 1000, 2),
                "duration_min": round(lap.duration_s / 60, 1),
                "avg_hr": lap.avg_hr,
                "elev_gain_m": round(lap.elev_gain_m),
            }
            for lap in laps
        ],
    }


def _compare_to_ride(session: Session, id_a: int, id_b: int) -> dict:
    def _get(aid: int) -> dict:
        act = session.get(Activity, aid)
        if act is None:
            return {"error": f"Activity {aid} not found"}
        m = session.get(Metrics, aid)
        return {**(_activity_dict(act) or {}), **_metrics_dict(m)}

    return {"ride_a": _get(id_a), "ride_b": _get(id_b)}


def _get_recent_load(session: Session, days: int) -> dict:
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)
    activities = list(
        session.execute(
            select(Activity).where(Activity.start_time >= cutoff).order_by(Activity.start_time)
        ).scalars()
    )
    daily_trimp: dict[str, float] = {}
    for a in activities:
        key = a.start_time.strftime("%Y-%m-%d")
        daily_trimp[key] = daily_trimp.get(key, 0.0) + (a.tss_proxy or 0.0)

    # Simple ACWR: acute = 7-day sum / 7, chronic = 28-day sum / 28 (annualised)
    recent_7 = [
        v
        for k, v in daily_trimp.items()
        if datetime.datetime.strptime(k, "%Y-%m-%d").replace(tzinfo=datetime.UTC)
        >= datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=7)
    ]
    all_vals = list(daily_trimp.values())
    acute = sum(recent_7) / 7 if recent_7 else 0
    chronic = sum(all_vals) / days if all_vals else 0
    acwr = round(acute / chronic, 2) if chronic > 0 else None

    return {
        "days_requested": days,
        "acwr": acwr,
        "acute_load_7d": round(acute, 1),
        "chronic_load": round(chronic, 1),
        "daily_trimp": daily_trimp,
    }


def _get_wellness_window(session: Session, days: int) -> dict:
    cutoff = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)).date()
    rows = list(
        session.execute(
            select(WellnessDaily).where(WellnessDaily.date >= cutoff).order_by(WellnessDaily.date)
        ).scalars()
    )
    return {
        "days_requested": days,
        "entries": [
            {
                "date": str(w.date),
                "hrv_overnight": w.hrv_overnight,
                "sleep_score": w.sleep_score,
                "body_battery_low": w.body_battery_low,
                "body_battery_high": w.body_battery_high,
                "resting_hr": w.resting_hr,
                "acwr": w.acwr,
            }
            for w in rows
        ],
    }


def _find_similar_routes(session: Session, activity_id: int) -> dict:
    activity = session.get(Activity, activity_id)
    if activity is None:
        return {"error": f"Activity {activity_id} not found"}

    low = activity.distance_m * 0.80
    high = activity.distance_m * 1.20

    similar = list(
        session.execute(
            select(Activity)
            .where(
                Activity.bike_type == activity.bike_type,
                Activity.distance_m.between(low, high),
                Activity.id != activity_id,
            )
            .order_by(Activity.start_time.desc())
            .limit(5)
        ).scalars()
    )
    return {
        "reference_activity_id": activity_id,
        "similar_activities": [_activity_dict(a) for a in similar],
    }
