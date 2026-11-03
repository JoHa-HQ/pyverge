# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""End-to-end Celery adapter: eager tasks through the public task API."""

from __future__ import annotations

from typing import Any

import pytest
import semver
from celery import chain
from celery.exceptions import CeleryError

from pyverge.adapters.celery import CeleryRuntime, task
from pyverge.execution.context import MigrationContext
from pyverge.schemas import PydanticModelAdapter
from tests.examples.pydantic.semver import (
    UserV1,
    UserV2,
    UserV3,
    migrate_v1_to_v2,
    migrate_v2_to_v3,
)
from tests.examples.pydantic.semver_nested import PersonV1


def _reverse(data: dict[str, Any], context: MigrationContext | None = None) -> dict:
    data = dict(data)
    data.pop("age", None)
    return data


def _strip_status(
    data: dict[str, Any], context: MigrationContext | None = None
) -> dict:
    data = dict(data)
    data.pop("status", None)
    return data


def _age_from_context(
    data: dict[str, Any], context: MigrationContext | None = None
) -> dict:
    return {**data, "age": (context or {}).get("age")}


REGISTRY = [
    semver.Version,
    "user_test",
    [UserV1, UserV2],
    [
        ((UserV1, UserV2), migrate_v1_to_v2),
        ((UserV2, UserV1), _reverse),
    ],
]

CHAIN_REGISTRY = [
    semver.Version,
    "user_test",
    [UserV1, UserV2, UserV3],
    [
        ((UserV1, UserV2), migrate_v1_to_v2),
        ((UserV2, UserV3), migrate_v2_to_v3),
        ((UserV3, UserV2), _strip_status),
        ((UserV2, UserV1), _reverse),
    ],
]

CONTEXT_REGISTRY = [
    semver.Version,
    "user_test",
    [UserV1, UserV2],
    [((UserV1, UserV2), _age_from_context)],
]

V1 = {
    "kind": "User",
    "version": "1.0.0",
    "name": "A",
    "email": "a@b.c",
    "role": "user",
}
V2 = {**V1, "version": "2.0.0", "age": None}
V3 = {**V2, "version": "3.0.0", "age": 0, "status": "active"}

TASK_TARGETS = {
    "legacy": "1.0.0",
    "enrich": "2.0.0",
    "publish": "3.0.0",
}


@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
def test_task_converges_payload_before_handler(app, manager) -> None:
    instance = manager()
    runtime = CeleryRuntime(instance, instance.runner())
    seen: list[dict[str, Any]] = []

    @task(app, runtime=runtime, target="latest", payload="user")
    def process(user: dict[str, Any]) -> dict[str, Any]:
        seen.append(user)
        return user

    result = process.delay(V1).get()

    assert seen == [V2]
    assert result == V2


@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
def test_task_header_selects_target(app, manager) -> None:
    instance = manager()
    runtime = CeleryRuntime(instance, instance.runner())
    seen: list[dict[str, Any]] = []

    @task(
        app,
        runtime=runtime,
        target="latest",
        header="content-version",
        payload="user",
    )
    def process(user: dict[str, Any]) -> None:
        seen.append(user)

    process.apply_async(args=[V2], headers={"content-version": "1.0.0"}).get()

    assert seen == [V1]


@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
def test_task_return_converges(app, manager) -> None:
    instance = manager()
    runtime = CeleryRuntime(instance, instance.runner())

    @task(
        app,
        runtime=runtime,
        target="latest",
        return_target="1.0.0",
        payload="user",
    )
    def process(user: dict[str, Any]) -> dict[str, Any]:
        return user

    assert process.delay(V2).get() == V1


@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
def test_task_name_target(app, manager) -> None:
    instance = manager()
    runtime = CeleryRuntime(instance, instance.runner())
    seen: list[dict[str, Any]] = []

    @task(
        app,
        runtime=runtime,
        target="latest",
        task_targets={"process_legacy": "1.0.0"},
        payload="user",
        name="process_legacy",
    )
    def process(user: dict[str, Any]) -> None:
        seen.append(user)

    process.delay(V2).get()

    assert seen == [V1]


@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, CONTEXT_REGISTRY, id="pydantic")],
    indirect=True,
)
def test_task_context_reaches_migration(app, manager) -> None:
    instance = manager()
    runtime = CeleryRuntime(
        instance,
        instance.runner(),
        context_factory=lambda request: MigrationContext.create({"age": 42}),
    )
    seen: list[dict[str, Any]] = []

    @task(app, runtime=runtime, target="latest", payload="user")
    def process(user: dict[str, Any]) -> None:
        seen.append(user)

    process.delay(V1).get()

    assert seen == [{**V2, "age": 42}]


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
def test_worker_bind_blocks_unhealthy_registry(manager) -> None:
    instance = manager()
    runtime = CeleryRuntime(instance)

    with pytest.raises(CeleryError, match="Registry health validation failed"):
        runtime.bind(instance.runner())


@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, CHAIN_REGISTRY, id="pydantic")],
    indirect=True,
)
def test_task_orchestration_across_versions(app, manager) -> None:
    """A Celery chain hands payloads between tasks of different versions."""
    instance = manager()
    runtime = CeleryRuntime(instance, instance.runner())
    seen: list[tuple[str, dict[str, Any]]] = []

    @task(
        app,
        runtime=runtime,
        name="legacy",
        target="latest",
        task_targets=TASK_TARGETS,
        return_target="1.0.0",
        payload="user",
    )
    def legacy(user: dict[str, Any]) -> dict[str, Any]:
        seen.append(("legacy", user))
        return user

    @task(
        app,
        runtime=runtime,
        name="enrich",
        target="latest",
        task_targets=TASK_TARGETS,
        return_target="2.0.0",
        payload="user",
    )
    def enrich(user: dict[str, Any]) -> dict[str, Any]:
        enriched = {**user, "age": 37}
        seen.append(("enrich", enriched))
        return enriched

    @task(
        app,
        runtime=runtime,
        name="publish",
        target="latest",
        task_targets=TASK_TARGETS,
        return_target="3.0.0",
        payload="user",
    )
    def publish(user: dict[str, Any]) -> dict[str, Any]:
        published = {**user, "status": "inactive"}
        seen.append(("publish", published))
        return published

    result = chain(legacy.s(V1), enrich.s(), publish.s()).apply_async().get()

    assert [name for name, _ in seen] == ["legacy", "enrich", "publish"]
    assert seen[0][1] == V1
    assert seen[1][1] == {**V2, "age": 37}
    assert seen[2][1] == {**V3, "age": 37, "status": "inactive"}
    assert result == seen[2][1]
