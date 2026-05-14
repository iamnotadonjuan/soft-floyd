"""Retrieve relevant activity cards for RAG context."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from coach.log import log
from coach.rag.chunking import build_wellness_chunk
from coach.rag.embedder import _get_vector, serialize_f32
from coach.store.models import Activity, Embedding, WellnessDaily

if TYPE_CHECKING:
    from coach.config import Config

_SIMILARITY_TOP_K = 8
_PRE_FILTER_DAYS = 90
_DURATION_BUCKET_PCT = 0.20


@dataclass
class RetrievalContext:
    current_card: str
    similar_cards: list[str] = field(default_factory=list)
    recent_cards: list[str] = field(default_factory=list)
    wellness_summary: str = ""


def _pre_filter_ids(session: Session, activity: Activity) -> set[int]:
    """Return activity IDs to consider for vector search."""
    cutoff = activity.start_time - datetime.timedelta(days=_PRE_FILTER_DAYS)

    # Same bike_type, last 90 days
    recent = session.execute(
        select(Activity.id).where(
            Activity.bike_type == activity.bike_type,
            Activity.start_time >= cutoff,
            Activity.id != activity.id,
        )
    ).scalars()
    ids: set[int] = set(recent)

    # All-time top-5 by similar duration (±20%)
    low = activity.duration_s * (1 - _DURATION_BUCKET_PCT)
    high = activity.duration_s * (1 + _DURATION_BUCKET_PCT)
    similar_dur = session.execute(
        select(Activity.id)
        .where(
            Activity.duration_s.between(low, high),
            Activity.id != activity.id,
        )
        .limit(5)
    ).scalars()
    ids.update(similar_dur)

    return ids


def _vec_search(
    session: Session, query_vector: list[float], candidate_ids: set[int], k: int
) -> list[int]:
    """Return top-k embedding IDs from the vec table filtered to candidate_ids."""
    # Fetch more than k from vec, then filter in Python
    fetch_k = max(k * 4, 32)
    rows = session.execute(
        text(
            """
            SELECT ev.rowid, e.activity_id
            FROM embedding_vec ev
            JOIN embedding e ON ev.rowid = e.id
            WHERE ev.embedding MATCH :query AND k = :k
              AND e.chunk_type = 'summary'
              AND e.activity_id IS NOT NULL
            ORDER BY ev.distance
            """
        ),
        {"query": serialize_f32(query_vector), "k": fetch_k},
    ).fetchall()

    seen_acts: set[int] = set()
    result: list[int] = []
    for _rowid, act_id in rows:
        if act_id not in candidate_ids or act_id in seen_acts:
            continue
        seen_acts.add(act_id)
        result.append(act_id)
        if len(result) >= k:
            break
    return result


def _card_for_activity(session: Session, act_id: int) -> str | None:
    emb = session.execute(
        select(Embedding).where(
            Embedding.activity_id == act_id,
            Embedding.chunk_type == "summary",
        )
    ).scalar_one_or_none()
    return emb.text if emb else None


def _recent_activity_ids(session: Session, activity: Activity, n: int = 3) -> list[int]:
    rows = session.execute(
        select(Activity.id)
        .where(
            Activity.id != activity.id,
            Activity.start_time < activity.start_time,
        )
        .order_by(Activity.start_time.desc())
        .limit(n)
    ).scalars()
    return list(rows)


def _wellness_summary(session: Session, before: datetime.datetime) -> str:
    cutoff = (before - datetime.timedelta(days=7)).date()
    rows = list(
        session.execute(
            select(WellnessDaily).where(WellnessDaily.date >= cutoff).order_by(WellnessDaily.date)
        ).scalars()
    )
    return build_wellness_chunk(rows, cutoff)


def retrieve_for_activity(
    session: Session,
    cfg: Config,
    activity_id: int,
) -> RetrievalContext:
    """Build RetrievalContext for the given activity."""
    activity = session.get(Activity, activity_id)
    if activity is None:
        raise ValueError(f"Activity {activity_id} not found")

    # Current card (from DB or fresh build)
    current_emb = session.execute(
        select(Embedding).where(
            Embedding.activity_id == activity_id,
            Embedding.chunk_type == "summary",
        )
    ).scalar_one_or_none()

    if current_emb:
        current_card = current_emb.text
    else:
        from coach.rag.chunking import build_activity_card
        from coach.store.models import Lap, Metrics

        laps = list(session.execute(select(Lap).where(Lap.activity_id == activity_id)).scalars())
        metrics = session.get(Metrics, activity_id)
        wellness = session.get(WellnessDaily, activity.start_time.date())
        current_card = build_activity_card(activity, laps, metrics, wellness)

    # Similar cards via vec search
    similar_cards: list[str] = []
    if cfg.openai_api_key and current_emb:
        try:
            query_vec = _get_vector(cfg, current_card)
            candidate_ids = _pre_filter_ids(session, activity)
            if candidate_ids:
                top_ids = _vec_search(session, query_vec, candidate_ids, _SIMILARITY_TOP_K)
                for act_id in top_ids:
                    card = _card_for_activity(session, act_id)
                    if card:
                        similar_cards.append(card)
        except Exception as exc:
            log.warning("retriever.vec_search_failed", error=str(exc))

    # Recent cards (last 3 chronologically)
    recent_cards: list[str] = []
    for act_id in _recent_activity_ids(session, activity):
        card = _card_for_activity(session, act_id)
        if card:
            recent_cards.append(card)

    # Wellness summary (last 7 days)
    wellness_summary = _wellness_summary(session, activity.start_time)

    log.debug(
        "retriever.built",
        activity_id=activity_id,
        similar=len(similar_cards),
        recent=len(recent_cards),
    )
    return RetrievalContext(
        current_card=current_card,
        similar_cards=similar_cards,
        recent_cards=recent_cards,
        wellness_summary=wellness_summary,
    )
