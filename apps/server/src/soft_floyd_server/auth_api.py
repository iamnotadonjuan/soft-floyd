"""Google OIDC transport; account/session decisions live in core.auth."""

from __future__ import annotations

import hashlib
import secrets
import time
from base64 import urlsafe_b64encode
from urllib.parse import urlencode

import anyio
import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from soft_floyd_core.auth import service as auth_service
from soft_floyd_core.config import get_settings
from soft_floyd_core.db import session_scope

from soft_floyd_server.runtime import get_session_factory

router = APIRouter(prefix="/auth")
SESSION_COOKIE = "soft_floyd_session"
OAUTH_COOKIE = "soft_floyd_oauth"


class AccountOut(BaseModel):
    id: int
    email: str
    name: str
    picture_url: str | None


def _account_out(account: object) -> AccountOut:
    return AccountOut.model_validate(account, from_attributes=True)


def _google_config() -> tuple[str, str]:
    settings = get_settings()
    try:
        auth_service.signing_key(settings)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    return settings.google_client_id, settings.google_client_secret


@router.get("/google/start")
def start_google() -> RedirectResponse:
    client_id, _ = _google_config()
    settings = get_settings()
    nonce = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(24)
    cookie_value = jwt.encode(
        {"state": state, "nonce": nonce, "verifier": verifier, "exp": time.time() + 600},
        auth_service.signing_key(settings),
        algorithm="HS256",
    )
    challenge = urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    params = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )
    response = RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")
    response.set_cookie(
        OAUTH_COOKIE,
        cookie_value,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=600,
        path="/api/auth",
    )
    return response


@router.get("/google/callback")
async def google_callback(request: Request, code: str | None = None, state: str | None = None):
    client_id, client_secret = _google_config()
    settings = get_settings()
    cookie_state = request.cookies.get(OAUTH_COOKIE)
    if not code or not state or not cookie_state:
        raise HTTPException(status_code=400, detail="Google sign-in expired; try again")
    try:
        values = jwt.decode(cookie_state, auth_service.signing_key(settings), algorithms=["HS256"])
        if not secrets.compare_digest(state, str(values["state"])):
            raise ValueError("OAuth state mismatch")
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Google sign-in expired; try again") from exc
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": values["verifier"],
                },
            )
        token_response.raise_for_status()
        raw_id_token = token_response.json()["id_token"]
        identity = await anyio.to_thread.run_sync(
            auth_service.verify_google_id_token, raw_id_token, client_id, values["nonce"]
        )
    except (httpx.HTTPError, KeyError, auth_service.InvalidCredentials) as exc:
        raise HTTPException(status_code=400, detail="Google sign-in failed; try again") from exc
    with session_scope(get_session_factory()) as session:
        account = auth_service.get_or_create_account(session, identity)
        app_token = auth_service.create_session(session, settings, account)
    response = RedirectResponse(settings.web_origin)
    response.delete_cookie(OAUTH_COOKIE, path="/api/auth")
    response.set_cookie(
        SESSION_COOKIE,
        app_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=auth_service.SESSION_DAYS * 86400,
        path="/",
    )
    return response


@router.get("/me", response_model=AccountOut)
def me(request: Request) -> AccountOut:
    return _account_out(request.state.account)


@router.post("/logout", status_code=204)
def logout(request: Request):
    with session_scope(get_session_factory()) as session:
        auth_service.revoke_session(session, get_settings(), request.cookies[SESSION_COOKIE])
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
