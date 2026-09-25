"""Account identity and mandatory ORM ownership filtering for rider data."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from soft_floyd_core.models import (
    Activity,
    Bike,
    CoachConversation,
    CoachMemoryNote,
    CoachMessage,
    GarminSyncState,
    Lap,
    LLMUsageRecord,
    Record,
    RiderProfile,
    TrainingSession,
)

_current_account: ContextVar[int | None] = ContextVar("soft_floyd_account", default=None)
OWNED_MODELS = (
    RiderProfile,
    Bike,
    Activity,
    Lap,
    Record,
    GarminSyncState,
    CoachConversation,
    CoachMessage,
    CoachMemoryNote,
    TrainingSession,
)


def enter_account(account_id: int) -> Token[int | None]:
    return _current_account.set(account_id)


def leave_account(token: Token[int | None]) -> None:
    _current_account.reset(token)


@contextmanager
def scoped_account(owner: int) -> Iterator[None]:
    token = enter_account(owner)
    try:
        yield
    finally:
        leave_account(token)


def account_id(session: Session | None = None) -> int:
    value = _current_account.get()
    if session is not None:
        value = session.info.get("account_id", value)
    if value is None:
        raise RuntimeError("An authenticated account is required")
    return int(value)


@event.listens_for(Session, "do_orm_execute")
def _scope_reads(state: ORMExecuteState) -> None:
    if not state.is_select:
        return
    owner = state.session.info.get("account_id", _current_account.get())
    if owner is None:
        # Auth and migration sessions deliberately have no rider-data access.
        for model in OWNED_MODELS:
            state.statement = state.statement.options(
                with_loader_criteria(model, lambda cls: cls.account_id == -1)
            )
        return
    for model in OWNED_MODELS:
        state.statement = state.statement.options(
            with_loader_criteria(model, lambda cls: cls.account_id == owner, include_aliases=True)
        )


@event.listens_for(Session, "before_flush")
def _scope_writes(session: Session, *_args: object) -> None:
    owner = session.info.get("account_id", _current_account.get())
    for row in session.new.union(session.dirty).union(session.deleted):
        if isinstance(row, OWNED_MODELS):
            if owner is None:
                raise RuntimeError("An authenticated account is required")
            if row in session.new and row.account_id is None:
                row.account_id = owner
            if isinstance(row, Activity) and row in session.new and row.garmin_id is None:
                # An explicitly assigned legacy ride ID is its Garmin ID.
                row.garmin_id = row.id
            if row.account_id != owner:
                raise PermissionError("Cross-account write refused")
        elif isinstance(row, LLMUsageRecord) and row in session.new and owner is not None:
            row.account_id = owner
