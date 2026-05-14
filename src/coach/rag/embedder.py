"""OpenAI embedding creation and storage in embedding + embedding_vec."""

from __future__ import annotations

import datetime
import struct
from typing import TYPE_CHECKING

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from coach.log import log
from coach.rag.chunking import build_activity_card, build_wellness_chunk
from coach.store.models import Activity, Embedding, Lap, Metrics, WellnessDaily

if TYPE_CHECKING:
    from coach.config import Config

_EMBED_MODEL = "text-embedding-3-small"
_DIM = 1536


def serialize_f32(v: list[float]) -> bytes:
    return struct.pack(f"{len(v)}f", *v)


def _openai_client(cfg: Config):  # noqa: ANN201
    import openai

    return openai.OpenAI(api_key=cfg.openai_api_key or None)


def _get_vector(cfg: Config, text_input: str) -> list[float]:
    client = _openai_client(cfg)
    response = client.embeddings.create(model=_EMBED_MODEL, input=text_input)
    return response.data[0].embedding


def _insert_vec(session: Session, embedding_id: int, vector: list[float]) -> None:
    session.execute(
        text("INSERT INTO embedding_vec(rowid, embedding) VALUES (:id, :vec)"),
        {"id": embedding_id, "vec": serialize_f32(vector)},
    )


def embed_activity(session: Session, cfg: Config, activity_id: int) -> int | None:
    """Embed a single activity's summary card. Idempotent — skips if already embedded."""
    existing = session.execute(
        select(Embedding).where(
            Embedding.activity_id == activity_id,
            Embedding.chunk_type == "summary",
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id

    activity = session.get(Activity, activity_id)
    if activity is None:
        log.warning("embedder.activity_not_found", activity_id=activity_id)
        return None

    laps = list(session.execute(select(Lap).where(Lap.activity_id == activity_id)).scalars())
    metrics = session.get(Metrics, activity_id)
    wellness = session.get(WellnessDaily, activity.start_time.date())

    card = build_activity_card(activity, laps, metrics, wellness)

    if not cfg.openai_api_key:
        log.warning("embedder.no_openai_key", activity_id=activity_id)
        return None

    vector = _get_vector(cfg, card)

    emb = Embedding(
        activity_id=activity_id,
        chunk_type="summary",
        text=card,
    )
    session.add(emb)
    session.flush()  # populate emb.id

    _insert_vec(session, emb.id, vector)
    session.commit()

    log.info("embedder.activity_embedded", activity_id=activity_id, embedding_id=emb.id)
    return emb.id


def embed_weekly_wellness(session: Session, cfg: Config, week_start: datetime.date) -> int | None:
    """Embed a weekly wellness summary. Idempotent — skips if already embedded."""
    week_end = week_start + datetime.timedelta(days=7)

    # Check for existing wellness embedding covering this week
    existing = session.execute(
        select(Embedding).where(
            Embedding.chunk_type == "wellness",
            Embedding.text.like(f"Week of {week_start}%"),
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id

    rows = list(
        session.execute(
            select(WellnessDaily).where(
                WellnessDaily.date >= week_start,
                WellnessDaily.date < week_end,
            )
        ).scalars()
    )

    chunk = build_wellness_chunk(rows, week_start)

    if not cfg.openai_api_key:
        log.warning("embedder.no_openai_key_wellness", week_start=str(week_start))
        return None

    vector = _get_vector(cfg, chunk)

    emb = Embedding(
        activity_id=None,
        chunk_type="wellness",
        text=chunk,
    )
    session.add(emb)
    session.flush()

    _insert_vec(session, emb.id, vector)
    session.commit()

    log.info("embedder.wellness_embedded", week_start=str(week_start), embedding_id=emb.id)
    return emb.id
