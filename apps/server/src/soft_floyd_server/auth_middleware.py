"""Authenticate before rider REST and FastMCP handlers see a request."""

from __future__ import annotations

from soft_floyd_core.account_scope import enter_account, leave_account
from soft_floyd_core.auth.service import InvalidCredentials, verify_app_token
from soft_floyd_core.config import get_settings
from soft_floyd_core.db import session_scope
from starlette.responses import JSONResponse

from soft_floyd_server.runtime import get_session_factory


class AccountAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path in {"/api/health", "/api/auth/google/start", "/api/auth/google/callback"}:
            await self.app(scope, receive, send)
            return
        if not (path.startswith("/api/") or path.startswith("/mcp")):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope["headers"]}
        settings = get_settings()
        is_mcp = path.startswith("/mcp")
        if is_mcp:
            authorization = headers.get("authorization", "")
            raw = authorization[7:] if authorization.startswith("Bearer ") else ""
            audience = "soft-floyd-mcp"
        else:
            from http.cookies import SimpleCookie

            cookies = SimpleCookie()
            cookies.load(headers.get("cookie", ""))
            session_cookie = cookies.get("soft_floyd_session")
            raw = session_cookie.value if session_cookie else ""
            audience = "soft-floyd-web"
            if scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
                if headers.get("origin") != settings.web_origin:
                    await JSONResponse({"detail": "Invalid request origin"}, status_code=403)(
                        scope, receive, send
                    )
                    return
        try:
            with session_scope(get_session_factory()) as session:
                account = verify_app_token(session, settings, raw, audience)
                session.expunge(account)
        except (InvalidCredentials, RuntimeError):
            await JSONResponse({"detail": "Sign in is required"}, status_code=401)(
                scope, receive, send
            )
            return
        scope.setdefault("state", {})["account"] = account
        token = enter_account(account.id)
        try:
            await self.app(scope, receive, send)
        finally:
            leave_account(token)
