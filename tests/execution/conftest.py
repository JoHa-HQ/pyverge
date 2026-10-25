"""Execution test fixtures."""

from __future__ import annotations

import pytest

from pyverge.execution.plan import ExecutionPlan, PathPlan
from tests.utils.middleware import AsyncScriptedBackend, ScriptedBackend


@pytest.fixture(params=[()], ids=["empty"])
def plan(request: pytest.FixtureRequest) -> ExecutionPlan:
    entries = request.param
    return ExecutionPlan(
        path=PathPlan(entries=entries, container=None, target_fields=frozenset()),
        payload={},
        levels=(),
    )


@pytest.fixture(
    params=[(ScriptedBackend, 0, ())],
    ids=["threaded"],
)
def execution_runner(request, manager, runtime_environment):
    backend_cls, failures, middlewares = request.param
    backend = backend_cls(failures)
    return manager().runner(
        backend=backend,
        middleware=tuple(middlewares),
        environment=runtime_environment,
    )


@pytest.fixture(
    params=[(AsyncScriptedBackend, 0, ())],
    ids=["async"],
)
def async_execution_runner(request, manager, runtime_environment):
    backend_cls, failures, middlewares = request.param
    backend = backend_cls(failures)
    return manager().runner(
        backend=backend,
        middleware=tuple(middlewares),
        environment=runtime_environment,
    )
