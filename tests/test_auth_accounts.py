"""Authentication boundary and two-account isolation across rider surfaces."""

from __future__ import annotations

import asyncio
import datetime as dt
from urllib.parse import parse_qs, urlparse

import httpx2
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from soft_floyd_core.account_scope import scoped_account
from soft_floyd_core.auth import service as auth_service
from soft_floyd_core.auth.service import Identity, create_session, issue_mcp_token
from soft_floyd_core.config import get_settings
from soft_floyd_core.db import session_scope
from soft_floyd_core.models import Account, Activity, CoachMemoryNote
from soft_floyd_server.runtime import get_session_factory


def test_google_identity_checks_signature_claims_and_nonce(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class FakeJWKClient:
        def __init__(self, _url):
            pass

        def get_signing_key_from_jwt(self, _token):
            return type("Key", (), {"key": key.public_key()})()

    monkeypatch.setattr(auth_service, "PyJWKClient", FakeJWKClient)
    claims = {
        "sub": "google-123",
        "email": "rider@example.com",
        "email_verified": True,
        "name": "Rider",
        "nonce": "expected",
        "iss": "https://accounts.google.com",
        "aud": "client-123",
        "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
    }
    raw = jwt.encode(claims, key, algorithm="RS256")
    assert auth_service.verify_google_id_token(raw, "client-123", "expected").sub == "google-123"
    with pytest.raises(auth_service.InvalidCredentials):
        auth_service.verify_google_id_token(raw, "client-123", "wrong")
    with pytest.raises(auth_service.InvalidCredentials):
        auth_service.verify_google_id_token(raw, "other-client", "expected")
    unverified = jwt.encode({**claims, "email_verified": False}, key, algorithm="RS256")
    with pytest.raises(auth_service.InvalidCredentials):
        auth_service.verify_google_id_token(unverified, "client-123", "expected")


def _second_login(client) -> str:
    with session_scope(get_session_factory()) as session:
        account = Account(google_sub="second-user", email="second@example.com", name="Second Rider")
        session.add(account)
        session.flush()
        return create_session(session, get_settings(), account)


def test_anonymous_and_wrong_token_audience_are_rejected(client):
    web_token = client.cookies.get("soft_floyd_session")
    assert web_token
    client.cookies.clear()
    assert client.get("/api/profile").status_code == 401
    assert client.post("/mcp/", json={}).status_code == 401
    assert client.get("/api/health").status_code == 200
    client.cookies.set("soft_floyd_session", web_token)
    response = client.post("/mcp/", json={}, headers={"Authorization": f"Bearer {web_token}"})
    assert response.status_code == 401


def test_rider_data_is_isolated_across_accounts(client):
    first_token = client.cookies.get("soft_floyd_session")
    assert first_token
    client.put("/api/profile", json={"goal_text": "Ride a century"})
    bike = client.post("/api/bikes", json={"kind": "road"}).json()
    conversation = client.post("/api/coach/conversations").json()
    with scoped_account(1):
        with session_scope(get_session_factory()) as session:
            ride = Activity(garmin_id=4242, start_time=dt.datetime(2026, 1, 1))
            session.add(ride)
            session.add(CoachMemoryNote(text="Prefers easy mornings"))
            session.flush()
            ride_id = ride.id

    second_token = _second_login(client)
    client.cookies.set("soft_floyd_session", second_token)
    assert client.get("/api/profile").json()["goal_text"] == ""
    assert client.get("/api/bikes").json() == []
    assert client.get("/api/activities").json() == []
    assert client.get(f"/api/activities/{ride_id}").status_code == 404
    assert client.get(f"/api/coach/conversations/{conversation['id']}").status_code == 404
    assert client.get("/api/coach/memory").json() == []
    assert client.patch(f"/api/bikes/{bike['id']}", json={"nickname": "Stolen"}).status_code == 404

    with scoped_account(2):
        with session_scope(get_session_factory()) as session:
            session.add(Activity(garmin_id=4242, start_time=dt.datetime(2026, 1, 2)))
    assert len(client.get("/api/activities").json()) == 1
    client.cookies.set("soft_floyd_session", first_token)
    assert client.get("/api/profile").json()["goal_text"] == "Ride a century"
    assert len(client.get("/api/activities").json()) == 1


def test_logout_revokes_web_and_mcp_tokens(client):
    web_token = client.cookies.get("soft_floyd_session")
    assert web_token
    with session_scope(get_session_factory()) as session:
        mcp_token = issue_mcp_token(session, get_settings(), web_token)
    response = client.post("/api/auth/logout")
    assert response.status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    response = client.post("/mcp/", json={}, headers={"Authorization": f"Bearer {mcp_token}"})
    assert response.status_code == 401


def test_mcp_requires_its_own_valid_bearer_token(client):
    web_token = client.cookies.get("soft_floyd_session")
    assert web_token
    with session_scope(get_session_factory()) as session:
        mcp_token = issue_mcp_token(session, get_settings(), web_token)
    response = client.post(
        "/mcp/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "auth-test", "version": "1"},
            },
        },
        headers={
            "Authorization": f"Bearer {mcp_token}",
            "Accept": "application/json, text/event-stream",
        },
    )
    assert response.status_code < 500
    assert response.status_code != 401


def test_google_callback_registers_account_and_rejects_bad_state(client, monkeypatch):
    from soft_floyd_server import auth_api

    monkeypatch.setenv("SOFT_FLOYD_GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setenv("SOFT_FLOYD_GOOGLE_CLIENT_SECRET", "test-secret")

    start = client.get("/api/auth/google/start", follow_redirects=False)
    assert start.status_code == 307
    query = parse_qs(urlparse(start.headers["location"]).query)
    state = query["state"][0]
    cookie = client.cookies.get("soft_floyd_oauth")
    assert cookie
    payload = jwt.decode(cookie, get_settings().jwt_secret, algorithms=["HS256"])
    assert payload["verifier"] not in start.headers["location"]
    assert (
        client.get(
            "/api/auth/google/callback", params={"code": "one-time-code", "state": "wrong"}
        ).status_code
        == 400
    )

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id_token": "fake-id-token"}

    class FakeGoogleClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def post(self, _url, data):
            assert data["code_verifier"] == payload["verifier"]
            return FakeResponse()

    monkeypatch.setattr(auth_api.httpx, "AsyncClient", FakeGoogleClient)
    monkeypatch.setattr(
        auth_api.auth_service,
        "verify_google_id_token",
        lambda _raw, _client, _nonce: Identity(
            sub="new-google-sub", email="new@example.com", name="New Rider", picture_url=None
        ),
    )
    result = client.get(
        "/api/auth/google/callback",
        params={"code": "one-time-code", "state": state},
        follow_redirects=False,
    )
    assert result.status_code == 307
    assert client.get("/api/auth/me").json()["email"] == "new@example.com"


async def test_web_coach_bridge_calls_authenticated_mcp(client):
    from soft_floyd_server.main import app
    from soft_floyd_server.mcp_bridge import CoachMCPBridge

    web_token = client.cookies.get("soft_floyd_session")
    assert web_token
    with session_scope(get_session_factory()) as session:
        mcp_token = issue_mcp_token(session, get_settings(), web_token)

    def asgi_client(**kwargs):
        return httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), **kwargs)

    async with CoachMCPBridge(get_settings(), mcp_token, asgi_client) as bridge:
        result = await bridge.run("get_rider_profile", "{}")
        context = await bridge.context()
    assert result.status == "Reading your profile"
    assert '"goal_text"' in result.content
    assert "Goal: not set" in context


def _asgi_client(**kwargs) -> httpx2.AsyncClient:
    from soft_floyd_server.main import app

    return httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), **kwargs)


def _mcp_client(mcp_token: str) -> Client:
    """A generic authenticated MCP client, for tools CoachMCPBridge doesn't
    wrap (it only calls run_coach_tool/get_coach_context)."""
    transport = StreamableHttpTransport(
        get_settings().internal_mcp_url,
        headers={"Authorization": f"Bearer {mcp_token}"},
        httpx_client_factory=_asgi_client,
    )
    return Client(transport)


def test_mcp_is_stateless_so_a_session_cannot_carry_another_accounts_context(client):
    """Locks in stateless_http=True (main.py): stateful mode ties a
    session to scope["user"], which our middleware never sets — it would
    let a request bearing account B's valid token but account A's
    still-open mcp-session-id header run its tool calls as A. Stateless
    mode never hands out a session id to reuse.
    """
    with session_scope(get_session_factory()) as session:
        mcp_token = issue_mcp_token(
            session, get_settings(), client.cookies.get("soft_floyd_session")
        )
    response = client.post(
        "/mcp/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "isolation-test", "version": "1"},
            },
        },
        headers={
            "Authorization": f"Bearer {mcp_token}",
            "Accept": "application/json, text/event-stream",
        },
    )
    assert response.status_code < 300
    assert "mcp-session-id" not in {k.lower() for k in response.headers}


async def test_mcp_tools_reject_cross_account_object_ids(client):
    """B, holding valid MCP credentials of B's own, cannot reach A's ride,
    bike or memory note by guessing/reusing A's object IDs — on the direct
    MCP tools or through the coach's run_coach_tool dispatcher."""
    client.put("/api/profile", json={"goal_text": "A's goal"})
    bike = client.post("/api/bikes", json={"kind": "road"}).json()
    first_web_token = client.cookies.get("soft_floyd_session")
    with scoped_account(1):
        with session_scope(get_session_factory()) as session:
            ride = Activity(garmin_id=4242, start_time=dt.datetime(2026, 1, 1))
            session.add(ride)
            note = CoachMemoryNote(text="Prefers easy mornings")
            session.add(note)
            session.flush()
            ride_id, note_id = ride.id, note.id

    second_web_token = _second_login(client)
    with session_scope(get_session_factory()) as session:
        second_mcp_token = issue_mcp_token(session, get_settings(), second_web_token)

    async with _mcp_client(second_mcp_token) as mcp_client:
        profile = await mcp_client.call_tool("get_rider_profile", {})
        assert profile.data.goal_text == ""  # never A's

        activity = await mcp_client.call_tool("get_activity", {"activity_id": ride_id})
        assert not activity.data  # None over the wire, never A's ride

        for name, arguments in [
            ("update_bike", {"bike_id": bike["id"], "bike": {"nickname": "Stolen"}}),
            ("delete_bike", {"bike_id": bike["id"]}),
            ("delete_coach_memory", {"note_id": note_id}),
        ]:
            result = await mcp_client.call_tool(name, arguments, raise_on_error=False)
            assert result.is_error, f"{name} must not reach account A's row"

        for tool_args in [
            {"name": "get_ride", "arguments": f'{{"activity_id": {ride_id}}}'},
            {"name": "forget", "arguments": f'{{"note_id": {note_id}}}'},
        ]:
            result = await mcp_client.call_tool("run_coach_tool", tool_args)
            assert '"error"' in result.data.content

    # A's rows are untouched.
    with scoped_account(1):
        with session_scope(get_session_factory()) as session:
            assert session.get(Activity, ride_id) is not None
            assert session.get(CoachMemoryNote, note_id) is not None
    client.cookies.set("soft_floyd_session", first_web_token)
    assert not client.get("/api/bikes").json()[0]["nickname"]


async def test_concurrent_requests_do_not_cross_accounts(client):
    """Two accounts hitting the API at the same time never see each
    other's data — the ContextVar the whole scoping scheme relies on
    (account_scope.py) must stay isolated per asyncio task, not just per
    sequential request."""
    first_token = client.cookies.get("soft_floyd_session")
    client.put("/api/profile", json={"goal_text": "First rider's goal"})
    second_token = _second_login(client)

    async def _many_profile_reads(token: str, expected_goal: str) -> None:
        async with _asgi_client(base_url="http://testserver") as http_client:
            http_client.cookies.set("soft_floyd_session", token)
            http_client.headers.update({"origin": "http://localhost:5173"})
            for _ in range(10):
                response = await http_client.get("/api/profile")
                assert response.json()["goal_text"] == expected_goal

    await asyncio.gather(
        _many_profile_reads(first_token, "First rider's goal"),
        _many_profile_reads(second_token, ""),
    )


def test_owned_models_cover_every_account_scoped_table():
    """Guards against a new model gaining an account_id column without
    being added to OWNED_MODELS, which would silently leave it
    unfiltered by account_scope's do_orm_execute/before_flush hooks."""
    from soft_floyd_core import models
    from soft_floyd_core.account_scope import OWNED_MODELS

    # AuthSession is auth infrastructure, deliberately queryable without an
    # account context. Book/BookPassage are the shared training corpus.
    # LLMUsageRecord keeps a global spending cap alongside per-account
    # attribution (llm/usage.py) and is scoped separately.
    exempt = {
        models.Account,
        models.AuthSession,
        models.Book,
        models.BookPassage,
        models.LLMUsageRecord,
    }
    for mapper in models.Base.registry.mappers:
        cls = mapper.class_
        if cls in exempt:
            continue
        if hasattr(cls, "account_id"):
            assert cls in OWNED_MODELS, f"{cls.__name__} has account_id but isn't owner-filtered"
