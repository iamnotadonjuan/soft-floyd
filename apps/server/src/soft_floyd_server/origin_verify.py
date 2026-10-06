"""Reject requests that did not come through our CloudFront distribution."""

from __future__ import annotations

import hmac

from soft_floyd_core.config import get_settings
from starlette.responses import JSONResponse

HEADER = b"x-origin-verify"
# The server calls its own /mcp (and Docker its health check) over loopback
# inside the container. Internet traffic reaches uvicorn from CloudFront
# addresses, and uvicorn only honours X-Forwarded-For from loopback peers,
# so a remote caller cannot appear as loopback.
LOOPBACK = {"127.0.0.1", "::1"}


class OriginVerifyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        secret = get_settings().origin_verify_secret
        client = scope.get("client")
        if scope["type"] != "http" or not secret or (client and client[0] in LOOPBACK):
            await self.app(scope, receive, send)
            return
        supplied = next((v for k, v in scope["headers"] if k == HEADER), b"")
        if not hmac.compare_digest(supplied, secret.encode()):
            await JSONResponse({"detail": "Forbidden"}, status_code=403)(scope, receive, send)
            return
        await self.app(scope, receive, send)
