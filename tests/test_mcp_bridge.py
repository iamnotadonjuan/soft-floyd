"""Regression tests for FastMCP's structured tool responses."""

from types import SimpleNamespace

from pydantic import BaseModel
from soft_floyd_server.mcp_bridge import _tool_result


class _RootSource(BaseModel):
    book_id: int
    title: str
    author: str | None
    page_start: int
    page_end: int


class _RootResult(BaseModel):
    content: str
    status: str
    sources: list[_RootSource]
    training_session_ids: list[int]


def test_tool_result_accepts_fastmcp_pydantic_sources():
    source = _RootSource(
        book_id=3,
        title="Training book",
        author="Coach",
        page_start=42,
        page_end=43,
    )
    data = _RootResult(
        content='{"passages": []}',
        status="Checking your training books",
        sources=[source],
        training_session_ids=[],
    )

    result = _tool_result(SimpleNamespace(data=data, structured_content=None))

    assert result.sources[0].book_id == 3
    assert result.sources[0].page_start == 42
    assert result.content == '{"passages": []}'


def test_tool_result_prefers_structured_content_mappings():
    response = SimpleNamespace(
        data=None,
        structured_content={
            "content": "{}",
            "status": "Checking your training books",
            "sources": [
                {
                    "book_id": 3,
                    "title": "Training book",
                    "author": None,
                    "page_start": 42,
                    "page_end": 43,
                }
            ],
            "training_session_ids": [7],
        },
    )

    result = _tool_result(response)

    assert result.sources[0].title == "Training book"
    assert result.training_session_ids == [7]
