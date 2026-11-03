# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""Plan-cache sizing, keying, and reuse behaviour."""

from __future__ import annotations

import pytest
import semver

from pyverge.core.graph import latest_target_resolver
from pyverge.core.registry import Registry
from pyverge.runtime.plan_cache import PlanCache
from pyverge.schemas import PydanticModelAdapter
from tests.examples.pydantic.semver import UserV1, UserV2, migrate_v1_to_v2

_MODELS = [
    [
        PydanticModelAdapter,
        [
            semver.Version,
            "test",
            [UserV1, UserV2],
            [((UserV1, UserV2), migrate_v1_to_v2)],
        ],
    ]
]


def _payload(version: str = "1.0.0") -> dict:
    return {
        "document": {
            "kind": "User",
            "version": version,
            "name": "Alice",
            "email": "a@b.c",
            "role": "user",
        }
    }


def _flat_payload() -> dict:
    return {
        "kind": "User",
        "version": "1.0.0",
        "name": "Alice",
        "email": "a@b.c",
        "role": "user",
    }


@pytest.mark.parametrize("size", [0, -1, 1, 128])
def test_plan_cache_accepts_supported_sizes(size: int) -> None:
    assert PlanCache(size).size == size


def test_plan_cache_rejects_invalid_negative_size() -> None:
    with pytest.raises(ValueError, match="plan_cache_size"):
        PlanCache(-2)


@pytest.mark.parametrize(
    "model_adapter, registry", _MODELS, indirect=["model_adapter", "registry"]
)
def test_plan_cache_reuses_plan_for_same_shape(
    registry: Registry,
    runner_factory,
) -> None:
    runner = runner_factory(plan_cache_size=2)
    first = runner.plan(
        _payload("1.0.0"),
        "latest",
        source_model=None,
        max_depth=-1,
    )
    second = runner.plan(
        _payload("1.0.0"),
        "latest",
        source_model=None,
        max_depth=-1,
    )

    assert first.path is second.path
    assert len(runner.coordinator.cache) == 1


@pytest.mark.parametrize(
    "model_adapter, registry", _MODELS, indirect=["model_adapter", "registry"]
)
def test_plan_cache_disabled_compiles_each_time(
    registry: Registry,
    runner_factory,
) -> None:
    runner = runner_factory(plan_cache_size=0)
    first = runner.plan(_payload(), "latest", source_model=None, max_depth=-1)
    second = runner.plan(_payload(), "latest", source_model=None, max_depth=-1)

    assert first.path is not second.path
    assert len(runner.coordinator.cache) == 0


@pytest.mark.parametrize(
    "model_adapter, registry", _MODELS, indirect=["model_adapter", "registry"]
)
def test_plan_cache_keys_on_entry_identity(
    registry: Registry,
    runner_factory,
) -> None:
    runner = runner_factory(plan_cache_size=-1)
    first = runner.plan(_payload("1.0.0"), "latest", source_model=None, max_depth=-1)
    second = runner.plan(_payload("2.0.0"), "latest", source_model=None, max_depth=-1)
    third = runner.plan(_flat_payload(), "latest", source_model=None, max_depth=-1)

    assert first.path is not second.path
    assert first.path is not third.path
    assert len(runner.coordinator.cache) == 3  # noqa: PLR2004


@pytest.mark.parametrize(
    "model_adapter, registry", _MODELS, indirect=["model_adapter", "registry"]
)
def test_plan_cache_lru_evicts(registry: Registry, runner_factory) -> None:
    runner = runner_factory(plan_cache_size=1)
    runner.plan(_payload("1.0.0"), "latest", source_model=None, max_depth=-1)
    runner.plan(_payload("2.0.0"), "latest", source_model=None, max_depth=-1)

    assert len(runner.coordinator.cache) == 1


@pytest.mark.parametrize(
    "model_adapter, registry", _MODELS, indirect=["model_adapter", "registry"]
)
def test_plan_cache_skips_callable_targets(
    registry: Registry,
    runner_factory,
) -> None:
    runner = runner_factory(plan_cache_size=-1)

    runner.plan(
        _payload(),
        latest_target_resolver(registry),
        source_model=None,
        max_depth=-1,
    )

    assert len(runner.coordinator.cache) == 0
