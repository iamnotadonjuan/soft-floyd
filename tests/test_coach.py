"""Coach agent: scope guardrail, tool loop, memory, budget and sensor honesty."""

from __future__ import annotations

import datetime as dt
import json
import struct

import pytest
from fastmcp import Client
from pydantic import TypeAdapter
from soft_floyd_core.activities import service as activities_service
from soft_floyd_core.coach import memory
from soft_floyd_core.coach import service as coach
from soft_floyd_core.coach.guardrail import REFUSAL, classify_scope
from soft_floyd_core.coach.tools import run_tool
from soft_floyd_core.llm.client import (
    CHAT_MODEL,
    EMBEDDING_MODEL,
    ChatDone,
    TextDelta,
    ToolCall,
    Usage,
)
from soft_floyd_core.llm.usage import BudgetExceededError, month_to_date_cost
from soft_floyd_core.models import (
    Activity,
    Base,
    Bike,
    Book,
    BookPassage,
    CoachMessage,
    Lap,
    LLMUsageRecord,
    RiderProfile,
)
from soft_floyd_server.mcp_server import mcp
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

NOW = dt.datetime(2026, 9, 23, 12, 0)  # a Wednesday
CHAT_USAGE = Usage(CHAT_MODEL, 1000, 0, 100)


class FakeLLM:
    """Scripted stand-in for LLMClient: each chat_stream call pops one round."""

    def __init__(self, *, in_scope=True, rounds=None, scope_result=None):
        self.scope_result = scope_result if scope_result is not None else {"in_scope": in_scope}
        self.rounds = list(rounds or [])
        self.stream_calls: list[tuple[list, list | None]] = []
        self.json_calls: list[list] = []

    async def chat_json(self, messages, schema_name, schema):
        self.json_calls.append(messages)
        return self.scope_result, Usage(CHAT_MODEL, 120, 0, 5)

    async def chat_stream(self, messages, tools=None):
        self.stream_calls.append((json.loads(json.dumps(messages)), tools))
        for item in self.rounds.pop(0):
            yield item

    async def embed(self, text):
        return [1.0, 0.0], Usage(EMBEDDING_MODEL, 10, 0, 0)


def _text_round(*parts):
    return [*(TextDelta(p) for p in parts), ChatDone(usage=CHAT_USAGE)]


def _seed(session, *, power_bike=False):
    session.add(RiderProfile(id=1, goal_text="Ride a 150 km gran fondo", has_hr_monitor=True))
    session.add(Bike(nickname="Road", kind="road", is_primary=True, has_power_meter=power_bike))
    session.commit()


def _seed_book(session):
    book = Book(sha256="b" * 64, title="Training Book", source_name="book.pdf")
    session.add(book)
    session.flush()
    session.add(
        BookPassage(
            book_id=book.id,
            ordinal=0,
            page_start=12,
            page_end=12,
            text="Long endurance rides build aerobic fitness.",
            embedding=struct.pack("<2f", 1.0, 0.0),
        )
    )
    session.commit()


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


async def _run(session, conversation_id, text, llm, budget=10.0):
    return [e async for e in coach.run_turn(session, conversation_id, text, llm, budget, now=NOW)]


def _usage_rows(session):
    return session.scalar(select(func.count(LLMUsageRecord.id)))


async def test_off_topic_message_is_refused_without_calling_the_coach_model(session):
    _seed(session)
    conv = coach.create_conversation(session)
    llm = FakeLLM(in_scope=False)

    events = await _run(session, conv.id, "Write me a Python script to sort a list", llm)

    assert [e.type for e in events] == ["delta", "done"]
    assert events[0].text == REFUSAL
    assert llm.stream_calls == []
    assert _usage_rows(session) == 1  # only the classifier
    detail = coach.get_conversation(session, conv.id)
    assert [m.role for m in detail.messages] == ["user", "assistant"]
    assert detail.messages[1].content == REFUSAL


async def test_classifier_fails_closed_on_unexpected_output():
    in_scope, _ = await classify_scope(FakeLLM(scope_result={}), "hello", None)
    assert in_scope is False
    in_scope, _ = await classify_scope(FakeLLM(scope_result={"in_scope": "yes"}), "hi", None)
    assert in_scope is False


async def test_follow_up_passes_previous_reply_to_the_classifier(session):
    _seed(session)
    conv = coach.create_conversation(session)
    await _run(session, conv.id, "How was my week?", FakeLLM(rounds=[_text_round("Solid week.")]))

    llm = FakeLLM(rounds=[_text_round("Because volume went up.")])
    await _run(session, conv.id, "why?", llm)

    classifier_input = llm.json_calls[0][1]["content"]
    assert "<coach_previous_reply>Solid week.</coach_previous_reply>" in classifier_input
    assert "<message>why?</message>" in classifier_input
    # History reaches the coach model too.
    sent = llm.stream_calls[0][0]
    assert {"role": "assistant", "content": "Solid week."} in sent


async def test_tool_loop_uses_core_data_saves_memory_and_cites_books(session):
    _seed(session)
    _seed_book(session)
    session.add(
        Activity(
            id=7,
            start_time=dt.datetime(2026, 9, 21, 8),
            bike_type="road",
            duration_s=7200,
            distance_m=60000,
            fit_status="ok",
            has_hr_data=True,
            avg_hr=140,
        )
    )
    session.commit()
    conv = coach.create_conversation(session)
    llm = FakeLLM(
        rounds=[
            [
                ChatDone(
                    usage=CHAT_USAGE,
                    tool_calls=[
                        ToolCall("c1", "get_training_summary", '{"weeks": 4}'),
                        ToolCall("c2", "remember", '{"note": "Knee hurts on long climbs."}'),
                        ToolCall("c3", "search_training_books", '{"query": "endurance"}'),
                    ],
                )
            ],
            _text_round("Per Training Book (p. 12), ", "keep building long rides."),
        ]
    )

    events = await _run(session, conv.id, "How do I get ready for my fondo? My knee hurts", llm)

    types = [e.type for e in events]
    assert types.count("tool_status") == 3
    assert types[-2:] == ["sources", "done"]
    assert events[-2].sources[0].title == "Training Book"
    assert events[-1].message.content == "Per Training Book (p. 12), keep building long rides."

    # First call offers tools and carries rider context; second sees tool results.
    first_messages, first_tools = llm.stream_calls[0]
    assert first_tools is not None
    assert "Ride a 150 km gran fondo" in first_messages[1]["content"]
    second_messages, _ = llm.stream_calls[1]
    tool_msgs = [m for m in second_messages if m["role"] == "tool"]
    assert len(tool_msgs) == 3
    summary = json.loads(tool_msgs[0]["content"])
    assert summary["total_rides"] == 1 and len(summary["weeks"]) == 4

    assert [n.text for n in memory.list_notes(session)] == ["Knee hurts on long climbs."]
    # classifier + 2 chat rounds + 1 query embedding
    assert _usage_rows(session) == 4
    saved = coach.get_conversation(session, conv.id)
    assert saved.title == "How do I get ready for my fondo? My knee hurts"
    assert saved.messages[1].sources[0].page_start == 12


async def test_memory_notes_are_injected_into_the_next_turn(session):
    _seed(session)
    memory.add_note(session, "Prefers morning rides.")
    conv = coach.create_conversation(session)
    llm = FakeLLM(rounds=[_text_round("Ok.")])
    await _run(session, conv.id, "Plan my week", llm)
    assert "Prefers morning rides." in llm.stream_calls[0][0][1]["content"]


async def test_last_round_withholds_tools_to_force_an_answer(session):
    _seed(session)
    conv = coach.create_conversation(session)
    looping = [ChatDone(usage=CHAT_USAGE, tool_calls=[ToolCall("x", "get_rider_profile", "{}")])]
    llm = FakeLLM(rounds=[looping] * 4 + [_text_round("Here is my answer.")])

    events = await _run(session, conv.id, "Analyze everything", llm)

    assert len(llm.stream_calls) == 5
    assert llm.stream_calls[-1][1] is None
    assert events[-1].message.content == "Here is my answer."


async def test_budget_guard_blocks_new_turns(session):
    _seed(session)
    conv = coach.create_conversation(session)
    session.add(
        LLMUsageRecord(
            model=CHAT_MODEL, prompt_tokens=1, cached_tokens=0, completion_tokens=1, cost_usd=10.0
        )
    )
    session.commit()
    assert month_to_date_cost(session) == pytest.approx(10.0)
    with pytest.raises(BudgetExceededError):
        coach.check_turn(session, conv.id, "How was my ride?", 10.0)
    with pytest.raises(BudgetExceededError):
        await _run(session, conv.id, "How was my ride?", FakeLLM(), budget=10.0)
    assert session.scalar(select(func.count(CoachMessage.id))) == 0


def test_check_turn_rejects_empty_long_and_unknown(session):
    _seed(session)
    conv = coach.create_conversation(session)
    with pytest.raises(ValueError):
        coach.check_turn(session, conv.id, "   ", 10.0)
    with pytest.raises(ValueError):
        coach.check_turn(session, conv.id, "x" * (coach.MAX_MESSAGE_CHARS + 1), 10.0)
    with pytest.raises(LookupError):
        coach.check_turn(session, 999, "hi", 10.0)


def test_memory_dedupes_caps_and_validates(session):
    first = memory.add_note(session, "Has a 90 minute weekday limit.")
    assert memory.add_note(session, "has a 90 minute  weekday limit.").id == first.id
    with pytest.raises(ValueError):
        memory.add_note(session, "  ")
    with pytest.raises(ValueError):
        memory.add_note(session, "x" * (memory.MAX_NOTE_CHARS + 1))
    for i in range(memory.MAX_NOTES - 1):
        memory.add_note(session, f"note {i}")
    with pytest.raises(ValueError, match="full"):
        memory.add_note(session, "one too many")
    memory.delete_note(session, first.id)
    with pytest.raises(LookupError):
        memory.delete_note(session, first.id)


def test_training_summary_only_averages_verified_streams(session):
    _seed(session)  # no power meter in the garage
    session.add_all(
        [
            Activity(
                id=1,
                start_time=dt.datetime(2026, 9, 22, 7),
                duration_s=3600,
                distance_m=30000,
                fit_status="ok",
                has_hr_data=True,
                avg_hr=150,
                avg_power_w=200,  # Garmin estimate; no verified power stream
            ),
            Activity(
                id=2,
                start_time=dt.datetime(2026, 9, 21, 7),
                duration_s=3600,
                distance_m=20000,
                fit_status="download_failed",
                avg_hr=170,  # summary-only; FIT never verified it
            ),
            Activity(id=3, start_time=dt.datetime(2026, 6, 1), duration_s=100),  # out of range
        ]
    )
    session.commit()

    summary = activities_service.get_training_summary(session, 2, now=NOW)

    assert [w.week_start for w in summary.weeks] == [dt.date(2026, 9, 14), dt.date(2026, 9, 21)]
    current = summary.weeks[1]
    assert current.rides == 2 and current.distance_km == 50.0
    assert current.avg_hr == 150 and current.hr_rides == 1
    assert current.avg_power_w is None and current.power_rides == 0
    assert summary.total_rides == 2
    assert "no usable FIT data" in summary.data_note
    assert "No verified power data" in summary.data_note


async def test_get_ride_tool_hides_unverified_lap_power(session):
    _seed(session)
    session.add(
        Activity(
            id=9,
            start_time=dt.datetime(2026, 9, 20, 7),
            fit_status="ok",
            has_hr_data=True,
            avg_hr=140,
            avg_power_w=210,
        )
    )
    session.add(Lap(activity_id=9, lap_index=0, avg_hr=138, avg_power_w=205))
    session.commit()

    result = await run_tool(session, "get_ride", '{"activity_id": 9}', None)
    payload = json.loads(result.content)

    assert payload["ride"]["avg_power_w"] is None
    assert payload["laps"][0]["avg_power_w"] is None
    assert payload["laps"][0]["avg_hr"] == 138


async def test_tool_errors_go_back_to_the_model(session):
    _seed(session)
    bad_json = await run_tool(session, "get_ride", "{not json", None)
    assert "error" in json.loads(bad_json.content)
    missing = await run_tool(session, "forget", '{"note_id": 42}', None)
    assert "not found" in json.loads(missing.content)["error"]
    unknown = await run_tool(session, "send_email", "{}", None)
    assert "Unknown tool" in json.loads(unknown.content)["error"]


def _shared_factory(monkeypatch):
    from soft_floyd_server import http_api, mcp_server

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        _seed(db)
    monkeypatch.setattr(http_api, "get_session_factory", lambda: factory)
    monkeypatch.setattr(mcp_server, "get_session_factory", lambda: factory)
    return engine, factory


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_rest_streams_a_coach_turn_and_persists_it(client, monkeypatch):
    engine, _ = _shared_factory(monkeypatch)
    llm = FakeLLM(rounds=[_text_round("Ride ", "easy today.")])
    monkeypatch.setattr(coach, "make_coach_llm", lambda _key: llm)
    try:
        conv = client.post("/api/coach/conversations").json()
        response = client.post(
            f"/api/coach/conversations/{conv['id']}/messages", json={"text": "What today?"}
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(response.text)
        assert [name for name, _ in events] == ["delta", "delta", "done"]
        assert events[-1][1]["message"]["content"] == "Ride easy today."

        detail = client.get(f"/api/coach/conversations/{conv['id']}").json()
        assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
        assert client.get("/api/coach/conversations").json()[0]["title"] == "What today?"

        assert (
            client.post("/api/coach/conversations/999/messages", json={"text": "hi"}).status_code
            == 404
        )
        empty = client.post(f"/api/coach/conversations/{conv['id']}/messages", json={"text": " "})
        assert empty.status_code == 400

        assert client.delete(f"/api/coach/conversations/{conv['id']}").status_code == 204
        assert client.get(f"/api/coach/conversations/{conv['id']}").status_code == 404
    finally:
        engine.dispose()


def test_rest_requires_an_api_key(client, monkeypatch):
    engine, _ = _shared_factory(monkeypatch)
    monkeypatch.setenv("SOFT_FLOYD_OPENAI_API_KEY", "")
    try:
        conv = client.post("/api/coach/conversations").json()
        response = client.post(
            f"/api/coach/conversations/{conv['id']}/messages", json={"text": "hi"}
        )
        assert response.status_code == 400
        assert "OPENAI_API_KEY" in response.json()["detail"]
    finally:
        engine.dispose()


def test_rest_reports_budget_exhaustion(client, monkeypatch):
    engine, factory = _shared_factory(monkeypatch)
    monkeypatch.setattr(coach, "make_coach_llm", lambda _key: FakeLLM())
    monkeypatch.setenv("SOFT_FLOYD_LLM_MONTHLY_BUDGET_USD", "0.5")
    with factory() as db:
        db.add(
            LLMUsageRecord(
                model=CHAT_MODEL, prompt_tokens=1, cached_tokens=0, completion_tokens=1, cost_usd=1
            )
        )
        db.commit()
    try:
        conv = client.post("/api/coach/conversations").json()
        response = client.post(
            f"/api/coach/conversations/{conv['id']}/messages", json={"text": "hi"}
        )
        assert response.status_code == 402
        assert "budget" in response.json()["detail"]
    finally:
        engine.dispose()


async def test_mcp_and_rest_agree_on_memory_and_training_summary(client, monkeypatch):
    engine, factory = _shared_factory(monkeypatch)
    with factory() as db:
        db.add(Activity(id=5, start_time=dt.datetime.now() - dt.timedelta(days=1), distance_m=1000))
        db.commit()
    try:
        async with Client(mcp) as mcp_client:
            added = await mcp_client.call_tool("add_coach_memory", {"note": "Rides a gravel bike."})
            listed = await mcp_client.call_tool("list_coach_memory", {})
            summary = await mcp_client.call_tool("get_training_summary", {"weeks": 3})

        def dump(result):
            return TypeAdapter(type(result.data)).dump_python(result.data, mode="json")

        rest_memory = client.get("/api/coach/memory").json()
        assert rest_memory == dump(listed)
        assert rest_memory[0]["text"] == dump(added)["text"] == "Rides a gravel bike."
        assert client.get("/api/training-summary", params={"weeks": 3}).json() == dump(summary)

        assert client.delete(f"/api/coach/memory/{rest_memory[0]['id']}").status_code == 204
        async with Client(mcp) as mcp_client:
            assert dump(await mcp_client.call_tool("list_coach_memory", {})) == []
    finally:
        engine.dispose()
