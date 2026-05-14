"""Token usage accounting and cost calculation for OpenAI GPT-4.1 mini."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from coach.store.models import Message

if TYPE_CHECKING:
    pass

# GPT-4.1 mini pricing (USD per million tokens)
_INPUT_PER_MTOK = Decimal("0.40")
_OUTPUT_PER_MTOK = Decimal("1.60")
_CACHE_READ_PER_MTOK = Decimal("0.10")  # OpenAI auto-caches; cached tokens at 75% discount

_M = Decimal("1_000_000")


def calculate_cost(
    tokens_in: int = 0,
    tokens_out: int = 0,
    cache_read: int = 0,
    cache_write: int = 0,  # unused for OpenAI (no separate write tier); kept for signature compat
) -> Decimal:
    """Return total cost in USD for one OpenAI API call.

    tokens_in should be the *uncached* portion (prompt_tokens - cached_tokens).
    cache_read is the number of cached prompt tokens (charged at _CACHE_READ_PER_MTOK).
    """
    cost = (
        Decimal(tokens_in) / _M * _INPUT_PER_MTOK
        + Decimal(tokens_out) / _M * _OUTPUT_PER_MTOK
        + Decimal(cache_read) / _M * _CACHE_READ_PER_MTOK
    )
    return cost


def record_usage(session: Session, message: Message, usage_obj: object) -> Decimal:
    """Extract token counts from OpenAI usage object, update Message row, return cost."""
    prompt_tokens = getattr(usage_obj, "prompt_tokens", 0) or 0
    tokens_out = getattr(usage_obj, "completion_tokens", 0) or 0

    details = getattr(usage_obj, "prompt_tokens_details", None)
    cache_read = getattr(details, "cached_tokens", 0) or 0
    tokens_in = prompt_tokens - cache_read  # uncached portion at full price

    cost = calculate_cost(tokens_in, tokens_out, cache_read)

    message.tokens_in = prompt_tokens  # store total for informational display
    message.tokens_out = tokens_out
    message.cache_read = cache_read
    message.cache_write = 0
    message.cost_usd = float(cost)

    return cost


def monthly_total(session: Session) -> dict:
    """Return cost summary for the current calendar month."""
    now = datetime.datetime.now(datetime.UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_cost = (
        session.execute(
            select(func.sum(Message.cost_usd)).where(Message.created_at >= month_start)
        ).scalar()
        or 0.0
    )

    total_calls = (
        session.execute(
            select(func.count(Message.id)).where(
                Message.created_at >= month_start,
                Message.role == "assistant",
            )
        ).scalar()
        or 0
    )

    return {
        "month": now.strftime("%Y-%m"),
        "total_cost_usd": round(float(total_cost), 4),
        "total_api_calls": total_calls,
        "projected_monthly_usd": round(float(total_cost) / max(now.day, 1) * 30, 2),
    }
