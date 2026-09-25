"""Account identity, revocable browser sessions, and short-lived MCP grants."""

from __future__ import annotations

import datetime as dt
import secrets
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from soft_floyd_core.config import Settings
from soft_floyd_core.models import Account, AuthSession

SESSION_DAYS = 7
MCP_TOKEN_SECONDS = 900
GOOGLE_KEYS = "https://www.googleapis.com/oauth2/v3/certs"


class InvalidCredentials(Exception):
    pass


@dataclass(frozen=True)
class Identity:
    sub: str
    email: str
    name: str
    picture_url: str | None


def signing_key(settings: Settings) -> str:
    if not settings.jwt_secret or len(settings.jwt_secret) < 32:
        raise RuntimeError("SOFT_FLOYD_JWT_SECRET must contain at least 32 characters")
    return settings.jwt_secret


def verify_google_id_token(raw: str, client_id: str, nonce: str) -> Identity:
    try:
        key = PyJWKClient(GOOGLE_KEYS).get_signing_key_from_jwt(raw).key
        claims = jwt.decode(
            raw,
            key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=["accounts.google.com", "https://accounts.google.com"],
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise InvalidCredentials("Google identity could not be verified") from exc
    if claims.get("nonce") != nonce or claims.get("email_verified") is not True:
        raise InvalidCredentials("Google identity could not be verified")
    if not claims.get("sub") or not claims.get("email"):
        raise InvalidCredentials("Google identity is incomplete")
    return Identity(
        sub=str(claims["sub"]),
        email=str(claims["email"]),
        name=str(claims.get("name") or claims["email"]),
        picture_url=str(claims["picture"]) if claims.get("picture") else None,
    )


def get_or_create_account(session: Session, identity: Identity) -> Account:
    account = session.scalar(select(Account).where(Account.google_sub == identity.sub))
    if account is None:
        account = Account(google_sub=identity.sub, email=identity.email, name=identity.name)
        session.add(account)
    account.email = identity.email
    account.name = identity.name
    account.picture_url = identity.picture_url
    session.flush()
    return account


def _jwt(settings: Settings, *, account_id: int, sid: str, audience: str, seconds: int) -> str:
    now = dt.datetime.now(dt.UTC)
    return jwt.encode(
        {
            "iss": "soft-floyd",
            "sub": str(account_id),
            "sid": sid,
            "aud": audience,
            "iat": now,
            "exp": now + dt.timedelta(seconds=seconds),
        },
        signing_key(settings),
        algorithm="HS256",
    )


def create_session(session: Session, settings: Settings, account: Account) -> str:
    sid = secrets.token_urlsafe(32)
    session.add(
        AuthSession(
            id=sid,
            account_id=account.id,
            expires_at=dt.datetime.now(dt.UTC).replace(tzinfo=None)
            + dt.timedelta(days=SESSION_DAYS),
        )
    )
    session.flush()
    return _jwt(
        settings,
        account_id=account.id,
        sid=sid,
        audience="soft-floyd-web",
        seconds=SESSION_DAYS * 86400,
    )


def verify_app_token(session: Session, settings: Settings, raw: str, audience: str) -> Account:
    try:
        claims = jwt.decode(
            raw,
            signing_key(settings),
            algorithms=["HS256"],
            audience=audience,
            issuer="soft-floyd",
        )
        owner = int(claims["sub"])
        sid = str(claims["sid"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError) as exc:
        raise InvalidCredentials("Sign in is required") from exc
    auth_session = session.get(AuthSession, sid)
    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    if (
        auth_session is None
        or auth_session.account_id != owner
        or auth_session.revoked_at is not None
        or auth_session.expires_at <= now
    ):
        raise InvalidCredentials("Sign in is required")
    account = session.get(Account, owner)
    if account is None:
        raise InvalidCredentials("Sign in is required")
    return account


def revoke_session(session: Session, settings: Settings, raw: str) -> None:
    account = verify_app_token(session, settings, raw, "soft-floyd-web")
    claims = jwt.decode(
        raw,
        signing_key(settings),
        algorithms=["HS256"],
        audience="soft-floyd-web",
        issuer="soft-floyd",
    )
    row = session.get(AuthSession, claims["sid"])
    if row is not None and row.account_id == account.id:
        row.revoked_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)


def issue_mcp_token(session: Session, settings: Settings, web_token: str) -> str:
    account = verify_app_token(session, settings, web_token, "soft-floyd-web")
    claims = jwt.decode(
        web_token,
        signing_key(settings),
        algorithms=["HS256"],
        audience="soft-floyd-web",
        issuer="soft-floyd",
    )
    return _jwt(
        settings,
        account_id=account.id,
        sid=claims["sid"],
        audience="soft-floyd-mcp",
        seconds=MCP_TOKEN_SECONDS,
    )
