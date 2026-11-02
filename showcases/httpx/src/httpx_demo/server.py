"""A tiny versioned HTTP service, independent of pyverge.

The service records the request it received and always answers with a v2 body.
It stands in for a real service whose contract is already at v2.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any, cast

from .domain import order_v2


class DemoServer(ThreadingHTTPServer):
    """HTTP server carrying the last request for the demo and tests."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.received_body: dict[str, Any] | None = None
        self.received_headers: dict[str, str] = {}

    @property
    def url(self) -> str:
        """Return the base URL for an httpx client."""
        host, port = self.server_address
        return f"http://{host}:{port}"


class Handler(BaseHTTPRequestHandler):
    """Record one order request and answer with the v2 shape."""

    def do_POST(self) -> None:
        server = cast(DemoServer, self.server)
        length = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            self.send_error(HTTPStatus.BAD_REQUEST, "invalid JSON")
            return
        server.received_body = body
        server.received_headers = dict(self.headers)

        data = json.dumps(order_v2()).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", "application/json")
        self.send_header("content-version", "2.0.0")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        """Keep the demo output clean."""


@contextmanager
def serve() -> Iterator[DemoServer]:
    """Run the demo server on an ephemeral localhost port."""
    server = DemoServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


__all__ = ["DemoServer", "Handler", "serve"]
