"""Book retrieval and ride context use local data with verifiable citations."""

from __future__ import annotations

import datetime as dt
import hashlib
import struct

import pytest
from fastmcp import Client
from pydantic import TypeAdapter
from soft_floyd_core.db import make_engine
from soft_floyd_core.llm.client import EMBEDDING_MODEL, Usage
from soft_floyd_core.models import (
    Activity,
    Base,
    Book,
    BookPassage,
    LLMUsageRecord,
    RiderProfile,
)
from soft_floyd_core.rag import service as rag
from soft_floyd_server.mcp_server import mcp
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from typer.testing import CliRunner


def _seed_power_profile(session):
    """Support the concurrent garage refactor while this commit stays independent."""
    if "has_power_meter" in RiderProfile.__table__.columns:
        session.add(RiderProfile(id=1, has_hr_monitor=True, has_power_meter=True))
    else:
        from soft_floyd_core.models import Bike

        session.add(RiderProfile(id=1, has_hr_monitor=True))
        session.add(Bike(nickname="Road", kind="road", is_primary=True, has_power_meter=True))


def _seed_basic_profile(session, *, goal_text=""):
    session.add(RiderProfile(id=1, goal_text=goal_text))
    if "has_power_meter" not in RiderProfile.__table__.columns:
        from soft_floyd_core.models import Bike

        session.add(Bike(nickname="Road", kind="road", is_primary=True))


class FakeEmbedder:
    calls = 0

    async def embed(self, text):
        self.calls += 1
        vector = [1.0, 0.0] if "endurance" in text.lower() else [0.0, 1.0]
        return vector, Usage(EMBEDDING_MODEL, 10, 0, 0)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


def test_book_tables_are_created_by_alembic(tmp_path):
    engine = make_engine(tmp_path / "rag.db")
    try:
        assert {"book", "book_passage", "llm_usage"} <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_books_import_cli_uses_core_import(tmp_path, monkeypatch):
    from soft_floyd_server.cli import app

    class Page:
        def extract_text(self):
            return "Endurance training in a small local book."

    class Reader:
        is_encrypted = False
        pages = [Page()]

    monkeypatch.setattr(rag, "PdfReader", lambda _: Reader())
    monkeypatch.setattr(rag, "make_embedder", lambda _key: FakeEmbedder())
    monkeypatch.setenv("SOFT_FLOYD_DB_PATH", str(tmp_path / "cli.db"))
    path = tmp_path / "training.pdf"
    path.write_bytes(b"PDF fixture")

    result = CliRunner().invoke(app, ["books", "import", str(path), "--title", "Training"])
    assert result.exit_code == 0, result.output
    assert "Imported book" in result.output


def test_rest_context_works_before_books_or_rides_exist(client):
    response = client.get("/api/training-context", params={"query": "endurance"})
    assert response.status_code == 200
    assert response.json()["passages"] == []
    assert response.json()["ride"] is None
    missing = client.get("/api/training-context", params={"query": "endurance", "activity_id": 9})
    assert missing.status_code == 404


async def test_pdf_import_citations_idempotency_and_semantic_ranking(
    session, tmp_path, monkeypatch
):
    class Page:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class Reader:
        is_encrypted = False
        pages = [Page("Endurance rides build aerobic fitness."), Page("Sprint training is brief.")]

    monkeypatch.setattr(rag, "PdfReader", lambda _: Reader())
    path = tmp_path / "owned.pdf"
    path.write_bytes(b"a PDF fixture")
    embedder = FakeEmbedder()

    imported = await rag.import_pdf(session, path, "Training Book", "Coach", embedder)
    session.commit()
    again = await rag.import_pdf(session, path, "Different title", None, embedder)
    assert imported.passages == 2
    assert again.already_imported and again.book_id == imported.book_id
    assert embedder.calls == 2
    assert session.scalar(select(func.count()).select_from(LLMUsageRecord)) == 2

    context = await rag.get_training_context(session, "endurance advice", embedder)
    assert context.passages[0].title == "Training Book"
    assert context.passages[0].page_start == context.passages[0].page_end == 1
    assert context.ride is None
    assert session.scalar(select(func.count()).select_from(LLMUsageRecord)) == 3


async def test_textless_pdf_rejected_before_embedding(session, tmp_path, monkeypatch):
    class Reader:
        is_encrypted = False
        pages = [type("Page", (), {"extract_text": lambda self: ""})()]

    monkeypatch.setattr(rag, "PdfReader", lambda _: Reader())
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"scan")
    embedder = FakeEmbedder()
    with pytest.raises(ValueError, match="no selectable text"):
        await rag.import_pdf(session, path, "Scan", None, embedder)
    assert embedder.calls == 0


async def test_partial_embedding_failure_resumes_without_reembedding(
    session, tmp_path, monkeypatch
):
    class Page:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class Reader:
        is_encrypted = False
        pages = [Page("Endurance training"), Page("Sprint training")]

    class FailingEmbedder(FakeEmbedder):
        async def embed(self, text):
            if "Sprint" in text:
                raise RuntimeError("embedding service unavailable")
            return await super().embed(text)

    monkeypatch.setattr(rag, "PdfReader", lambda _: Reader())
    path = tmp_path / "book.pdf"
    path.write_bytes(b"book")
    with pytest.raises(RuntimeError, match="unavailable"):
        await rag.import_pdf(session, path, "Book", None, FailingEmbedder())
    assert session.scalar(select(func.count()).select_from(LLMUsageRecord)) == 1
    book = session.scalar(select(Book))
    assert book.import_status == "importing"
    assert session.scalar(select(func.count()).select_from(BookPassage)) == 1

    # An unfinished book must not leak into search results.
    before = await rag.get_training_context(session, "endurance", FakeEmbedder())
    assert before.passages == []

    retry_embedder = FakeEmbedder()
    resumed = await rag.import_pdf(session, path, "Ignored title", None, retry_embedder)
    assert resumed.resumed_from == 1
    assert resumed.passages == 2
    assert retry_embedder.calls == 1
    assert book.import_status == "complete"
    assert session.scalar(select(func.count()).select_from(LLMUsageRecord)) == 2
    ordinals = session.scalars(select(BookPassage.ordinal).order_by(BookPassage.ordinal)).all()
    assert ordinals == [0, 1]


async def test_resume_rejects_changed_chunking(session, tmp_path, monkeypatch):
    class Page:
        def extract_text(self):
            return "Different extracted text"

    class Reader:
        is_encrypted = False
        pages = [Page()]

    path = tmp_path / "book.pdf"
    path.write_bytes(b"book")
    book = Book(
        sha256=hashlib.sha256(b"book").hexdigest(),
        title="Book",
        source_name="book.pdf",
        import_status="importing",
    )
    session.add(book)
    session.flush()
    session.add(
        BookPassage(
            book_id=book.id,
            ordinal=0,
            page_start=1,
            page_end=1,
            text="Old text",
            embedding=struct.pack("<2f", 1.0, 0.0),
        )
    )
    session.commit()
    monkeypatch.setattr(rag, "PdfReader", lambda _: Reader())

    with pytest.raises(ValueError, match="differs from current PDF chunking"):
        await rag.import_pdf(session, path, "Book", None, FakeEmbedder())


async def test_latest_ride_context_hides_unverified_power_and_failed_fit(session):
    _seed_power_profile(session)
    older = Activity(
        id=1,
        start_time=dt.datetime(2026, 1, 1),
        bike_type="road",
        fit_status="ok",
        has_power_data=True,
        avg_power_w=200,
    )
    newest = Activity(
        id=2,
        start_time=dt.datetime(2026, 1, 2),
        bike_type="road",
        fit_status="ok",
        has_power_data=False,
        has_hr_data=True,
        avg_power_w=250,
        avg_hr=145,
    )
    session.add_all([older, newest])
    session.commit()

    context = await rag.get_training_context(session, "endurance", None)
    assert context.ride.activity_id == 2
    assert context.ride.avg_hr == 145
    assert context.ride.avg_power_w is None
    assert "Power data unavailable" in context.ride.data_note

    newest.fit_status = "parse_failed"
    session.commit()
    failed = await rag.get_training_context(session, "endurance", None)
    assert failed.ride.avg_hr is None
    assert failed.ride.sensors_present == []
    assert "FIT data unavailable" in failed.ride.data_note


async def test_mcp_and_rest_return_same_training_context(client, monkeypatch):
    from soft_floyd_server import http_api, mcp_server

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        _seed_basic_profile(db, goal_text="Finish a long ride")
        db.add(Activity(id=4, start_time=dt.datetime(2026, 1, 2), bike_type="road"))
        book = Book(sha256="a" * 64, title="Training Book", source_name="book.pdf")
        db.add(book)
        db.flush()
        db.add(
            BookPassage(
                book_id=book.id,
                page_start=5,
                page_end=5,
                text="Endurance riding builds aerobic fitness.",
                embedding=struct.pack("<2f", 1.0, 0.0),
            )
        )
        db.commit()

    monkeypatch.setattr(http_api, "get_session_factory", lambda: factory)
    monkeypatch.setattr(mcp_server, "get_session_factory", lambda: factory)
    monkeypatch.setattr(rag, "make_embedder", lambda _key: FakeEmbedder())
    try:
        rest = client.get("/api/training-context", params={"query": "endurance"}).json()
        async with Client(mcp) as mcp_client:
            result = await mcp_client.call_tool("get_training_context", {"query": "endurance"})
        assert TypeAdapter(type(result.data)).dump_python(result.data, mode="json") == rest
        assert rest["ride"]["activity_id"] == 4
        assert rest["passages"][0]["page_start"] == 5
    finally:
        engine.dispose()
