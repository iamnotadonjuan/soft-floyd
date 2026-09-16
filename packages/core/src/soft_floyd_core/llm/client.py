"""OpenAI client wrapper with per-call cost accounting.

Not called anywhere in the scaffold — the coach agent, RAG, and chat are
out of scope for this commit (see docs/exec-plans/active). This exists so
the model choice and cost math are pinned down before that work starts.

Pricing is USD per 1M tokens as of the model's release; update alongside
docs/references when OpenAI changes pricing.
"""

from __future__ import annotations

from dataclasses import dataclass

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
