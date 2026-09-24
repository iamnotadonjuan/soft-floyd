"""Durable notes the coach keeps about the rider.

The coach writes them through its `remember` tool; the rider reads and
deletes them in the web UI (and any MCP client can too). Every note is
injected into every coach turn, so both size and count are capped to keep
the prompt — and the bill — small.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from soft_floyd_core.models import CoachMemoryNote

MAX_NOTE_CHARS = 300
MAX_NOTES = 50


class MemoryNoteOut(BaseModel):
    id: int
    text: str
    created_at: dt.datetime


def _to_out(note: CoachMemoryNote) -> MemoryNoteOut:
    return MemoryNoteOut(id=note.id, text=note.text, created_at=note.created_at)


def list_notes(session: Session) -> list[MemoryNoteOut]:
    notes = session.scalars(select(CoachMemoryNote).order_by(CoachMemoryNote.id)).all()
    return [_to_out(n) for n in notes]


def add_note(session: Session, text: str) -> MemoryNoteOut:
    text = " ".join(text.split())
    if not text:
        raise ValueError("Memory note must not be empty")
    if len(text) > MAX_NOTE_CHARS:
        raise ValueError(f"Memory note must be at most {MAX_NOTE_CHARS} characters")
    existing = session.scalar(
        select(CoachMemoryNote).where(func.lower(CoachMemoryNote.text) == text.lower())
    )
    if existing is not None:
        return _to_out(existing)
    count = session.scalar(select(func.count(CoachMemoryNote.id))) or 0
    if count >= MAX_NOTES:
        raise ValueError(f"Coach memory is full ({MAX_NOTES} notes); delete one first")
    note = CoachMemoryNote(text=text)
    session.add(note)
    session.flush()
    return _to_out(note)


def delete_note(session: Session, note_id: int) -> None:
    note = session.get(CoachMemoryNote, note_id)
    if note is None:
        raise LookupError(f"Memory note {note_id} not found")
    session.delete(note)
    session.flush()
