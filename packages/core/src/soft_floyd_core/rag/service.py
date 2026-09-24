"""PDF ingestion, exact semantic search, and sensor-honest ride context."""

from __future__ import annotations

import hashlib
import math
import re
import struct
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from soft_floyd_core.activities.service import available_metrics_for_activity
from soft_floyd_core.llm.client import LLMClient, Usage
from soft_floyd_core.models import Activity, Book, BookPassage, LLMUsageRecord
from soft_floyd_core.profile.service import get_profile

_CHUNK_WORDS = 220
_OVERLAP_WORDS = 40
_TOP_K = 5


class Embedder(Protocol):
    async def embed(self, text: str) -> tuple[list[float], Usage]: ...


def make_embedder(api_key: str | None) -> Embedder | None:
    return LLMClient(api_key) if api_key else None


class ImportResult(BaseModel):
    book_id: int
    passages: int
    already_imported: bool
    resumed_from: int = 0


class PassageOut(BaseModel):
    book_id: int
    title: str
    author: str | None
    page_start: int
    page_end: int
    text: str


class RideContextOut(BaseModel):
    activity_id: int
    start_time: str
    bike_type: str
    duration_s: float
    distance_m: float
    elev_gain_m: float
    avg_hr: int | None
    max_hr: int | None
    avg_power_w: int | None
    avg_cadence: int | None
    sensors_present: list[str]
    available_metrics: list[str]
    data_note: str | None


class TrainingContextOut(BaseModel):
    query: str
    goal_text: str
    primary_discipline: str | None
    ride: RideContextOut | None
    passages: list[PassageOut]


def _pack(vector: list[float]) -> bytes:
    if not vector or not all(math.isfinite(v) for v in vector):
        raise ValueError("Embedding must contain finite values")
    return struct.pack(f"<{len(vector)}f", *vector)


def _unpack(blob: bytes) -> tuple[float, ...]:
    if len(blob) % 4:
        raise ValueError("Stored embedding has invalid length")
    return struct.unpack(f"<{len(blob) // 4}f", blob)


def _similarity(query: list[float], blob: bytes) -> float:
    stored = _unpack(blob)
    if len(query) != len(stored):
        raise ValueError("Stored embedding dimension differs from the current model")
    dot = sum(a * b for a, b in zip(query, stored, strict=True))
    qnorm = math.sqrt(sum(v * v for v in query))
    snorm = math.sqrt(sum(v * v for v in stored))
    return dot / (qnorm * snorm) if qnorm and snorm else -1.0


def _chunks(path: Path) -> list[tuple[int, str]]:
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are not supported")
        pages = [page.extract_text() or "" for page in reader.pages]
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Could not read PDF: {exc}") from exc

    chunks = []
    for page_number, raw_text in enumerate(pages, start=1):
        words = re.sub(r"\s+", " ", raw_text).strip().split()
        if not words:
            continue
        step = _CHUNK_WORDS - _OVERLAP_WORDS
        for start in range(0, len(words), step):
            part = words[start : start + _CHUNK_WORDS]
            # A tiny tail is more useful attached to the previous chunk.
            if chunks and start and len(part) < _OVERLAP_WORDS:
                break
            chunks.append((page_number, " ".join(part)))
            if start + _CHUNK_WORDS >= len(words):
                break
    if not chunks:
        raise ValueError("PDF contains no selectable text; OCR is not supported yet")
    return chunks


def _record_usage(session: Session, usage: Usage) -> None:
    session.add(
        LLMUsageRecord(
            model=usage.model,
            prompt_tokens=usage.prompt_tokens,
            cached_tokens=usage.cached_tokens,
            completion_tokens=usage.completion_tokens,
            cost_usd=usage.cost_usd,
        )
    )


async def import_pdf(
    session: Session,
    path: Path,
    title: str,
    author: str | None,
    embedder: Embedder,
    progress: Callable[[int, int], None] | None = None,
) -> ImportResult:
    if not path.is_file() or path.suffix.lower() != ".pdf":
        raise ValueError("Provide an existing PDF file")
    if not title.strip():
        raise ValueError("Book title must not be empty")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    existing = session.scalar(select(Book).where(Book.sha256 == digest))
    if existing is not None and existing.import_status == "complete":
        count = len(
            session.scalars(select(BookPassage.id).where(BookPassage.book_id == existing.id)).all()
        )
        return ImportResult(book_id=existing.id, passages=count, already_imported=True)

    chunks = _chunks(path)
    if existing is None:
        book = Book(
            sha256=digest,
            title=title.strip(),
            author=author,
            source_name=path.name,
            import_status="importing",
        )
        session.add(book)
        session.commit()
    else:
        book = existing

    saved = session.scalars(
        select(BookPassage).where(BookPassage.book_id == book.id).order_by(BookPassage.ordinal)
    ).all()
    for ordinal, passage in enumerate(saved):
        if (
            ordinal >= len(chunks)
            or passage.ordinal != ordinal
            or (passage.page_start, passage.text) != chunks[ordinal]
        ):
            raise ValueError("Saved import differs from current PDF chunking; cannot resume")

    resumed_from = len(saved)
    if progress is not None:
        progress(resumed_from, len(chunks))
    for ordinal in range(resumed_from, len(chunks)):
        page, text = chunks[ordinal]
        vector, usage = await embedder.embed(text)
        _record_usage(session, usage)
        session.add(
            BookPassage(
                book_id=book.id,
                ordinal=ordinal,
                page_start=page,
                page_end=page,
                text=text,
                embedding=_pack(vector),
            )
        )
        session.commit()
        if progress is not None:
            progress(ordinal + 1, len(chunks))
    book.import_status = "complete"
    session.commit()
    return ImportResult(
        book_id=book.id,
        passages=len(chunks),
        already_imported=False,
        resumed_from=resumed_from,
    )


def _ride_context(session: Session, activity: Activity) -> RideContextOut:
    allowed = available_metrics_for_activity(session, activity)
    verified = activity.fit_status == "ok"
    sensors = []
    for name in ("power", "hr", "cadence", "speed", "gps"):
        if verified and getattr(activity, f"has_{name}_data"):
            sensors.append(name)
    return RideContextOut(
        activity_id=activity.id,
        start_time=activity.start_time.isoformat(),
        bike_type=activity.bike_type,
        duration_s=activity.duration_s,
        distance_m=activity.distance_m,
        elev_gain_m=activity.elev_gain_m,
        avg_hr=activity.avg_hr if "hr" in sensors and "hr_zones" in allowed else None,
        max_hr=activity.max_hr if "hr" in sensors and "hr_zones" in allowed else None,
        avg_power_w=(
            activity.avg_power_w if "power" in sensors and "normalized_power" in allowed else None
        ),
        avg_cadence=(
            activity.avg_cadence
            if "cadence" in sensors and "cadence_distribution" in allowed
            else None
        ),
        sensors_present=sensors,
        available_metrics=allowed,
        data_note=(
            "FIT data unavailable; only Garmin summary fields are shown."
            if not verified
            else "Power data unavailable on this ride."
            if "power" not in sensors
            else None
        ),
    )


async def get_training_context(
    session: Session, query: str, embedder: Embedder | None, activity_id: int | None = None
) -> TrainingContextOut:
    query = query.strip()
    if not query:
        raise ValueError("Query must not be empty")

    profile = get_profile(session)
    if activity_id is None:
        activity = session.scalar(
            select(Activity).order_by(Activity.start_time.desc(), Activity.id.desc())
        )
    else:
        activity = session.get(Activity, activity_id)
        if activity is None:
            raise LookupError(f"Activity {activity_id} not found")

    passages: list[PassageOut] = []
    rows = session.execute(
        select(BookPassage, Book)
        .join(Book, Book.id == BookPassage.book_id)
        .where(Book.import_status == "complete")
    ).all()
    if rows:
        if embedder is None:
            raise ValueError("SOFT_FLOYD_OPENAI_API_KEY is required for book search")
        vector, usage = await embedder.embed(query)
        _record_usage(session, usage)
        session.commit()
        ranked = sorted(
            rows,
            key=lambda row: _similarity(vector, row[0].embedding),
            reverse=True,
        )
        passages = [
            PassageOut(
                book_id=book.id,
                title=book.title,
                author=book.author,
                page_start=passage.page_start,
                page_end=passage.page_end,
                text=passage.text,
            )
            for passage, book in ranked[:_TOP_K]
        ]

    return TrainingContextOut(
        query=query,
        goal_text=profile.goal_text,
        primary_discipline=profile.primary_discipline,
        ride=_ride_context(session, activity) if activity else None,
        passages=passages,
    )
