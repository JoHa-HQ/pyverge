# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""End-to-end Celery lifecycle: signals bind and validate the runtime."""

from __future__ import annotations

from typing import Any

import pytest
import semver
from celery.signals import worker_process_init, worker_process_shutdown

from pyverge.adapters.celery import CeleryLifecycle, CeleryRuntime
from pyverge.execution.context import MigrationContext
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


@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, REGISTRY, id="pydantic")],
    indirect=True,
)
def test_lifecycle_binds_and_shuts_down(manager) -> None:
    instance = manager()
    runtime = CeleryRuntime(instance)
    runner = instance.runner()
    closed: list[bool] = []
    lifecycle = CeleryLifecycle(
        runtime,
        lambda: runner,
        on_shutdown=lambda: closed.append(True),
    )
    lifecycle.install()
    try:
        worker_process_init.send(sender=None)
        assert runtime.runner is runner

        worker_process_shutdown.send(sender=None)
        assert closed == [True]
    finally:
        lifecycle.uninstall()


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
def test_lifecycle_stops_the_process_on_unhealthy_registry(manager) -> None:
    instance = manager()
    runtime = CeleryRuntime(instance)
    lifecycle = CeleryLifecycle(runtime, instance.runner)
    lifecycle.install()
    try:
        with pytest.raises(SystemExit):
            worker_process_init.send(sender=None)
    finally:
        lifecycle.uninstall()
