"""End-to-end FastStream adapter: convergence through the public broker surface.

Each case publishes a payload at a registered version and asserts the subscriber
handler saw the manager's target version — the convergence decoder runs in the
subscriber pipeline before the handler. Reflection reconciles each handler's
declared payload model into the graph before start.
"""

from __future__ import annotations

from typing import Any

import pytest
import semver
from faststream import FastStream
from faststream.kafka import KafkaBroker, TestKafkaBroker

from pyverge.adapters.faststream import (
    FastStreamSource,
    TopicTargets,
    publish_to,
    publisher,
    subscriber,
)
from pyverge.core import MigrationContext
from pyverge.registry.errors import MigrationPathError
from pyverge.schemas import PydanticModelAdapter
from tests.examples.pydantic.semver import (
    UserV1,
    UserV2,
    migrate_v1_to_v2,
)


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

#: Only the forward edge is registered, so a downgrade has no path.
FORWARD_ONLY_REGISTRY = [
    semver.Version,
    "user_test",
    [UserV1, UserV2],
    [((UserV1, UserV2), migrate_v1_to_v2)],
]

V1_PAYLOAD = {
    "kind": "User",
    "version": "1.0.0",
    "name": "A",
    "email": "a@b.c",
    "role": "user",
}
V2_PAYLOAD = {**V1_PAYLOAD, "version": "2.0.0", "age": None}
KAFKA_BROKER = (KafkaBroker, {"bootstrap_servers": "localhost:9092"})


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
@pytest.mark.parametrize(
    "broker, payload, expected",
    [
        pytest.param(
            (*KAFKA_BROKER, "latest"), V1_PAYLOAD, V2_PAYLOAD, id="stale-to-latest"
        ),
        pytest.param(
            (*KAFKA_BROKER, "latest"), V2_PAYLOAD, V2_PAYLOAD, id="current-passthrough"
        ),
        pytest.param(
            (*KAFKA_BROKER, "1.0.0"), V2_PAYLOAD, V1_PAYLOAD, id="pinned-downgrade"
        ),
        pytest.param(
            (*KAFKA_BROKER, {"User": "1.0.0"}),
            V2_PAYLOAD,
            V1_PAYLOAD,
            id="per-kind",
        ),
    ],
    indirect=["broker"],
)
async def test_converges_to_target(broker, payload, expected) -> None:
    async with TestKafkaBroker(broker) as br:
        await br.publish(payload, "users")
    assert broker.payloads == [expected]


def test_source_skips_handler_without_model(manager, model_adapter) -> None:
    runtime_manager = type(
        "RuntimeManager",
        (manager,),
        {"_reflection_locked": False},
    )
    instance = runtime_manager()
    broker = KafkaBroker("localhost:9092")

    @subscriber(broker, "raw", manager=instance)
    async def handle(payload: dict) -> None: ...

    report = manager.reflect(
        FastStreamSource(FastStream(broker), adapter=model_adapter)
    )

    assert report.registered_models == 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
class TestProduce:
    async def test_in_out_bridge(self, manager, broker) -> None:
        instance = manager()
        out: list[dict[str, Any]] = []

        @subscriber(broker, "in-topic", manager=instance, targets="latest")
        @publisher(broker, "out-topic", manager=instance, target="1.0.0")
        async def handle(user: UserV2) -> UserV2:
            return user

        @broker.subscriber("out-topic")
        async def sink(payload: dict) -> None:
            out.append(payload)

        async with TestKafkaBroker(broker) as br:
            await br.publish(V1_PAYLOAD, "in-topic")
        assert out == [V1_PAYLOAD]

    async def test_out_passthrough(self, manager, broker) -> None:
        instance = manager()
        out: list[dict[str, Any]] = []

        @subscriber(broker, "in-topic", manager=instance, targets="latest")
        @publisher(broker, "out-topic", manager=instance, target="latest")
        async def handle(user: UserV2) -> UserV2:
            return user

        @broker.subscriber("out-topic")
        async def sink(payload: dict) -> None:
            out.append(payload)

        async with TestKafkaBroker(broker) as br:
            await br.publish(V1_PAYLOAD, "in-topic")
        assert out == [V2_PAYLOAD]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
class TestNegotiation:
    async def test_header_selects_version(self, manager) -> None:
        instance = manager()
        broker = KafkaBroker("localhost:9092")
        seen: list[dict[str, Any]] = []

        @subscriber(broker, "users", manager=instance, header="accept-version")
        async def handle(user: UserV2) -> None:
            seen.append(user.model_dump())

        async with TestKafkaBroker(broker) as br:
            await br.publish(
                V2_PAYLOAD,
                "users",
                headers={"accept-version": "1.0.0"},
            )
        assert seen == [V1_PAYLOAD]

    async def test_per_topic_targets(self, manager) -> None:
        instance = manager()
        broker = KafkaBroker("localhost:9092")
        seen: list[dict[str, Any]] = []

        @subscriber(
            broker,
            "users",
            "users-latest",
            manager=instance,
            targets=TopicTargets({"users": "1.0.0", "users-latest": "latest"}),
        )
        async def handle(user: UserV2) -> None:
            seen.append(user.model_dump())

        async with TestKafkaBroker(broker) as br:
            await br.publish(V2_PAYLOAD, "users")
            await br.publish(V2_PAYLOAD, "users-latest")
        assert seen == [V1_PAYLOAD, V2_PAYLOAD]

    async def test_publish_to_converges_each_route(self, manager) -> None:
        instance = manager()
        broker = KafkaBroker("localhost:9092")
        out_v1: list[dict[str, Any]] = []
        out_v2: list[dict[str, Any]] = []

        @subscriber(broker, "in-topic", manager=instance)
        @publish_to(
            broker,
            routes={"out-v1": "1.0.0", "out-v2": "latest"},
            manager=instance,
        )
        async def handle(user: UserV2) -> UserV2:
            return user

        @broker.subscriber("out-v1")
        async def sink_v1(payload: dict) -> None:
            out_v1.append(payload)

        @broker.subscriber("out-v2")
        async def sink_v2(payload: dict) -> None:
            out_v2.append(payload)

        async with TestKafkaBroker(broker) as br:
            await br.publish(V2_PAYLOAD, "in-topic")
        assert out_v1 == [V1_PAYLOAD]
        assert out_v2 == [V2_PAYLOAD]


@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, FORWARD_ONLY_REGISTRY, id="pydantic")],
    indirect=True,
)
class TestFailures:
    def test_no_migration_path_raises(self, manager) -> None:
        with pytest.raises(MigrationPathError):
            manager().runner().run(
                V2_PAYLOAD,
                "1.0.0",
                container=None,
                max_depth=-1,
                context=None,
            )


def test_source_reflects_subscriber_models(manager, source) -> None:
    report = manager.reflect(source)

    assert report.registered_models == 1
    assert [str(version) for version in manager._default_engine.registry.versions] == [
        "User@2.0.0"
    ]


def test_source_reflects_publisher_models(manager, publisher_source) -> None:
    report = manager.reflect(publisher_source)

    assert report.registered_models == 1
    assert [str(version) for version in manager._default_engine.registry.versions] == [
        "User@2.0.0"
    ]
