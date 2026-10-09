"""Response protections for private API and MCP data."""

from __future__ import annotations


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                is_private = scope.get("path", "").startswith(("/api/", "/mcp"))
                if is_private:
                    headers = [
                        (name, value) for name, value in headers if name.lower() != b"cache-control"
                    ]
                present = {name.lower() for name, _ in headers}
                additions = {
                    b"x-content-type-options": b"nosniff",
                    b"referrer-policy": b"no-referrer",
                    b"x-frame-options": b"DENY",
                }
                if is_private:
                    additions[b"cache-control"] = b"no-store"
                    additions[b"content-security-policy"] = (
                        b"default-src 'none'; frame-ancestors 'none'"
                    )
                headers.extend(
                    (name, value) for name, value in additions.items() if name not in present
                )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
