"""The hosted deployment only accepts requests that CloudFront stamped with
the shared X-Origin-Verify secret; locally (secret unset) it does nothing.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from soft_floyd_server.origin_verify import OriginVerifyMiddleware
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route


def _client() -> TestClient:
    async def ok(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/api/health", ok)])
    return TestClient(OriginVerifyMiddleware(app))


def test_noop_when_secret_unset(monkeypatch):
    monkeypatch.delenv("SOFT_FLOYD_ORIGIN_VERIFY_SECRET", raising=False)
    assert _client().get("/api/health").status_code == 200


def test_rejects_missing_or_wrong_header(monkeypatch):
    monkeypatch.setenv("SOFT_FLOYD_ORIGIN_VERIFY_SECRET", "s3cret")
    client = _client()
    assert client.get("/api/health").status_code == 403
    assert client.get("/api/health", headers={"X-Origin-Verify": "nope"}).status_code == 403


def test_allows_matching_header(monkeypatch):
    monkeypatch.setenv("SOFT_FLOYD_ORIGIN_VERIFY_SECRET", "s3cret")
    response = _client().get("/api/health", headers={"X-Origin-Verify": "s3cret"})
    assert response.status_code == 200


def test_allows_loopback_without_header(monkeypatch):
    monkeypatch.setenv("SOFT_FLOYD_ORIGIN_VERIFY_SECRET", "s3cret")

    async def ok(request):
        return PlainTextResponse("ok")

    app = OriginVerifyMiddleware(Starlette(routes=[Route("/api/health", ok)]))
    client = TestClient(app, client=("127.0.0.1", 50000))
    assert client.get("/api/health").status_code == 200
