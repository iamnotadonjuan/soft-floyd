"""OpenAI client wrapper with per-call cost accounting.

The only place this app talks to OpenAI. Callers never pick a model:
book RAG embeds with EMBEDDING_MODEL and the coach agent (exec-plan 0007)
chats with CHAT_MODEL. Every returned `Usage` must be persisted with
`soft_floyd_core.llm.usage.record_usage` by the caller.

Pricing is USD per 1M tokens as of the model's release; update alongside
docs/references when OpenAI changes pricing.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

CHAT_MODEL = "gpt-4.1-mini"
EMBEDDING_MODEL = "text-embedding-3-small"

# USD per 1M tokens.
_PRICING = {
    CHAT_MODEL: {"input": 0.40, "cached_input": 0.10, "output": 1.60},
    EMBEDDING_MODEL: {"input": 0.02, "cached_input": 0.02, "output": 0.0},
}


@dataclass(frozen=True)
class Usage:
    model: str
    prompt_tokens: int
    cached_tokens: int
    completion_tokens: int

    @property
    def cost_usd(self) -> float:
        price = _PRICING[self.model]
        uncached = max(self.prompt_tokens - self.cached_tokens, 0)
        return (
            uncached * price["input"]
            + self.cached_tokens * price["cached_input"]
            + self.completion_tokens * price["output"]
        ) / 1_000_000


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text, exactly as the model produced it


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ChatDone:
    """Last item of every `chat_stream`: the tool calls the model asked for
    (empty when it answered in text) and the request's token usage."""

    usage: Usage
    tool_calls: list[ToolCall] = field(default_factory=list)


def _chat_usage(raw: Any) -> Usage:
    if raw is None:
        return Usage(CHAT_MODEL, 0, 0, 0)
    details = getattr(raw, "prompt_tokens_details", None)
    return Usage(
        model=CHAT_MODEL,
        prompt_tokens=raw.prompt_tokens,
        cached_tokens=(getattr(details, "cached_tokens", 0) or 0) if details else 0,
        completion_tokens=raw.completion_tokens,
    )


class LLMClient:
    """Thin wrapper pinning the model choice; callers never pick a model."""

    def __init__(self, api_key: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)

    async def embed(self, text: str) -> tuple[list[float], Usage]:
        response = await self._client.embeddings.create(model=EMBEDDING_MODEL, input=text)
        usage = Usage(
            model=EMBEDDING_MODEL,
            prompt_tokens=response.usage.prompt_tokens,
            cached_tokens=0,
            completion_tokens=0,
        )
        return response.data[0].embedding, usage

    async def chat_stream(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> AsyncIterator[TextDelta | ChatDone]:
        kwargs: dict[str, Any] = {}
        if tools:
            kwargs["tools"] = tools
        stream = await self._client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            temperature=0.4,
            **kwargs,
        )
        # Tool-call arguments arrive as fragments keyed by index.
        pending: dict[int, dict[str, str]] = {}
        usage_raw = None
        async for chunk in stream:
            if chunk.usage is not None:
                usage_raw = chunk.usage
            for choice in chunk.choices:
                delta = choice.delta
                if delta.content:
                    yield TextDelta(delta.content)
                for call in delta.tool_calls or []:
                    slot = pending.setdefault(call.index, {"id": "", "name": "", "arguments": ""})
                    if call.id:
                        slot["id"] = call.id
                    if call.function and call.function.name:
                        slot["name"] += call.function.name
                    if call.function and call.function.arguments:
                        slot["arguments"] += call.function.arguments
        yield ChatDone(
            usage=_chat_usage(usage_raw),
            tool_calls=[ToolCall(**pending[i]) for i in sorted(pending)],
        )

    async def chat_structured(
        self,
        messages: list[dict[str, Any]],
        schema_name: str,
        schema: dict[str, Any],
        *,
        max_completion_tokens: int,
        temperature: float = 0,
    ) -> tuple[dict[str, Any], Usage]:
        response = await self._client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            },
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content), _chat_usage(response.usage)

    async def chat_json(
        self, messages: list[dict[str, Any]], schema_name: str, schema: dict[str, Any]
    ) -> tuple[dict[str, Any], Usage]:
        """The guardrail's tiny classification call — a fixed 50-token cap
        keeps it cheap. Anything bigger (training session generation) uses
        chat_structured directly with its own budget."""
        return await self.chat_structured(messages, schema_name, schema, max_completion_tokens=50)
