"""Persisting LLM spend and enforcing the monthly budget.

Every paid call (embeddings and chat) goes through `record_usage`, so
`month_to_date_cost` is the real bill, not an estimate.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from soft_floyd_core.llm.client import Usage
from soft_floyd_core.models import LLMUsageRecord


class BudgetExceededError(RuntimeError):
    """Month-to-date LLM spend has reached SOFT_FLOYD_LLM_MONTHLY_BUDGET_USD."""


def record_usage(session: Session, usage: Usage) -> None:
    session.add(
        LLMUsageRecord(
            model=usage.model,
            prompt_tokens=usage.prompt_tokens,
            cached_tokens=usage.cached_tokens,
            completion_tokens=usage.completion_tokens,
            cost_usd=usage.cost_usd,
        )
    )


def month_to_date_cost(session: Session, now: dt.datetime | None = None) -> float:
    now = now or dt.datetime.now(dt.UTC)
    # occurred_at is stored naive-UTC by SQLite; compare against a naive bound.
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    total = session.scalar(
        select(func.coalesce(func.sum(LLMUsageRecord.cost_usd), 0.0)).where(
            LLMUsageRecord.occurred_at >= month_start
        )
    )
    return float(total or 0.0)


def ensure_within_budget(session: Session, budget_usd: float) -> None:
    spent = month_to_date_cost(session)
    if spent >= budget_usd:
        raise BudgetExceededError(
            f"Monthly LLM budget reached (${spent:.2f} of ${budget_usd:.2f}). "
            "Raise SOFT_FLOYD_LLM_MONTHLY_BUDGET_USD or wait until next month."
        )
