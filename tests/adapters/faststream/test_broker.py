# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""End-to-end: the PyvergeBroker facade over a real FastStream broker."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest
import semver
from faststream import FastStream
from faststream.exceptions import StartupValidationError
from faststream.kafka import KafkaBroker, TestKafkaBroker

from pyverge.adapters.faststream import (
    FastStreamRuntime,
    NegotiationError,
    PyvergeBroker,
    subscriber,
)
from pyverge.execution.context import MigrationContext
from pyverge.manager.types import VersionRange
from pyverge.schemas import PydanticModelAdapter
from tests.examples.pydantic.semver import (
    UserV1,
    UserV2,
    migrate_v1_to_v2,
)
from tests.examples.pydantic.semver_nested import PersonV1


def _reverse(
    data: dict[str, Any], context: MigrationContext | None = None
) -> dict[str, Any]:
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

V1_PAYLOAD = {
    "kind": "User",
    "version": "1.0.0",
    "name": "A",
    "email": "a@b.c",
    "role": "user",
}
V2_PAYLOAD = {**V1_PAYLOAD, "version": "2.0.0", "age": None}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
async def test_facade_converges_and_records_bindings(manager) -> None:
    instance = manager()
    broker = PyvergeBroker(
        KafkaBroker("localhost:9092"),
        manager=instance,
        runner=instance.runner(),
    )
    out: list[dict[str, Any]] = []

    @broker.subscriber("in-topic", target="latest")
    @broker.publisher("out-topic", target="1.0.0")
    async def handle(user: UserV2) -> UserV2:
        return user

    @broker.underlying.subscriber("out-topic")
    async def sink(payload: dict) -> None:
        out.append(payload)

    async with TestKafkaBroker(broker.underlying) as br:
        await br.publish(V1_PAYLOAD, "in-topic")

    assert out == [V1_PAYLOAD]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
async def test_invalid_header_fails_before_the_handler(manager) -> None:
    broker = KafkaBroker("localhost:9092")
    instance = manager()
    runtime = FastStreamRuntime(instance, instance.runner())
    seen: list[UserV2] = []

    @subscriber(
        broker,
        "users",
        runtime=runtime,
        header="accept-version",
    )
    async def handle(user: UserV2) -> None:
        seen.append(user)

    async with TestKafkaBroker(broker) as br:
        with pytest.raises(NegotiationError):
            await br.publish(
                V2_PAYLOAD,
                "users",
                headers={"accept-version": ""},
            )

    assert seen == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
async def test_facade_publish_to_converges_each_route(manager) -> None:
    instance = manager()
    broker = PyvergeBroker(
        KafkaBroker("localhost:9092"),
        manager=instance,
        runner=instance.runner(),
    )
    out_v1: list[dict[str, Any]] = []
    out_v2: list[dict[str, Any]] = []

    @broker.subscriber("in-topic")
    @broker.publish_to(routes={"out-v1": "1.0.0", "out-v2": "latest"})
    async def handle(user: UserV2) -> UserV2:
        return user

    @broker.underlying.subscriber("out-v1")
    async def sink_v1(payload: dict) -> None:
        out_v1.append(payload)

    @broker.underlying.subscriber("out-v2")
    async def sink_v2(payload: dict) -> None:
        out_v2.append(payload)

    async with TestKafkaBroker(broker.underlying) as br:
        await br.publish(V2_PAYLOAD, "in-topic")

    assert out_v1 == [V1_PAYLOAD]
    assert out_v2 == [V2_PAYLOAD]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
@pytest.mark.parametrize(
    "header_value, expected",
    [
        pytest.param('{"User": "1.0.0"}', V1_PAYLOAD, id="mapping"),
        pytest.param('{"User": 1}', None, id="mapping-not-strings"),
    ],
)
async def test_header_forms(manager, header_value, expected) -> None:
    broker = KafkaBroker("localhost:9092")
    instance = manager()
    runtime = FastStreamRuntime(instance, instance.runner())
    seen: list[dict[str, Any]] = []

    @subscriber(
        broker,
        "users",
        runtime=runtime,
        header="accept-version",
    )
    async def handle(user: UserV1 | UserV2) -> None:
        seen.append(user.model_dump())

    async with TestKafkaBroker(broker) as br:
        if expected is None:
            with pytest.raises(NegotiationError):
                await br.publish(
                    V2_PAYLOAD,
                    "users",
                    headers={"accept-version": header_value},
                )
        else:
            await br.publish(
                V2_PAYLOAD,
                "users",
                headers={"accept-version": header_value},
            )

    assert seen == ([expected] if expected is not None else [])


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
async def test_runtime_binds_during_startup(manager) -> None:
    instance = manager()
    runtime = FastStreamRuntime(instance)
    broker = KafkaBroker("localhost:9092")
    seen: list[dict[str, Any]] = []

    @subscriber(broker, "users", runtime=runtime)
    async def handle(user: UserV2) -> None:
        seen.append(user.model_dump())

    runtime.bind(instance.runner())

    async with TestKafkaBroker(broker) as br:
        await br.publish(V1_PAYLOAD, "users")

    assert seen == [V2_PAYLOAD]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
async def test_unbound_runtime_fails_before_convergence(manager) -> None:
    instance = manager()
    runtime = FastStreamRuntime(instance)
    broker = KafkaBroker("localhost:9092")

    @subscriber(broker, "users", runtime=runtime)
    async def handle(user: UserV2) -> None: ...

    async with TestKafkaBroker(broker) as br:
        with pytest.raises(RuntimeError, match="no runner"):
            await br.publish(V1_PAYLOAD, "users")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
async def test_user_defined_selector_overrides_first_match(manager) -> None:
    instance = manager()
    runtime = FastStreamRuntime(instance, instance.runner())
    broker = KafkaBroker("localhost:9092")
    seen: list[dict[str, Any]] = []

    class FixedTarget:
        def select(self, context: Any) -> str:
            return "1.0.0"

    @subscriber(
        broker,
        "users",
        runtime=runtime,
        selector=FixedTarget(),
    )
    async def handle(user: UserV1 | UserV2) -> None:
        seen.append(user.model_dump())

    async with TestKafkaBroker(broker) as br:
        await br.publish(V2_PAYLOAD, "users")

    assert seen == [V1_PAYLOAD]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
@pytest.mark.parametrize(
    "header_value",
    [
        pytest.param('{"gte": "1.0.0", "lt": "2.0.0"}', id="bounds"),
        pytest.param('{"eq": "1.0.0"}', id="exact"),
    ],
)
async def test_header_range_selects_highest_match(manager, header_value) -> None:
    instance = manager()
    runtime = FastStreamRuntime(instance, instance.runner())
    broker = KafkaBroker("localhost:9092")
    seen: list[dict[str, Any]] = []

    @subscriber(
        broker,
        "users",
        runtime=runtime,
        header="accept-version",
    )
    async def handle(user: UserV1 | UserV2) -> None:
        seen.append(user.model_dump())

    async with TestKafkaBroker(broker) as br:
        await br.publish(
            V2_PAYLOAD,
            "users",
            headers={"accept-version": header_value},
        )

    assert seen == [V1_PAYLOAD]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
async def test_python_range_target(manager) -> None:
    instance = manager()
    runtime = FastStreamRuntime(instance, instance.runner())
    broker = KafkaBroker("localhost:9092")
    seen: list[dict[str, Any]] = []

    @subscriber(
        broker,
        "users",
        runtime=runtime,
        targets=VersionRange(gte="1.0.0", lt="2.0.0"),
    )
    async def handle(user: UserV1 | UserV2) -> None:
        seen.append(user.model_dump())

    async with TestKafkaBroker(broker) as br:
        await br.publish(V2_PAYLOAD, "users")

    assert seen == [V1_PAYLOAD]


def _add_age_from_context(
    data: dict[str, Any], context: MigrationContext | None = None
) -> dict[str, Any]:
    age = (context or {}).get("age")
    return {**data, "age": age}


CONTEXT_REGISTRY = [
    semver.Version,
    "user_test",
    [UserV1, UserV2],
    [((UserV1, UserV2), _add_age_from_context)],
]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, CONTEXT_REGISTRY, id="pydantic")],
    indirect=True,
)
async def test_runtime_context_reaches_migrations(manager) -> None:
    instance = manager()
    runtime = FastStreamRuntime(
        instance,
        instance.runner(),
        context_factory=lambda message: MigrationContext.create({"age": 42}),
    )
    broker = KafkaBroker("localhost:9092")
    seen: list[dict[str, Any]] = []

    @subscriber(broker, "users", runtime=runtime)
    async def handle(user: UserV2) -> None:
        seen.append(user.model_dump())

    async with TestKafkaBroker(broker) as br:
        await br.publish(V1_PAYLOAD, "users")

    assert seen == [{**V2_PAYLOAD, "age": 42}]


@pytest.mark.anyio
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
async def test_startup_blocks_unhealthy_registry(manager) -> None:
    instance = manager()
    runtime = FastStreamRuntime(instance)
    broker = KafkaBroker("localhost:9092")

    @asynccontextmanager
    async def lifespan():
        runtime.bind(instance.runner())
        yield

    app = FastStream(broker, lifespan=lifespan)

    async with TestKafkaBroker(broker):
        with pytest.raises(StartupValidationError):
            async with app.lifespan_context():
                pass
