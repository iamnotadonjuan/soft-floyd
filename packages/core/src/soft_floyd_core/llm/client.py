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

CHAT_MODEL = "gpt-6-luna"
EMBEDDING_MODEL = "text-embedding-3-small"

# USD per 1M tokens.
_PRICING = {
    CHAT_MODEL: {"input": 0.10, "cached_input": 0.01, "cache_write": 0.125, "output": 0.50},
    EMBEDDING_MODEL: {"input": 0.02, "cached_input": 0.02, "output": 0.0},
}


@dataclass(frozen=True)
class Usage:
    model: str
    prompt_tokens: int
    cached_tokens: int
    completion_tokens: int
    cache_write_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        price = _PRICING[self.model]
        uncached = max(self.prompt_tokens - self.cached_tokens - self.cache_write_tokens, 0)
        return (
            uncached * price["input"]
            + self.cached_tokens * price["cached_input"]
            + self.cache_write_tokens * price.get("cache_write", price["input"])
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
    response_items: list[dict[str, Any]] = field(default_factory=list)


class IncompleteResponseError(RuntimeError):
    def __init__(self, usage: Usage | None = None) -> None:
        super().__init__("The model did not return a complete response")
        self.usage = usage


def _response_usage(raw: Any) -> Usage:
    if raw is None:
        raise RuntimeError("The model response did not include usage")
    details = getattr(raw, "input_tokens_details", None)
    return Usage(
        model=CHAT_MODEL,
        prompt_tokens=raw.input_tokens,
        cached_tokens=(getattr(details, "cached_tokens", 0) or 0) if details else 0,
        completion_tokens=raw.output_tokens,
        cache_write_tokens=(getattr(details, "cache_write_tokens", 0) or 0) if details else 0,
    )


def _response_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep complete output items when replaying a tool round, including reasoning."""
    return messages


def _response_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": tool["function"]["name"],
            "description": tool["function"]["description"],
            "parameters": tool["function"]["parameters"],
            "strict": False,
        }
        for tool in tools
    ]


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
        stream = await self._client.responses.create(
            model=CHAT_MODEL,
            input=_response_input(messages),
            tools=_response_tools(tools) if tools else [],
            reasoning={"effort": "medium"},
            include=["reasoning.encrypted_content"],
            store=False,
            stream=True,
        )
        completed = None
        async for event in stream:
            if event.type == "response.output_text.delta":
                yield TextDelta(event.delta)
            elif event.type == "response.completed":
                completed = event.response
            elif event.type in {"response.failed", "response.incomplete"}:
                raw_usage = event.response.usage
                raise IncompleteResponseError(_response_usage(raw_usage) if raw_usage else None)
        if completed is None:
            raise IncompleteResponseError()
        items = [item.model_dump(exclude_none=True) for item in completed.output]
        yield ChatDone(
            usage=_response_usage(completed.usage),
            tool_calls=[
                ToolCall(id=item["call_id"], name=item["name"], arguments=item["arguments"])
                for item in items
                if item["type"] == "function_call"
            ],
            response_items=items,
        )

    async def chat_structured(
        self,
        messages: list[dict[str, Any]],
        schema_name: str,
        schema: dict[str, Any],
        *,
        max_completion_tokens: int,
        reasoning_effort: str = "medium",
    ) -> tuple[dict[str, Any], Usage]:
        response = await self._client.responses.create(
            model=CHAT_MODEL,
            input=_response_input(messages),
            reasoning={"effort": reasoning_effort},
            max_output_tokens=max_completion_tokens,
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": schema,
                    "strict": True,
                }
            },
            store=False,
        )
        usage = _response_usage(response.usage)
        if response.status != "completed" or not response.output_text:
            raise IncompleteResponseError(usage)
        try:
            return json.loads(response.output_text), usage
        except json.JSONDecodeError as exc:
            raise IncompleteResponseError(usage) from exc

    async def chat_json(
        self, messages: list[dict[str, Any]], schema_name: str, schema: dict[str, Any]
    ) -> tuple[dict[str, Any], Usage]:
        """A small no-reasoning scope classification call."""
        return await self.chat_structured(
            messages, schema_name, schema, max_completion_tokens=100, reasoning_effort="none"
        )
