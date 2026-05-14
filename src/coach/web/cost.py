"""Token usage accounting and cost calculation for Anthropic Haiku 4.5."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from coach.store.models import Message

if TYPE_CHECKING:
    pass

# Haiku 4.5 pricing (USD per million tokens)
_INPUT_PER_MTOK = Decimal("1.00")
_OUTPUT_PER_MTOK = Decimal("5.00")
_CACHE_WRITE_PER_MTOK = Decimal("1.25")
_CACHE_READ_PER_MTOK = Decimal("0.10")

_M = Decimal("1_000_000")


def calculate_cost(
    tokens_in: int = 0,
    tokens_out: int = 0,
    cache_read: int = 0,
    cache_write: int = 0,
) -> Decimal:
    """Return total cost in USD for one Anthropic API call."""
    cost = (
        Decimal(tokens_in) / _M * _INPUT_PER_MTOK
        + Decimal(tokens_out) / _M * _OUTPUT_PER_MTOK
        + Decimal(cache_read) / _M * _CACHE_READ_PER_MTOK
        + Decimal(cache_write) / _M * _CACHE_WRITE_PER_MTOK
    )
    return cost


def record_usage(session: Session, message: Message, usage_obj: object) -> Decimal:
    """Extract token counts from Anthropic usage object, update Message row, return cost."""
    tokens_in = getattr(usage_obj, "input_tokens", 0) or 0
    tokens_out = getattr(usage_obj, "output_tokens", 0) or 0
    cache_read = getattr(usage_obj, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage_obj, "cache_creation_input_tokens", 0) or 0

    cost = calculate_cost(tokens_in, tokens_out, cache_read, cache_write)

    message.tokens_in = tokens_in
    message.tokens_out = tokens_out
    message.cache_read = cache_read
    message.cache_write = cache_write
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
