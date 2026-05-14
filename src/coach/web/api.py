"""FastAPI application — Phase 2 HTTP surface (synchronous JSON endpoints)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from coach.agent.coach import CoachSession
from coach.config import Config
from coach.log import log
from coach.store.models import Conversation, Message
from coach.store.session import get_sync_session, init_db
from coach.web.cost import monthly_total


def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="Soft Floyd Coach API", version="0.2.0")

    @app.on_event("startup")
    def _startup() -> None:
        init_db(cfg.db_path)

    # ------------------------------------------------------------------
    # Analysis endpoints
    # ------------------------------------------------------------------

    @app.post("/api/activities/{activity_id}/analysis")
    async def trigger_analysis(activity_id: int) -> dict[str, Any]:
        """Generate (or re-run) Soft Floyd's initial analysis for an activity."""
        log.info("api.trigger_analysis", activity_id=activity_id)
        session = get_sync_session()
        try:
            coach = CoachSession(session, cfg, activity_id)
            text_parts: list[str] = []
            async for chunk in coach.initial_analysis():
                text_parts.append(chunk)
            full_text = "".join(text_parts)
            return {"activity_id": activity_id, "analysis": full_text}
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            log.error("api.analysis_error", activity_id=activity_id, error=str(exc))
            raise HTTPException(status_code=500, detail="Analysis failed") from exc
        finally:
            session.close()

    @app.get("/api/activities/{activity_id}/analysis")
    def get_analysis(activity_id: int) -> dict[str, Any]:
        """Return the latest stored analysis for an activity."""
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

            content = first_assistant.content_json
            if isinstance(content, list):
                text = " ".join(
                    b.get("text", "")
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            else:
                text = str(content or "")

            return {"activity_id": activity_id, "analysis": text, "conversation_id": conv.id}
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Chat endpoint
    # ------------------------------------------------------------------

    class ChatRequest(BaseModel):
        message: str

    @app.post("/api/activities/{activity_id}/chat")
    async def chat(activity_id: int, body: ChatRequest) -> dict[str, Any]:
        """Send a follow-up message to Soft Floyd about an activity."""
        log.info("api.chat", activity_id=activity_id)
        session = get_sync_session()
        try:
            coach = CoachSession(session, cfg, activity_id)
            text_parts: list[str] = []
            async for chunk in coach.chat(body.message):
                text_parts.append(chunk)
            return {"activity_id": activity_id, "reply": "".join(text_parts)}
        except Exception as exc:
            log.error("api.chat_error", activity_id=activity_id, error=str(exc))
            raise HTTPException(status_code=500, detail="Chat failed") from exc
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Cost endpoint
    # ------------------------------------------------------------------

    @app.get("/api/cost/month")
    def get_monthly_cost() -> dict[str, Any]:
        """Return current month's LLM spend."""
        session = get_sync_session()
        try:
            return monthly_total(session)
        finally:
            session.close()

    return app
