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
    Reflector,
    TopicTargets,
    publish_to,
    publisher,
    subscriber,
)
from pyverge.migration import MigrationContext, PydanticModelAdapter
from pyverge.registry.errors import CatalogError
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


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
@pytest.mark.parametrize(
    "broker, payload, expected",
    [
        pytest.param("latest", V1_PAYLOAD, V2_PAYLOAD, id="stale-to-latest"),
        pytest.param("latest", V2_PAYLOAD, V2_PAYLOAD, id="current-passthrough"),
        pytest.param("1.0.0", V2_PAYLOAD, V1_PAYLOAD, id="pinned-downgrade"),
        pytest.param({"User": "1.0.0"}, V2_PAYLOAD, V1_PAYLOAD, id="per-kind"),
    ],
    indirect=["broker"],
)
async def test_converges_to_target(broker, payloads, payload, expected) -> None:
    async with TestKafkaBroker(broker) as br:
        await br.publish(payload, "users")
    assert payloads == [expected]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
class TestReflection:
    def test_reflect_reconciles_typed_handler(self, manager, broker) -> None:
        reflected = Reflector(manager()).reflect(broker)
        assert [r.model for r in reflected] == [UserV2]
        assert reflected[0].topics == ("users",)

    def test_reflector_runs_on_startup(self, manager, broker) -> None:
        app = FastStream(broker, on_startup=[Reflector(manager())])
        assert app.brokers

    def test_handler_without_model_is_skipped(self, manager) -> None:
        instance = manager()
        broker = KafkaBroker("localhost:9092")

        @subscriber(broker, "raw", manager=instance)
        async def handle(payload: dict) -> None: ...

        assert Reflector(instance).reflect(broker) == []


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
        with pytest.raises(CatalogError):
            manager().migrate(V2_PAYLOAD, target="1.0.0")
