"""Responses transport and token accounting without live API calls."""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest
from soft_floyd_core.llm.client import (
    CHAT_MODEL,
    ChatDone,
    IncompleteResponseError,
    LLMClient,
    TextDelta,
    Usage,
)


def _usage():
    return NS(
        input_tokens=1000,
        output_tokens=200,
        input_tokens_details=NS(cached_tokens=200, cache_write_tokens=300),
    )


class _Item:
    def __init__(self, value):
        self.value = value

    def model_dump(self, **_kwargs):
        return self.value


class _Responses:
    def __init__(self, response, events=None):
        self.response = response
        self.events = events
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            async def events():
                for event in self.events:
                    yield event

            return events()
        return self.response


def _client(responses):
    client = LLMClient("test-key")
    client._client = NS(responses=responses)
    return client


def test_luna_cost_includes_cache_writes_and_reasoning_output():
    usage = Usage(CHAT_MODEL, 1000, 200, 200, cache_write_tokens=300)
    expected = (500 * 0.10 + 200 * 0.01 + 300 * 0.125 + 200 * 0.50) / 1_000_000
    assert usage.cost_usd == pytest.approx(expected)


async def test_stream_preserves_reasoning_and_function_call_items():
    reasoning = {"type": "reasoning", "encrypted_content": "opaque"}
    call = {
        "type": "function_call", "call_id": "call-1", "name": "get_ride",
        "arguments": '{"id":1}',
    }
    response = NS(output=[_Item(reasoning), _Item(call)], usage=_usage())
    responses = _Responses(response, [
        NS(type="response.output_text.delta", delta="Checking ride"),
        NS(type="response.completed", response=response),
    ])
    client = _client(responses)
    tools = [{"type": "function", "function": {
        "name": "get_ride", "description": "Find ride", "parameters": {"type": "object"},
    }}]

    items = [
        item async for item in client.chat_stream([{"role": "user", "content": "Show ride"}], tools)
    ]

    assert items[0] == TextDelta("Checking ride")
    assert isinstance(items[1], ChatDone)
    assert items[1].response_items == [reasoning, call]
    assert items[1].tool_calls[0].id == "call-1"
    assert items[1].usage.cache_write_tokens == 300
    sent = responses.calls[0]
    assert sent["model"] == CHAT_MODEL
    assert sent["reasoning"] == {"effort": "medium"}
    assert sent["store"] is False
    assert sent["include"] == ["reasoning.encrypted_content"]
    assert sent["tools"][0]["name"] == "get_ride"


async def test_structured_workout_uses_reasoning_and_scope_does_not():
    response = NS(status="completed", output_text=json.dumps({"ok": True}), usage=_usage())
    responses = _Responses(response)
    client = _client(responses)
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}

    result, usage = await client.chat_structured(
        [{"role": "user", "content": "Plan ride"}], "workout", schema,
        max_completion_tokens=4000,
    )
    assert result == {"ok": True}
    assert usage.completion_tokens == 200
    assert responses.calls[0]["text"]["format"]["strict"] is True
    assert responses.calls[0]["reasoning"] == {"effort": "medium"}

    await client.chat_json([{"role": "user", "content": "hello"}], "scope", schema)
    assert responses.calls[1]["reasoning"] == {"effort": "none"}
    assert responses.calls[1]["max_output_tokens"] == 100


async def test_incomplete_structured_response_exposes_billable_usage():
    responses = _Responses(NS(status="incomplete", output_text="", usage=_usage()))
    with pytest.raises(IncompleteResponseError) as error:
        await _client(responses).chat_structured(
            [{"role": "user", "content": "Plan"}], "workout", {}, max_completion_tokens=4000,
        )
    assert error.value.usage is not None
    assert error.value.usage.prompt_tokens == 1000
