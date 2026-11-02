"""Run the demo: ``python -m httpx_demo``."""

from __future__ import annotations

import json

import httpx

from pyverge.adapters.httpx import HttpPolicy

from .client import build_transport
from .domain import build_manager, order_v1
from .server import serve


def main() -> None:
    """Send a v1 order, converge to v2 on the wire, and read a v1 response."""
    manager = build_manager()
    policy = HttpPolicy(target="latest", response_target="1.0.0")
    transport = build_transport(manager, policy)

    with serve() as server:
        with httpx.Client(base_url=server.url, transport=transport) as client:
            response = client.post("/orders", json=order_v1())
            response.raise_for_status()
            print(
                json.dumps(
                    {
                        "client_sent": order_v1(),
                        "server_received": server.received_body,
                        "server_headers": server.received_headers,
                        "client_received": response.json(),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )


if __name__ == "__main__":
    main()
