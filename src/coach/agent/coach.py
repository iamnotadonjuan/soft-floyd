"""CoachSession: OpenAI streaming + tool loop for Soft Floyd."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from coach.agent.tools import TOOL_SCHEMAS, execute_tool
from coach.log import log
from coach.rag.retriever import RetrievalContext, retrieve_for_activity
from coach.store.models import Conversation, Message
from coach.web.cost import record_usage

if TYPE_CHECKING:
    from coach.config import Config

_MODEL = "gpt-4.1-mini"
_MAX_TOKENS = 1500
_MAX_TOOL_CALLS = 5
_SYSTEM_MD = Path(__file__).parent / "prompts" / "system.md"


def _load_system() -> str:
    return _SYSTEM_MD.read_text(encoding="utf-8")


def _context_block(ctx: RetrievalContext) -> str:
    parts = ["## Current Ride\n" + ctx.current_card]
    if ctx.similar_cards:
        parts.append("## Similar Past Rides\n" + "\n---\n".join(ctx.similar_cards))
    if ctx.recent_cards:
        parts.append("## Recent Rides (chronological)\n" + "\n---\n".join(ctx.recent_cards))
    if ctx.wellness_summary:
        parts.append("## Wellness Context\n" + ctx.wellness_summary)
    return "\n\n".join(parts)


def _build_openai_client(cfg: Config):  # noqa: ANN201
    import openai

    return openai.AsyncOpenAI(api_key=cfg.openai_api_key)


class CoachSession:
    def __init__(self, session: Session, cfg: Config, activity_id: int) -> None:
        self._session = session
        self._cfg = cfg
        self._activity_id = activity_id
        self._system = _load_system()
        self._client = _build_openai_client(cfg)
        self._conversation: Conversation | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def initial_analysis(self) -> AsyncIterator[str]:
        """Generate and stream Soft Floyd's initial ride analysis."""
        ctx = retrieve_for_activity(self._session, self._cfg, self._activity_id)
        user_content = (
            "Please analyse my ride and give me your Soft Floyd assessment.\n\n"
            + _context_block(ctx)
        )
        conv = Conversation(activity_id=self._activity_id)
        self._session.add(conv)
        self._session.flush()
        self._conversation = conv

        user_msg = Message(conversation_id=conv.id, role="user", content_json=user_content)
        self._session.add(user_msg)
        self._session.commit()

        messages = [{"role": "user", "content": user_content}]
        async for chunk in self._run_loop(messages, conv.id):
            yield chunk

    async def chat(self, user_message: str) -> AsyncIterator[str]:
        """Continue an existing conversation. Yields text chunks only."""
        async for event_type, data in self.chat_stream(user_message):
            if event_type == "token":
                yield data

    async def chat_stream(self, user_message: str) -> AsyncIterator[tuple[str, str]]:
        """Continue an existing conversation. Yields (event_type, data) pairs for SSE."""
        from sqlalchemy import select

        conv = self._session.execute(
            select(Conversation)
            .where(Conversation.activity_id == self._activity_id)
            .order_by(Conversation.id.desc())
        ).scalar_one_or_none()

        if conv is None:
            async for pair in self._bootstrap_chat_stream(user_message):
                yield pair
            return

        self._conversation = conv
        prior_messages = self._build_message_history(conv)

        user_msg = Message(conversation_id=conv.id, role="user", content_json=user_message)
        self._session.add(user_msg)
        self._session.commit()

        messages = prior_messages + [{"role": "user", "content": user_message}]
        async for pair in self._run_loop_events(messages, conv.id):
            yield pair

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _bootstrap_chat_stream(self, user_message: str) -> AsyncIterator[tuple[str, str]]:
        ctx = retrieve_for_activity(self._session, self._cfg, self._activity_id)
        combined = _context_block(ctx) + "\n\n" + user_message
        conv = Conversation(activity_id=self._activity_id)
        self._session.add(conv)
        self._session.flush()
        self._conversation = conv

        user_msg = Message(conversation_id=conv.id, role="user", content_json=combined)
        self._session.add(user_msg)
        self._session.commit()

        messages = [{"role": "user", "content": combined}]
        async for pair in self._run_loop_events(messages, conv.id):
            yield pair

    def _build_message_history(self, conv: Conversation) -> list[dict]:
        """Reconstruct the OpenAI messages list from persisted Message rows."""
        from sqlalchemy import select

        rows = list(
            self._session.execute(
                select(Message).where(Message.conversation_id == conv.id).order_by(Message.id)
            ).scalars()
        )
        messages: list[dict] = []
        for row in rows:
            content = row.content_json
            if isinstance(content, str):
                messages.append({"role": row.role, "content": content})
            elif isinstance(content, dict):
                # Stored OpenAI message dict (assistant with tool_calls, or tool result)
                messages.append(content)
            elif isinstance(content, list):
                # Tool result messages stored as a list of role+content dicts
                messages.extend(content)
        return messages

    async def _run_loop(self, messages: list[dict], conversation_id: int) -> AsyncIterator[str]:
        async for event_type, data in self._run_loop_events(messages, conversation_id):
            if event_type == "token":
                yield data

    async def _run_loop_events(
        self, messages: list[dict], conversation_id: int
    ) -> AsyncIterator[tuple[str, str]]:
        """Core OpenAI streaming + tool-use loop. Yields (event_type, data) pairs."""
        system_messages = [{"role": "system", "content": self._system}]

        for call_count in range(_MAX_TOOL_CALLS + 1):
            text_parts: list[str] = []
            # Accumulate tool_calls deltas: {index: {"id", "name", "arguments"}}
            tool_call_accum: dict[int, dict] = {}
            finish_reason: str | None = None
            usage_obj = None

            stream = await self._client.chat.completions.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                messages=system_messages + messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                stream=True,
                stream_options={"include_usage": True},
            )

            async for chunk in stream:
                # Usage arrives on the final chunk
                if chunk.usage is not None:
                    usage_obj = chunk.usage

                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                finish_reason = choice.finish_reason or finish_reason
                delta = choice.delta

                if delta.content:
                    text_parts.append(delta.content)
                    yield ("token", delta.content)

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_call_accum:
                            tool_call_accum[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc_delta.id:
                            tool_call_accum[idx]["id"] += tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                tool_call_accum[idx]["name"] += tc_delta.function.name
                            if tc_delta.function.arguments:
                                tool_call_accum[idx]["arguments"] += tc_delta.function.arguments

            # Build the assistant message dict for persistence + replay
            tool_calls_list = [
                {
                    "id": v["id"],
                    "type": "function",
                    "function": {"name": v["name"], "arguments": v["arguments"]},
                }
                for v in tool_call_accum.values()
            ]
            assistant_msg_dict: dict = {
                "role": "assistant",
                "content": "".join(text_parts) or None,
            }
            if tool_calls_list:
                assistant_msg_dict["tool_calls"] = tool_calls_list

            asst_msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content_json=assistant_msg_dict,
            )
            self._session.add(asst_msg)
            self._session.flush()
            if usage_obj is not None:
                record_usage(self._session, asst_msg, usage_obj)
            self._session.commit()

            if finish_reason != "tool_calls":
                break

            if call_count >= _MAX_TOOL_CALLS:
                log.warning("coach.tool_call_limit_reached", activity_id=self._activity_id)
                break

            # Execute tools and build tool-result messages
            tool_result_messages: list[dict] = []
            for tc in tool_calls_list:
                tool_name = tc["function"]["name"]
                log.debug("coach.tool_call", tool=tool_name, activity_id=self._activity_id)
                yield ("tool", tool_name)
                inputs = json.loads(tc["function"]["arguments"] or "{}")
                result = execute_tool(self._session, tool_name, inputs)
                tool_result_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result),
                    }
                )

            # Persist tool results as a single Message row (list of dicts)
            tool_msg = Message(
                conversation_id=conversation_id,
                role="tool",
                content_json=tool_result_messages,
            )
            self._session.add(tool_msg)
            self._session.commit()

            messages = messages + [assistant_msg_dict, *tool_result_messages]
