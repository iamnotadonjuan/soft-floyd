"""The coach's function-calling tools.

Each tool is a thin call into an existing core function — the same ones
the MCP tools and REST routes use — so the coach sees exactly the data
every other surface sees. Ride data always goes through
`rag.service.ride_context`, which applies the per-ride sensor gate; the
coach never gets a raw Garmin HR/power number the FIT data didn't verify.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from soft_floyd_core.activities import service as activities_service
from soft_floyd_core.bikes import service as bikes_service
from soft_floyd_core.coach import memory
from soft_floyd_core.models import Activity, Lap
from soft_floyd_core.profile import service as profile_service
from soft_floyd_core.rag import service as rag_service


class SourceOut(BaseModel):
    book_id: int
    title: str
    author: str | None
    page_start: int
    page_end: int


@dataclass
class ToolResult:
    content: str  # JSON handed back to the model
    status: str  # short progress label shown to the rider
    sources: list[SourceOut] = field(default_factory=list)


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


TOOLS: list[dict[str, Any]] = [
    _fn(
        "get_rider_profile",
        "The rider's goals, target event, availability, experience, body data, bikes, "
        "capability tier and the metrics their hardware supports.",
        {},
        [],
    ),
    _fn(
        "get_training_summary",
        "Weekly ride count, distance, time and elevation for recent weeks, with HR/power "
        "averages only where the rides' own data verified them.",
        {"weeks": {"type": "integer", "description": "Weeks to cover, 1-26. Default 8."}},
        [],
    ),
    _fn(
        "list_recent_rides",
        "The rider's most recent rides (newest first) with sensor-verified metrics.",
        {
            "limit": {"type": "integer", "description": "1-30. Default 10."},
            "bike_type": {
                "type": ["string", "null"],
                "enum": ["road", "mtb", "indoor", "other", None],
                "description": "Optional filter.",
            },
        },
        [],
    ),
    _fn(
        "get_ride",
        "One ride in detail, including laps and the metrics allowed for that ride.",
        {"activity_id": {"type": "integer"}},
        ["activity_id"],
    ),
    _fn(
        "search_training_books",
        "Search the rider's imported training books for passages relevant to a question. "
        "Cite the book title and page when you use a passage.",
        {"query": {"type": "string", "description": "A focused training question."}},
        ["query"],
    ),
    _fn(
        "remember",
        "Save one short, durable fact about the rider for future coaching.",
        {"note": {"type": "string", "description": f"At most {memory.MAX_NOTE_CHARS} chars."}},
        ["note"],
    ),
    _fn(
        "forget",
        "Delete a saved memory note that is wrong or no longer true.",
        {"note_id": {"type": "integer"}},
        ["note_id"],
    ),
]


def _json(value: Any) -> str:
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    return json.dumps(value, default=str)


def _profile(session: Session) -> ToolResult:
    profile = profile_service.get_profile(session)
    bikes = bikes_service.list_bikes(session)
    payload = {
        "profile": profile.model_dump(mode="json"),
        "bikes": [b.model_dump(mode="json") for b in bikes],
    }
    return ToolResult(_json(payload), "Reading your profile")


def _recent_rides(session: Session, limit: int, bike_type: str | None) -> ToolResult:
    limit = max(1, min(limit, 30))
    stmt = select(Activity).order_by(Activity.start_time.desc(), Activity.id.desc()).limit(limit)
    if bike_type:
        stmt = stmt.where(Activity.bike_type == bike_type)
    rides = [rag_service.ride_context(session, a) for a in session.scalars(stmt).all()]
    payload = {"rides": [r.model_dump(mode="json") for r in rides]}
    if not rides:
        payload["note"] = "No synced rides yet."
    return ToolResult(_json(payload), f"Looking at your last {limit} rides")


def _ride(session: Session, activity_id: int) -> ToolResult:
    activity = session.get(Activity, activity_id)
    if activity is None:
        return ToolResult(_json({"error": f"Ride {activity_id} not found"}), "Opening a ride")
    context = rag_service.ride_context(session, activity)
    hr_ok = context.avg_hr is not None
    power_ok = context.avg_power_w is not None
    cadence_ok = context.avg_cadence is not None
    laps = session.scalars(
        select(Lap).where(Lap.activity_id == activity_id).order_by(Lap.lap_index)
    ).all()
    payload = {
        "ride": context.model_dump(mode="json"),
        "laps": [
            {
                "lap_index": lap.lap_index,
                "distance_m": lap.distance_m,
                "duration_s": lap.duration_s,
                "elev_gain_m": lap.elev_gain_m,
                "avg_speed_mps": lap.avg_speed_mps if "speed" in context.sensors_present else None,
                "avg_hr": lap.avg_hr if hr_ok else None,
                "avg_power_w": lap.avg_power_w if power_ok else None,
                "avg_cadence": lap.avg_cadence if cadence_ok else None,
            }
            for lap in laps
        ],
    }
    return ToolResult(_json(payload), "Opening a ride")


async def _search_books(session: Session, query: str, embedder: Any) -> ToolResult:
    status = "Checking your training books"
    try:
        context = await rag_service.get_training_context(session, query, embedder)
    except ValueError as exc:
        return ToolResult(_json({"error": str(exc)}), status)
    if not context.passages:
        return ToolResult(_json({"passages": [], "note": "No books imported yet."}), status)
    sources = [
        SourceOut(
            book_id=p.book_id,
            title=p.title,
            author=p.author,
            page_start=p.page_start,
            page_end=p.page_end,
        )
        for p in context.passages
    ]
    payload = {"passages": [p.model_dump(mode="json") for p in context.passages]}
    return ToolResult(_json(payload), status, sources)


async def run_tool(session: Session, name: str, raw_args: str, embedder: Any) -> ToolResult:
    """Never raises for bad input: errors go back to the model as JSON so
    it can recover or explain, instead of aborting the rider's turn."""
    try:
        args = json.loads(raw_args or "{}")
        if not isinstance(args, dict):
            raise ValueError("arguments must be an object")
    except ValueError:
        return ToolResult(_json({"error": "Invalid tool arguments"}), "Thinking")

    try:
        if name == "get_rider_profile":
            return _profile(session)
        if name == "get_training_summary":
            summary = activities_service.get_training_summary(session, int(args.get("weeks") or 8))
            return ToolResult(_json(summary), f"Summarizing your last {len(summary.weeks)} weeks")
        if name == "list_recent_rides":
            return _recent_rides(session, int(args.get("limit") or 10), args.get("bike_type"))
        if name == "get_ride":
            return _ride(session, int(args["activity_id"]))
        if name == "search_training_books":
            return await _search_books(session, str(args.get("query", "")), embedder)
        if name == "remember":
            note = memory.add_note(session, str(args.get("note", "")))
            return ToolResult(_json(note), "Saving that to memory")
        if name == "forget":
            memory.delete_note(session, int(args["note_id"]))
            return ToolResult(_json({"deleted": True}), "Updating memory")
    except (KeyError, TypeError, ValueError, LookupError) as exc:
        return ToolResult(_json({"error": str(exc)}), "Thinking")
    return ToolResult(_json({"error": f"Unknown tool {name}"}), "Thinking")
