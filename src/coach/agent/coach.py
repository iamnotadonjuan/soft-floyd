"""CoachSession: Anthropic streaming + tool loop for Soft Floyd."""

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

_MODEL = "claude-haiku-4-5-20251001"
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


def _build_anthropic_client(cfg: Config):  # noqa: ANN201
    import anthropic

    return anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key or None)


class CoachSession:
    def __init__(self, session: Session, cfg: Config, activity_id: int) -> None:
        self._session = session
        self._cfg = cfg
        self._activity_id = activity_id
        self._system = _load_system()
        self._client = _build_anthropic_client(cfg)
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

        # Persist user turn
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
        """Handle chat when no prior conversation exists — embed context then reply."""
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
        """Reconstruct the Anthropic messages list from persisted Message rows."""
        from sqlalchemy import select

        rows = list(
            self._session.execute(
                select(Message).where(Message.conversation_id == conv.id).order_by(Message.id)
            ).scalars()
        )
        messages: list[dict] = []
        for row in rows:
            content = row.content_json
            if isinstance(content, str | list):
                messages.append({"role": row.role, "content": content})
        return messages

    async def _run_loop(self, messages: list[dict], conversation_id: int) -> AsyncIterator[str]:
        """Thin text-only wrapper around _run_loop_events."""
        async for event_type, data in self._run_loop_events(messages, conversation_id):
            if event_type == "token":
                yield data

    async def _run_loop_events(
        self, messages: list[dict], conversation_id: int
    ) -> AsyncIterator[tuple[str, str]]:
        """Core streaming + tool-use loop. Yields (event_type, data) pairs."""
        system_block = [
            {
                "type": "text",
                "text": self._system,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        for call_count in range(_MAX_TOOL_CALLS + 1):
            final_message = None

            async with self._client.messages.stream(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                system=system_block,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice={"type": "auto"},
            ) as stream:
                async for text in stream.text_stream:
                    yield ("token", text)
                final_message = await stream.get_final_message()

            # Persist assistant turn
            assistant_content = self._content_to_json(final_message.content)
            asst_msg = Message(
                conversation_id=conversation_id,
                role="assistant",
                content_json=assistant_content,
            )
            self._session.add(asst_msg)
            self._session.flush()
            record_usage(self._session, asst_msg, final_message.usage)
            self._session.commit()

            if final_message.stop_reason != "tool_use":
                break

            if call_count >= _MAX_TOOL_CALLS:
                log.warning("coach.tool_call_limit_reached", activity_id=self._activity_id)
                break

            # Execute tools and continue
            tool_results = []
            for block in final_message.content:
                if block.type == "tool_use":
                    log.debug("coach.tool_call", tool=block.name, activity_id=self._activity_id)
                    yield ("tool", block.name)
                    result = execute_tool(self._session, block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        }
                    )

            messages = messages + [
                {"role": "assistant", "content": assistant_content},
                {"role": "user", "content": tool_results},
            ]

    @staticmethod
    def _content_to_json(content: list) -> list[dict]:
        result = []
        for block in content:
            if block.type == "text":
                result.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                result.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )
        return result
