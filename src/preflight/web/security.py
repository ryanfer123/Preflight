"""Bound request bodies before multipart parsing; set browser security boundaries."""

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_LIMIT = 21 * 1024 * 1024
HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'self'; img-src 'self'; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}


class RequestBoundary:
    """Reject oversized streamed bodies, including requests without Content-Length."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Apply headers to every response and bound state-changing request bodies."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def secured(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = list(message["headers"]) + [
                    (key.lower().encode(), value.encode()) for key, value in HEADERS.items()
                ]
            await send(message)

        if scope["method"] != "POST":
            await self.app(scope, receive, secured)
            return
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > REQUEST_LIMIT:
                response = PlainTextResponse(
                    "Upload too large. Each file must be at most 10 MiB; two files maximum.",
                    status_code=413,
                )
                await response(scope, receive, secured)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)

        async def replay() -> Message:
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, replay, secured)
