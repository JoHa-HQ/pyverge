# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""End-to-end httpx transport: one strategy per transport, inside a real client."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any

import httpx
import pytest
import semver

from pyverge.adapters.httpx import HttpPolicy, PyvergeAsyncTransport, PyvergeTransport
from pyverge.adapters.runtime import ConvergenceRuntime
from pyverge.execution.context import MigrationContext
from pyverge.registry.errors import HealthValidationError
from pyverge.schemas import PydanticModelAdapter
from tests.examples.pydantic.semver import UserV1, UserV2, migrate_v1_to_v2
from tests.examples.pydantic.semver_nested import PersonV1


def _reverse(data: dict[str, Any], context: MigrationContext | None = None) -> dict:
    data = dict(data)
    data.pop("age", None)
    return data


REGISTRY = [
    semver.Version,
    "user_test",
    [UserV1, UserV2],
    [
        ((UserV1, UserV2), migrate_v1_to_v2),
        ((UserV2, UserV1), _reverse),
    ],
]

V1 = {
    "kind": "User",
    "version": "1.0.0",
    "name": "A",
    "email": "a@b.c",
    "role": "user",
}
V2 = {**V1, "version": "2.0.0", "age": None}

URL = "https://orders.test/orders"


class Server:
    """A tiny versioned echo server."""

    def __init__(self) -> None:
        self.payload: dict[str, Any] | None = None
        self.headers: dict[str, str] = {}
        self.response: dict[str, Any] = V2
        self.status = HTTPStatus.OK

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.payload = json.loads(request.content) if request.content else None
        self.headers = dict(request.headers)
        return httpx.Response(self.status, json=self.response)


def _runtime(instance) -> ConvergenceRuntime:
    return ConvergenceRuntime(instance, instance.runner())


@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
def test_transport_converges_request_and_response(manager) -> None:
    instance = manager()
    server = Server()
    transport = PyvergeTransport(
        _runtime(instance),
        policy=HttpPolicy(target="latest", response_target="1.0.0"),
        transport=httpx.MockTransport(server),
    )

    with httpx.Client(transport=transport) as client:
        response = client.post(URL, json=V1)

    assert server.payload == V2
    assert server.headers["content-version"] == "2.0.0"
    assert server.headers["accept-version"] == "1.0.0"
    assert response.json() == V1
    assert int(response.headers["content-length"]) == len(response.content)


@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
def test_one_strategy_per_transport(manager) -> None:
    instance = manager()
    runtime = _runtime(instance)
    server = Server()

    legacy = PyvergeTransport(
        runtime,
        policy=HttpPolicy(target="1.0.0"),
        transport=httpx.MockTransport(server),
    )
    with httpx.Client(transport=legacy) as client:
        client.post(URL, json=V2)
    assert server.payload == V1
    assert server.headers["content-version"] == "1.0.0"

    latest = PyvergeTransport(
        runtime,
        policy=HttpPolicy(target="latest"),
        transport=httpx.MockTransport(server),
    )
    with httpx.Client(transport=latest) as client:
        client.post(URL, json=V1)
    assert server.payload == V2
    assert server.headers["content-version"] == "2.0.0"


@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
def test_transport_leaves_response_unchanged_without_target(manager) -> None:
    instance = manager()
    server = Server()
    transport = PyvergeTransport(
        _runtime(instance),
        policy=HttpPolicy(target="latest"),
        transport=httpx.MockTransport(server),
    )

    with httpx.Client(transport=transport) as client:
        response = client.post(URL, json=V1)

    assert server.payload == V2
    assert response.json() == V2


@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
def test_transport_converges_response_without_request_body(manager) -> None:
    instance = manager()
    server = Server()
    transport = PyvergeTransport(
        _runtime(instance),
        policy=HttpPolicy(response_target="1.0.0"),
        transport=httpx.MockTransport(server),
    )

    with httpx.Client(transport=transport) as client:
        response = client.get(URL)

    assert server.payload is None
    assert response.json() == V1


@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
def test_transport_leaves_error_response_unchanged(manager) -> None:
    instance = manager()
    server = Server()
    server.status = HTTPStatus.NOT_FOUND
    transport = PyvergeTransport(
        _runtime(instance),
        policy=HttpPolicy(target="latest", response_target="1.0.0"),
        transport=httpx.MockTransport(server),
    )

    with httpx.Client(transport=transport) as client:
        response = client.get(URL)

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json() == V2


@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
def test_transport_passes_non_json_through(manager) -> None:
    instance = manager()

    def echo(request: httpx.Request) -> httpx.Response:
        return httpx.Response(HTTPStatus.OK, text=request.content.decode())

    transport = PyvergeTransport(
        _runtime(instance),
        policy=HttpPolicy(target="latest"),
        transport=httpx.MockTransport(echo),
    )

    with httpx.Client(transport=transport) as client:
        response = client.post(
            URL,
            content=b"plain body",
            headers={"content-type": "text/plain"},
        )

    assert response.text == "plain body"


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            [semver.Version, "test", [PersonV1], []],
            id="pydantic",
        )
    ],
    indirect=True,
)
def test_transport_bind_validates_registry_health(manager) -> None:
    instance = manager()
    transport = PyvergeTransport(ConvergenceRuntime(instance))

    with pytest.raises(HealthValidationError):
        transport.bind(instance.runner())


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
async def test_async_transport_converges_request_and_response(manager) -> None:
    instance = manager()
    server = Server()
    transport = PyvergeAsyncTransport(
        _runtime(instance),
        policy=HttpPolicy(target="latest", response_target="1.0.0"),
        transport=httpx.MockTransport(server),
    )

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.post(URL, json=V1)

    assert server.payload == V2
    assert server.headers["content-version"] == "2.0.0"
    assert response.json() == V1
