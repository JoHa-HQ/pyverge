# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""End-to-end httpx showcase: converge request and response through a transport."""

from __future__ import annotations

import httpx
import pytest
from httpx_demo.client import build_async_transport, build_transport
from httpx_demo.domain import build_manager, order_v1, order_v2
from httpx_demo.server import serve

from pyverge.adapters.httpx import HttpPolicy


def test_request_and_response_converge() -> None:
    manager = build_manager()
    policy = HttpPolicy(target="latest", response_target="1.0.0")
    transport = build_transport(manager, policy)

    with serve() as server:
        with httpx.Client(base_url=server.url, transport=transport) as client:
            response = client.post("/orders", json=order_v1())
            response.raise_for_status()

    assert server.received_body == order_v2()
    assert server.received_headers["content-version"] == "2.0.0"
    assert server.received_headers["accept-version"] == "1.0.0"
    assert response.json() == order_v1()


def test_legacy_policy_sends_v1() -> None:
    manager = build_manager()
    policy = HttpPolicy(target="1.0.0", response_target="latest")
    transport = build_transport(manager, policy)

    with serve() as server:
        with httpx.Client(base_url=server.url, transport=transport) as client:
            response = client.post("/orders", json=order_v2())
            response.raise_for_status()

    assert server.received_body == order_v1()
    assert server.received_headers["content-version"] == "1.0.0"
    assert server.received_headers["accept-version"] == "latest"
    assert response.json() == order_v2()


@pytest.mark.anyio
async def test_async_transport_converges() -> None:
    manager = build_manager()
    policy = HttpPolicy(target="latest", response_target="1.0.0")
    transport = build_async_transport(manager, policy)

    with serve() as server:
        async with httpx.AsyncClient(
            base_url=server.url, transport=transport
        ) as client:
            response = await client.post("/orders", json=order_v1())
            response.raise_for_status()

    assert server.received_body == order_v2()
    assert response.json() == order_v1()


def test_two_clients_use_independent_policies() -> None:
    manager = build_manager()
    legacy_transport = build_transport(
        manager,
        HttpPolicy(target="1.0.0", response_target="latest"),
    )
    current_transport = build_transport(
        manager,
        HttpPolicy(target="latest", response_target="1.0.0"),
    )

    with serve() as legacy_server, serve() as current_server:
        with httpx.Client(
            base_url=legacy_server.url, transport=legacy_transport
        ) as legacy:
            legacy_response = legacy.post("/orders", json=order_v2())
            legacy_response.raise_for_status()

        with httpx.Client(
            base_url=current_server.url, transport=current_transport
        ) as current:
            current_response = current.post("/orders", json=order_v1())
            current_response.raise_for_status()

    assert legacy_server.received_body == order_v1()
    assert current_server.received_body == order_v2()
    assert legacy_response.json() == order_v2()
    assert current_response.json() == order_v1()
