"""Coach conversations and the agent loop.

`run_turn` is the whole agent: budget check -> scope guardrail -> prompt
(static system prompt + rider context + recent history) -> streamed
model reply with up to `_MAX_TOOL_ROUNDS` rounds of tool calls ->
persisted assistant message. It yields `CoachEvent`s so the REST adapter
can forward them as SSE without knowing anything about the loop.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from soft_floyd_core.coach import memory
from soft_floyd_core.coach.guardrail import REFUSAL, ScopeClassifier, classify_scope
from soft_floyd_core.coach.prompts import SYSTEM_PROMPT
from soft_floyd_core.coach.tools import TOOLS, SourceOut, run_tool
from soft_floyd_core.llm.client import ChatDone, LLMClient, TextDelta
from soft_floyd_core.llm.usage import ensure_within_budget, record_usage
from soft_floyd_core.models import CoachConversation, CoachMessage
from soft_floyd_core.profile.service import get_profile

MAX_MESSAGE_CHARS = 4000
_HISTORY_MESSAGES = 12
_MAX_TOOL_ROUNDS = 4
_TITLE_CHARS = 60


class CoachLLM(ScopeClassifier, Protocol):
    def chat_stream(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> AsyncIterator[TextDelta | ChatDone]: ...

    async def embed(self, text: str) -> Any: ...


def make_coach_llm(api_key: str | None) -> LLMClient | None:
    return LLMClient(api_key) if api_key else None


class ConversationOut(BaseModel):
    id: int
    title: str
    created_at: dt.datetime
    updated_at: dt.datetime


class MessageOut(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    sources: list[SourceOut]
    created_at: dt.datetime


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]


class CoachEvent(BaseModel):
    """One SSE event. `type` decides which other field is set."""

    type: Literal["delta", "tool_status", "sources", "done", "error"]
    text: str | None = None
    sources: list[SourceOut] | None = None
    message: MessageOut | None = None


def _conversation_out(conv: CoachConversation) -> ConversationOut:
    return ConversationOut(
        id=conv.id, title=conv.title, created_at=conv.created_at, updated_at=conv.updated_at
    )


def _message_out(msg: CoachMessage) -> MessageOut:
    return MessageOut(
        id=msg.id,
        role=msg.role,  # type: ignore[arg-type]
        content=msg.content,
        sources=[SourceOut(**s) for s in msg.sources or []],
        created_at=msg.created_at,
    )


def create_conversation(session: Session) -> ConversationOut:
    conv = CoachConversation()
    session.add(conv)
    session.flush()
    return _conversation_out(conv)


def list_conversations(session: Session) -> list[ConversationOut]:
    rows = session.scalars(
        select(CoachConversation).order_by(
            CoachConversation.updated_at.desc(), CoachConversation.id.desc()
        )
    ).all()
    return [_conversation_out(c) for c in rows]


def _get(session: Session, conversation_id: int) -> CoachConversation:
    conv = session.get(CoachConversation, conversation_id)
    if conv is None:
        raise LookupError(f"Conversation {conversation_id} not found")
    return conv


def get_conversation(session: Session, conversation_id: int) -> ConversationDetailOut:
    conv = _get(session, conversation_id)
    return ConversationDetailOut(
        **_conversation_out(conv).model_dump(),
        messages=[_message_out(m) for m in conv.messages],
    )


def delete_conversation(session: Session, conversation_id: int) -> None:
    session.delete(_get(session, conversation_id))
    session.flush()


def check_turn(session: Session, conversation_id: int, text: str, budget_usd: float) -> str:
    """Everything that can reject a turn before streaming starts, so the
    REST adapter can still answer with a proper status code. Returns the
    normalized message text."""
    _get(session, conversation_id)
    text = text.strip()
    if not text:
        raise ValueError("Message must not be empty")
    if len(text) > MAX_MESSAGE_CHARS:
        raise ValueError(f"Message must be at most {MAX_MESSAGE_CHARS} characters")
    ensure_within_budget(session, budget_usd)
    return text


def _rider_context(session: Session, now: dt.datetime) -> str:
    profile = get_profile(session)
    notes = memory.list_notes(session)
    lines = [
        f"Today is {now.date().isoformat()} ({now.strftime('%A')}).",
        f"Goal: {profile.goal_text or 'not set'}.",
    ]
    if profile.target_event_name:
        lines.append(f"Target event: {profile.target_event_name} on {profile.target_event_date}.")
    lines += [
        f"Primary discipline: {profile.primary_discipline or 'unknown'}.",
        f"Capability tier: {profile.capability_tier}; metrics the rider's hardware supports: "
        f"{', '.join(profile.available_metrics)}.",
        "Call get_rider_profile for availability, experience and body data.",
        "",
        "Saved memory notes about the rider (id: note):",
    ]
    lines += [f"- {n.id}: {n.text}" for n in notes] or ["- (none yet)"]
    return "\n".join(lines)


async def run_turn(
    session: Session,
    conversation_id: int,
    text: str,
    llm: CoachLLM,
    budget_usd: float,
    now: dt.datetime | None = None,
) -> AsyncIterator[CoachEvent]:
    text = check_turn(session, conversation_id, text, budget_usd)
    conv = _get(session, conversation_id)
    history = list(conv.messages)[-_HISTORY_MESSAGES:]

    session.add(CoachMessage(conversation_id=conv.id, role="user", content=text))
    if not history:
        conv.title = text if len(text) <= _TITLE_CHARS else text[: _TITLE_CHARS - 1] + "…"
    conv.updated_at = dt.datetime.now(dt.UTC)
    session.commit()

    previous_reply = next((m.content for m in reversed(history) if m.role == "assistant"), None)
    in_scope, usage = await classify_scope(llm, text, previous_reply)
    record_usage(session, usage)
    session.commit()

    reply = ""
    sources: dict[tuple[int, int], SourceOut] = {}
    if not in_scope:
        reply = REFUSAL
        yield CoachEvent(type="delta", text=reply)
    else:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": _rider_context(session, now or dt.datetime.now())},
            *({"role": m.role, "content": m.content} for m in history),
            {"role": "user", "content": text},
        ]
        for round_ in range(_MAX_TOOL_ROUNDS + 1):
            # The last round gets no tools, forcing a written answer.
            tools = TOOLS if round_ < _MAX_TOOL_ROUNDS else None
            done: ChatDone | None = None
            round_text = ""
            async for item in llm.chat_stream(messages, tools):
                if isinstance(item, TextDelta):
                    round_text += item.text
                    yield CoachEvent(type="delta", text=item.text)
                else:
                    done = item
            reply += round_text
            if done is None:
                break
            record_usage(session, done.usage)
            session.commit()
            if not done.tool_calls:
                break
            messages.append(
                {
                    "role": "assistant",
                    "content": round_text or None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {"name": call.name, "arguments": call.arguments},
                        }
                        for call in done.tool_calls
                    ],
                }
            )
            for call in done.tool_calls:
                result = await run_tool(session, call.name, call.arguments, llm)
                session.commit()
                yield CoachEvent(type="tool_status", text=result.status)
                for source in result.sources:
                    sources.setdefault((source.book_id, source.page_start), source)
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": result.content}
                )

    if not reply.strip():
        reply = "Sorry — I couldn't put an answer together. Could you rephrase that?"
        yield CoachEvent(type="delta", text=reply)
    cited = [s for s in sources.values() if s.title in reply] or list(sources.values())
    if cited:
        yield CoachEvent(type="sources", sources=cited)
    assistant = CoachMessage(
        conversation_id=conv.id,
        role="assistant",
        content=reply,
        sources=[json.loads(s.model_dump_json()) for s in cited],
    )
    session.add(assistant)
    conv.updated_at = dt.datetime.now(dt.UTC)
    session.commit()
    yield CoachEvent(type="done", message=_message_out(assistant))
