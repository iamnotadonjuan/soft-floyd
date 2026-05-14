"""FastAPI application — Phase 3: CORS, SSE chat, activity list/detail, static serving."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func, select
from sse_starlette.sse import EventSourceResponse

from coach.agent.coach import CoachSession
from coach.config import Config
from coach.log import log
from coach.store.models import Activity, Conversation, Lap, Message, Metrics, Record
from coach.store.session import get_sync_session, init_db
from coach.web.cost import monthly_total

_FRONTEND_DIST = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"
_RECORD_DECIMATE = 1000  # max time-series points sent to frontend


def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="Soft Floyd Coach API", version="0.3.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def _startup() -> None:
        init_db(cfg.db_path)

    # ------------------------------------------------------------------
    # Activity list
    # ------------------------------------------------------------------

    @app.get("/api/activities")
    def list_activities(
        bike_type: str | None = Query(None),
        page: int = Query(0, ge=0),
        page_size: int = Query(20, ge=1, le=100),
    ) -> dict[str, Any]:
        session = get_sync_session()
        try:
            q = select(Activity).order_by(Activity.start_time.desc())
            if bike_type:
                q = q.where(Activity.bike_type == bike_type)

            total = session.execute(select(func.count()).select_from(q.subquery())).scalar() or 0

            rows = list(session.execute(q.offset(page * page_size).limit(page_size)).scalars())

            # Attach analyzed flag (has at least one assistant message)
            activity_ids = [a.id for a in rows]
            analyzed_ids: set[int] = set()
            if activity_ids:
                convs = session.execute(
                    select(Conversation.activity_id)
                    .join(Message, Message.conversation_id == Conversation.id)
                    .where(
                        Conversation.activity_id.in_(activity_ids),
                        Message.role == "assistant",
                    )
                    .distinct()
                ).scalars()
                analyzed_ids = set(convs)

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "activities": [
                    {
                        "id": a.id,
                        "date": a.start_time.strftime("%Y-%m-%d"),
                        "start_time": a.start_time.isoformat(),
                        "bike_type": a.bike_type,
                        "distance_km": round(a.distance_m / 1000, 2),
                        "duration_min": round(a.duration_s / 60, 1),
                        "elev_gain_m": round(a.elev_gain_m),
                        "avg_hr": a.avg_hr,
                        "max_hr": a.max_hr,
                        "tss_proxy": round(a.tss_proxy, 1) if a.tss_proxy else None,
                        "analyzed": a.id in analyzed_ids,
                    }
                    for a in rows
                ],
            }
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Activity detail
    # ------------------------------------------------------------------

    @app.get("/api/activities/{activity_id}")
    def get_activity(activity_id: int) -> dict[str, Any]:
        session = get_sync_session()
        try:
            activity = session.get(Activity, activity_id)
            if activity is None:
                raise HTTPException(status_code=404, detail="Activity not found")

            laps = list(
                session.execute(
                    select(Lap).where(Lap.activity_id == activity_id).order_by(Lap.lap_index)
                ).scalars()
            )
            metrics = session.get(Metrics, activity_id)

            # Downsample records to ≤1000 points
            all_records = list(
                session.execute(
                    select(Record)
                    .where(Record.activity_id == activity_id)
                    .order_by(Record.t_offset_s)
                ).scalars()
            )
            step = max(1, len(all_records) // _RECORD_DECIMATE)
            records = all_records[::step]

            return {
                "id": activity.id,
                "date": activity.start_time.strftime("%Y-%m-%d"),
                "start_time": activity.start_time.isoformat(),
                "bike_type": activity.bike_type,
                "sport": activity.sport,
                "sub_sport": activity.sub_sport,
                "is_indoor": activity.is_indoor,
                "distance_km": round(activity.distance_m / 1000, 2),
                "duration_min": round(activity.duration_s / 60, 1),
                "elev_gain_m": round(activity.elev_gain_m),
                "avg_hr": activity.avg_hr,
                "max_hr": activity.max_hr,
                "tss_proxy": round(activity.tss_proxy, 1) if activity.tss_proxy else None,
                "laps": [
                    {
                        "lap_index": lap.lap_index,
                        "distance_km": round(lap.distance_m / 1000, 2),
                        "duration_min": round(lap.duration_s / 60, 1),
                        "avg_hr": lap.avg_hr,
                        "avg_speed_kmh": round(lap.avg_speed * 3.6, 1) if lap.avg_speed else None,
                        "elev_gain_m": round(lap.elev_gain_m),
                        "gap_speed_kmh": round(lap.gap_speed * 3.6, 1) if lap.gap_speed else None,
                    }
                    for lap in laps
                ],
                "metrics": {
                    "decoupling_pct": metrics.decoupling_pct if metrics else None,
                    "hr_drift_pct": metrics.hr_drift_pct if metrics else None,
                    "time_in_z1_min": round((metrics.time_in_z1 or 0) / 60, 1) if metrics else None,
                    "time_in_z2_min": round((metrics.time_in_z2 or 0) / 60, 1) if metrics else None,
                    "time_in_z3_min": round((metrics.time_in_z3 or 0) / 60, 1) if metrics else None,
                    "time_in_z4_min": round((metrics.time_in_z4 or 0) / 60, 1) if metrics else None,
                    "time_in_z5_min": round((metrics.time_in_z5 or 0) / 60, 1) if metrics else None,
                    "vam_best_20min": metrics.vam_best_20min if metrics else None,
                    "gap_normalized_mps": metrics.gap_normalized if metrics else None,
                }
                if metrics
                else None,
                "timeseries": [
                    {
                        "t": rec.t_offset_s,
                        "hr": rec.hr,
                        "alt": rec.altitude_m,
                        "speed_kmh": round(rec.speed_mps * 3.6, 1) if rec.speed_mps else None,
                    }
                    for rec in records
                ],
            }
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Conversation messages
    # ------------------------------------------------------------------

    @app.get("/api/activities/{activity_id}/messages")
    def get_messages(activity_id: int) -> dict[str, Any]:
        session = get_sync_session()
        try:
            conv = session.execute(
                select(Conversation)
                .where(Conversation.activity_id == activity_id)
                .order_by(Conversation.id.desc())
            ).scalar_one_or_none()

            if conv is None:
                return {"activity_id": activity_id, "messages": []}

            msgs = list(
                session.execute(
                    select(Message).where(Message.conversation_id == conv.id).order_by(Message.id)
                ).scalars()
            )

            def _text(m: Message) -> str:
                c = m.content_json
                if isinstance(c, str):
                    return c
                if isinstance(c, list):
                    return " ".join(
                        b.get("text", "")
                        for b in c
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                return ""

            return {
                "activity_id": activity_id,
                "conversation_id": conv.id,
                "messages": [
                    {
                        "id": m.id,
                        "role": m.role,
                        "text": _text(m),
                        "tokens_in": m.tokens_in,
                        "tokens_out": m.tokens_out,
                        "cache_read": m.cache_read,
                        "cost_usd": m.cost_usd,
                        "created_at": m.created_at.isoformat(),
                    }
                    for m in msgs
                    if m.role in ("user", "assistant")
                ],
            }
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Analysis (sync JSON — trigger or retrieve)
    # ------------------------------------------------------------------

    @app.post("/api/activities/{activity_id}/analysis")
    async def trigger_analysis(activity_id: int) -> dict[str, Any]:
        log.info("api.trigger_analysis", activity_id=activity_id)
        session = get_sync_session()
        try:
            coach = CoachSession(session, cfg, activity_id)
            text_parts: list[str] = []
            async for chunk in coach.initial_analysis():
                text_parts.append(chunk)
            return {"activity_id": activity_id, "analysis": "".join(text_parts)}
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            log.error("api.analysis_error", activity_id=activity_id, error=str(exc))
            raise HTTPException(status_code=500, detail="Analysis failed") from exc
        finally:
            session.close()

    @app.get("/api/activities/{activity_id}/analysis")
    def get_analysis(activity_id: int) -> dict[str, Any]:
        session = get_sync_session()
        try:
            conv = session.execute(
                select(Conversation)
                .where(Conversation.activity_id == activity_id)
                .order_by(Conversation.id.desc())
            ).scalar_one_or_none()
            if conv is None:
                raise HTTPException(status_code=404, detail="No analysis found")

            first_assistant = session.execute(
                select(Message)
                .where(Message.conversation_id == conv.id, Message.role == "assistant")
                .order_by(Message.id)
            ).scalar_one_or_none()

            if first_assistant is None:
                raise HTTPException(status_code=404, detail="No analysis found")

            c = first_assistant.content_json
            if isinstance(c, list):
                text = " ".join(
                    b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text"
                )
            else:
                text = str(c or "")

            return {"activity_id": activity_id, "analysis": text, "conversation_id": conv.id}
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Chat — SSE streaming
    # ------------------------------------------------------------------

    class ChatRequest(BaseModel):
        message: str

    @app.post("/api/activities/{activity_id}/chat")
    async def chat_sse(activity_id: int, body: ChatRequest) -> EventSourceResponse:
        """Stream Soft Floyd's reply as SSE. Events: token | tool | done | error."""
        log.info("api.chat_sse", activity_id=activity_id)
        session = get_sync_session()

        async def _generate():
            try:
                coach = CoachSession(session, cfg, activity_id)
                async for event_type, data in coach.chat_stream(body.message):
                    yield {"event": event_type, "data": data}
                yield {"event": "done", "data": ""}
            except Exception as exc:
                log.error("api.chat_error", activity_id=activity_id, error=str(exc))
                yield {"event": "error", "data": str(exc)}
            finally:
                session.close()

        return EventSourceResponse(_generate())

    # ------------------------------------------------------------------
    # Cost
    # ------------------------------------------------------------------

    @app.get("/api/cost/month")
    def get_monthly_cost() -> dict[str, Any]:
        session = get_sync_session()
        try:
            return monthly_total(session)
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Serve React frontend (Phase 3 — opt-in via COACH_SERVE_FRONTEND=1)
    # ------------------------------------------------------------------

    if cfg.serve_frontend:
        from fastapi.staticfiles import StaticFiles

        dist = _FRONTEND_DIST
        if dist.exists():
            # Mount at root — must be last so API routes take priority
            app.mount("/", StaticFiles(directory=str(dist), html=True), name="static")
            log.info("api.serving_frontend", dist=str(dist))
        else:
            log.warning("api.frontend_dist_missing", dist=str(dist))

    return app
