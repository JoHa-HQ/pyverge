# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""Runtime planning, execution, policies, and backend adapters."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, TypeVar, cast

import pendulum
import pytest
import semver
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pyverge.core import MaxDepthExceededError, PayloadValidationError
from pyverge.core.engine import Engine
from pyverge.core.graph import (
    PathPlan,
    PathPlanEntry,
    earliest_target_resolver,
    fixed_target_resolver,
    latest_target_resolver,
    multi_target_resolver,
    skip_target_resolver,
)
from pyverge.core.registry import Registry
from pyverge.core.versioning import (
    EdgeKey,
    VersionNode,
)
from pyverge.runtime import (
    ExecutionPlanner,
    PayloadWalker,
    Runner,
)
from pyverge.runtime.backends import AsyncBackend, ProcessBackend, ThreadedBackend
from pyverge.runtime.context import (
    MigrationContext,
    RunContext,
    StepContext,
)
from pyverge.runtime.errors import (
    AsyncExecutionRequired,
    TargetValidationError,
    UnknownModelError,
)
from pyverge.schemas import JsonSchemaModelAdapter, ModelCodec, PydanticModelAdapter
from tests.examples.json import USER_V1_0_0, USER_V2_0_0
from tests.examples.pydantic.chrono import (
    UserV20250310,
    UserV20251231,
)
from tests.examples.pydantic.chrono import (
    migrate_v1_to_v2 as migrate_chrono_v1_to_v2,
)
from tests.examples.pydantic.semver import (
    UserContainer,
    UserV1,
    UserV2,
    UserV3,
    migrate_v1_to_v2,
    migrate_v2_to_v3,
)
from tests.utils.engine import envelope_model

V = TypeVar("V", semver.Version, pendulum.Date)


def _sync(value: Any) -> dict[str, Any]:
    assert not inspect.isawaitable(value)
    return value


def _run(runner: Runner, *args: Any, **kwargs: Any) -> dict[str, Any]:
    return _sync(runner.run(*args, **kwargs))


@st.composite
def _user_v1_payloads(draw):
    return {
        "document": {
            "kind": "User",
            "version": "1.0.0",
            "name": draw(st.text(min_size=1, max_size=20)),
            "email": draw(st.emails()),
            "role": draw(st.sampled_from(["admin", "user", "guest"])),
        }
    }


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [UserV1, UserV2],
                [((UserV1, UserV2), migrate_v1_to_v2)],
            ],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
@pytest.mark.parametrize(
    "runtime_backend", [(ThreadedBackend, {"max_workers": 0})], indirect=True
)
@settings(
    max_examples=25,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(payload=_user_v1_payloads())
def test_runner_preserves_generated_payload(
    registry: Registry,
    runner: Runner,
    payload: dict,
) -> None:
    result = _run(
        runner,
        payload,
        latest_target_resolver(registry),
        source_model=None,
        max_depth=-1,
        context=None,
    )

    assert result["document"]["version"] == "2.0.0"
    assert result["document"]["name"] == payload["document"]["name"]
    assert result["document"]["email"] == payload["document"]["email"]
    assert result["document"]["role"] == payload["document"]["role"]
    assert result["document"]["age"] is None


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [semver.Version, "test", [UserV1, UserV2, UserV3], []],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_fixed_and_multi_target_resolvers(
    engine: Engine,
    model_adapter,
    versioning_settings,
) -> None:
    source = envelope_model(model_adapter, versioning_settings, UserV1)
    fixed = envelope_model(model_adapter, versioning_settings, UserV2)
    fixed_resolver = fixed_target_resolver(engine.registry, fixed)
    multi = multi_target_resolver(
        {"User": fixed_resolver, "*": skip_target_resolver(engine.registry)}
    )

    assert fixed_resolver(source) is fixed
    assert multi(source) is fixed


def _path_entry(
    source: VersionNode[V],
    target: VersionNode[V],
    *,
    path: tuple[str | int, ...],
    steps=(),
) -> PathPlanEntry[V]:
    return PathPlanEntry(
        path=path,
        source=source,
        target=target,
        target_model=target.descriptor.ref,
        steps=steps,
        edges=(),
    )


def test_execution_planner_builds_levels(
    model_adapter,
    versioning_settings,
) -> None:
    low = envelope_model(model_adapter, versioning_settings, UserV1)
    high = envelope_model(model_adapter, versioning_settings, UserV2)
    parent = _path_entry(low, high, path=("document",))
    child = _path_entry(low, high, path=("document", "child"))
    sibling = _path_entry(low, high, path=("other",))
    plan = PathPlan(
        entries=(parent, child, sibling),
        source_model=None,
    )
    planner = ExecutionPlanner(bindings=cast("Any", object()))

    execution = planner.build(plan, {})

    assert tuple(entry.plan for entry in execution.levels[0]) == (child, sibling)
    assert tuple(entry.plan for entry in execution.levels[1]) == (parent,)


def _plus_one(value: int) -> int:
    return value + 1


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [UserV1, UserV2],
                [((UserV1, UserV2), migrate_v1_to_v2)],
            ],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_runner_process_backend(manager, registry: Registry, model_adapter) -> None:
    backend = ProcessBackend(max_workers=1)
    try:
        result = _run(
            manager().runner(runtime=backend),
            _payload(),
            latest_target_resolver(registry),
            source_model=None,
            max_depth=-1,
            context=None,
        )
    finally:
        backend.close()

    assert result["document"]["version"] == "2.0.0"


@pytest.mark.parametrize(
    ("target_case", "expected"),
    [
        pytest.param(None, "1.0.0", id="none"),
        pytest.param("skip", "1.0.0", id="skip"),
        pytest.param("latest", "2.0.0", id="latest"),
        pytest.param("earliest", "1.0.0", id="earliest"),
        pytest.param("2.0.0", "2.0.0", id="pinned"),
        pytest.param("model", "2.0.0", id="model"),
        pytest.param("dict", "2.0.0", id="per-kind"),
        pytest.param("wildcard", "2.0.0", id="wildcard"),
        pytest.param("fixed", "2.0.0", id="fixed"),
    ],
)
@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [UserV1, UserV2],
                [((UserV1, UserV2), migrate_v1_to_v2)],
            ],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_runner_target_policy_forms(
    manager,
    model_adapter,
    versioning_settings,
    target_case,
    expected: str,
) -> None:
    if target_case == "model":
        target = UserV2
    elif target_case == "dict":
        target = {"User": "2.0.0"}
    elif target_case == "wildcard":
        target = {"*": "2.0.0"}
    elif target_case == "fixed":
        target = model_adapter.versionable(UserV2)
    else:
        target = target_case

    result = manager().runner().run(_payload(), target)

    assert result["document"]["version"] == expected


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            [
                semver.Version,
                "user_test",
                [UserV1, UserV2],
                [((UserV1, UserV2), migrate_v1_to_v2)],
            ],
            id="pydantic",
        ),
    ],
    indirect=True,
)
def test_validate_target_rejects_invalid_payload(manager) -> None:
    invalid = _payload()
    invalid["document"]["version"] = "2.0.0"
    del invalid["document"]["name"]

    with pytest.raises(TargetValidationError):
        manager().runner().run(invalid, "2.0.0", validate_target=True)

    result = manager().runner().run(invalid, "2.0.0")
    assert result["document"]["version"] == "2.0.0"


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            [
                semver.Version,
                "user_test",
                [UserV1, UserV2],
                [((UserV1, UserV2), migrate_v1_to_v2)],
            ],
            id="pydantic",
        ),
    ],
    indirect=True,
)
def test_run_carries_source_and_target_contracts(manager) -> None:
    result = (
        manager()
        .runner()
        .run(
            _payload(),
            "2.0.0",
            source_model=None,
            validate_target=True,
        )
    )

    assert result["document"]["version"] == "2.0.0"
    assert result["document"]["age"] is None


def _payload() -> dict:
    return {
        "document": {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "email": "a@b.c",
            "role": "user",
        }
    }


@pytest.mark.parametrize(
    "model_adapter, registry, container",
    [
        pytest.param(
            PydanticModelAdapter,
            (semver.Version, "test", (UserV1, UserV2), ()),
            None,
            id="compound_key_semver",
        ),
        pytest.param(
            PydanticModelAdapter,
            (semver.Version, "test", (UserV1, UserV2), ()),
            UserContainer,
            id="pydantic_container_semver",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_extractor_finds_registered_versioned_dict(
    model_adapter,
    discovery_settings,
    registry,
    container: type | None,
) -> None:
    extractor = PayloadWalker(
        registry,
        validation_mode=discovery_settings.validation_mode,
        adapter=model_adapter,
    )
    entries = list(extractor.extract(_payload(), source_model=container, max_depth=-1))

    assert len(entries) == 1
    assert entries[0][0] == ("document",)
    assert entries[0][2].model_id.endswith("UserV1")


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            (semver.Version, "test", (UserV1,), ()),
            id="pydantic_semver_user_v1_unknown",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_extractor_unknown_version_is_skipped(
    model_adapter,
    discovery_settings,
    registry,
) -> None:
    extractor = PayloadWalker(
        registry,
        validation_mode=discovery_settings.validation_mode,
        adapter=model_adapter,
    )
    payload = {"document": {"kind": "User", "version": "9.9.9", "name": "Alice"}}

    assert list(extractor.extract(payload)) == []


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            (semver.Version, "test", (UserV1,), ()),
            id="pydantic_semver_user_v1_max_depth",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_extractor_max_depth_exceeded_for_nested_entry(
    model_adapter,
    discovery_settings,
    registry,
) -> None:
    extractor = PayloadWalker(
        registry,
        validation_mode=discovery_settings.validation_mode,
        adapter=model_adapter,
    )
    payload = {
        "document": {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "nested": {"kind": "User", "version": "1.0.0", "name": "Bob"},
        }
    }

    with pytest.raises(MaxDepthExceededError):
        list(extractor.extract(payload, max_depth=0))


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            (semver.Version, "test", (), ()),
            id="pydantic_semver_empty_pydantic",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_extractor_incompatible_container_fails_fast(
    model_adapter,
    discovery_settings,
    registry,
) -> None:
    extractor = PayloadWalker(
        registry,
        validation_mode=discovery_settings.validation_mode,
        adapter=model_adapter,
    )

    with pytest.raises(PayloadValidationError, match="recognized model type"):
        list(extractor.extract({}, source_model=dict))


def test_extractor_containerless_when_none(
    model_adapter,
    discovery_settings,
    registry,
) -> None:
    extractor = PayloadWalker(
        registry,
        validation_mode=discovery_settings.validation_mode,
        adapter=model_adapter,
    )

    assert list(extractor.extract({})) == []


@pytest.mark.parametrize(
    "model_adapter, registry, discovery_settings",
    [
        pytest.param(
            PydanticModelAdapter,
            (semver.Version, "test", (UserV1,), ()),
            {"validation_mode": "strict"},
            id="validation_strict",
        ),
        pytest.param(
            PydanticModelAdapter,
            (semver.Version, "test", (UserV1,), ()),
            {"validation_mode": "lax"},
            id="validation_lax",
        ),
    ],
    indirect=["model_adapter", "registry", "discovery_settings"],
)
def test_extractor_invalid_payload_raises(
    model_adapter,
    discovery_settings,
    registry,
) -> None:
    extractor = PayloadWalker(
        registry,
        validation_mode=discovery_settings.validation_mode,
        adapter=model_adapter,
    )
    payload = {
        "document": {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "email": "a@example.com",
            "role": "wrong-role",
        }
    }

    with pytest.raises(PayloadValidationError):
        list(extractor.extract(payload, source_model=UserContainer))


@pytest.mark.parametrize(
    "model_adapter, registry, discovery_settings",
    [
        pytest.param(
            PydanticModelAdapter,
            (semver.Version, "test", (UserV1,), ()),
            {"validation_mode": "none"},
            id="validation_none",
        ),
    ],
    indirect=["model_adapter", "registry", "discovery_settings"],
)
def test_extractor_validation_mode_none_skips_validate(
    model_adapter,
    discovery_settings,
    registry,
) -> None:
    extractor = PayloadWalker(
        registry,
        validation_mode=discovery_settings.validation_mode,
        adapter=model_adapter,
    )
    payload = {
        "document": {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "email": "a@example.com",
            "role": "wrong-role",
        }
    }

    assert len(list(extractor.extract(payload, source_model=UserContainer))) == 1


@pytest.mark.parametrize(
    ("model_adapter", "registry", "policy", "expected_version"),
    [
        pytest.param(
            PydanticModelAdapter,
            (
                semver.Version,
                "test",
                (UserV1, UserV2, UserV3),
                (
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    ((UserV2, UserV3), migrate_v2_to_v3),
                ),
            ),
            "latest",
            "3.0.0",
            id="semver-latest",
        ),
        pytest.param(
            PydanticModelAdapter,
            (
                semver.Version,
                "test",
                (UserV1, UserV2, UserV3),
                (
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    ((UserV2, UserV3), migrate_v2_to_v3),
                ),
            ),
            "earliest",
            "1.0.0",
            id="semver-earliest",
        ),
        pytest.param(
            PydanticModelAdapter,
            (
                semver.Version,
                "test",
                (UserV1, UserV2, UserV3),
                (
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    ((UserV2, UserV3), migrate_v2_to_v3),
                ),
            ),
            "fixed",
            "2.0.0",
            id="semver-fixed",
        ),
        pytest.param(
            PydanticModelAdapter,
            (
                semver.Version,
                "test",
                (UserV1, UserV2, UserV3),
                (
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    ((UserV2, UserV3), migrate_v2_to_v3),
                ),
            ),
            "skip",
            "1.0.0",
            id="semver-skip",
        ),
        pytest.param(
            JsonSchemaModelAdapter,
            (
                semver.Version,
                "test",
                (USER_V1_0_0, USER_V2_0_0),
                (
                    (
                        (USER_V1_0_0, USER_V2_0_0),
                        lambda d, _: {**d, "version": "2.0.0"},
                    ),
                ),
            ),
            "latest",
            "2.0.0",
            id="json-latest",
        ),
        pytest.param(
            JsonSchemaModelAdapter,
            (
                semver.Version,
                "test",
                (USER_V1_0_0, USER_V2_0_0),
                (
                    (
                        (USER_V1_0_0, USER_V2_0_0),
                        lambda d, _: {**d, "version": "2.0.0"},
                    ),
                ),
            ),
            "earliest",
            "1.0.0",
            id="json-earliest",
        ),
        pytest.param(
            JsonSchemaModelAdapter,
            (
                semver.Version,
                "test",
                (USER_V1_0_0, USER_V2_0_0),
                (
                    (
                        (USER_V1_0_0, USER_V2_0_0),
                        lambda d, _: {**d, "version": "2.0.0"},
                    ),
                ),
            ),
            "fixed",
            "2.0.0",
            id="json-fixed",
        ),
        pytest.param(
            JsonSchemaModelAdapter,
            (
                semver.Version,
                "test",
                (USER_V1_0_0, USER_V2_0_0),
                (
                    (
                        (USER_V1_0_0, USER_V2_0_0),
                        lambda d, _: {**d, "version": "2.0.0"},
                    ),
                ),
            ),
            "skip",
            "1.0.0",
            id="json-skip",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
@pytest.mark.parametrize(
    "runtime_backend", [(ThreadedBackend, {"max_workers": 0})], indirect=True
)
def test_runner_migrates_with_policy(
    registry: Registry,
    runner: Runner,
    policy: str,
    expected_version: str,
) -> None:
    if policy == "earliest":
        resolver = earliest_target_resolver(registry)
    elif policy == "fixed":
        resolver = fixed_target_resolver(registry, registry.kind_versions("User")[1])
    elif policy == "skip":
        resolver = skip_target_resolver(registry)
    else:
        resolver = latest_target_resolver(registry)

    result = _run(
        runner,
        _payload(),
        resolver,
        source_model=None,
        max_depth=-1,
        context=None,
    )

    assert result["document"]["version"] == expected_version


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            (
                semver.Version,
                "test",
                (UserV1, UserV2, UserV3),
                (
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    ((UserV2, UserV3), migrate_v2_to_v3),
                ),
            ),
            id="engine_container_guided",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
@pytest.mark.parametrize(
    "runtime_backend", [(ThreadedBackend, {"max_workers": 0})], indirect=True
)
def test_runner_container_guided_migration(
    registry: Registry,
    runner: Runner,
) -> None:
    plan = runner.plan(
        _payload(),
        latest_target_resolver(registry),
        source_model=UserContainer,
        max_depth=-1,
    )
    result = _sync(runner.execute(plan, context=None))

    assert result["document"]["version"] == "3.0.0"


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            (
                semver.Version,
                "test",
                (UserV1, UserV2, UserV3),
                (
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    ((UserV2, UserV3), migrate_v2_to_v3),
                ),
            ),
            id="engine_explicit_target_v2",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
@pytest.mark.parametrize(
    "runtime_backend", [(ThreadedBackend, {"max_workers": 0})], indirect=True
)
def test_runner_explicit_target_versionable(
    registry: Registry,
    model_adapter: PydanticModelAdapter,
    runner: Runner,
    discovery_settings,
) -> None:
    target_model = envelope_model(model_adapter, discovery_settings, UserV2)
    target = fixed_target_resolver(registry, target_model)

    result = _run(
        runner, _payload(), target, source_model=None, max_depth=-1, context=None
    )

    assert result["document"]["version"] == "2.0.0"
    assert result["document"]["age"] is None


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [UserV1, UserV2],
                [((UserV1, UserV2), migrate_v1_to_v2)],
            ],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
@pytest.mark.parametrize(
    "runtime_backend", [(ThreadedBackend, {"max_workers": 0})], indirect=True
)
def test_runner_noop_when_target_equals_source(
    registry: Registry,
    model_adapter: PydanticModelAdapter,
    runner: Runner,
    versioning_settings,
) -> None:
    source = envelope_model(model_adapter, versioning_settings, UserV1)
    plan = runner.plan(
        _payload(),
        fixed_target_resolver(registry, source),
        source_model=UserContainer,
        max_depth=-1,
    )

    result = _sync(runner.execute(plan, context=None))

    assert result == _payload()


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            (
                semver.Version,
                "test",
                (UserV1, UserV2, UserV3),
                (
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    ((UserV2, UserV3), migrate_v2_to_v3),
                ),
            ),
            id="engine_noop_same_version",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
@pytest.mark.parametrize(
    "runtime_backend", [(ThreadedBackend, {"max_workers": 0})], indirect=True
)
def test_runner_no_op_when_source_equals_target(
    registry: Registry,
    runner: Runner,
) -> None:
    payload = {
        "document": {
            "kind": "User",
            "version": "3.0.0",
            "name": "Alice",
            "email": "a@example.com",
            "role": "user",
            "age": 0,
            "status": "active",
        }
    }
    result = _run(
        runner,
        payload,
        latest_target_resolver(registry),
        source_model=None,
        max_depth=-1,
        context=None,
    )

    assert result["document"]["version"] == "3.0.0"


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            (
                pendulum.Date,
                "test",
                (UserV20250310, UserV20251231),
                (((UserV20250310, UserV20251231), migrate_chrono_v1_to_v2),),
            ),
            id="pydantic_chrono_engine",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
@pytest.mark.parametrize(
    "runtime_backend", [(ThreadedBackend, {"max_workers": 0})], indirect=True
)
def test_chrono_runner_migrates_to_latest(
    registry: Registry,
    runner: Runner,
) -> None:
    payload = {
        "document": {
            "kind": "User",
            "version": "2025-03-10",
            "name": "Alice",
            "email": "a@example.com",
            "role": "user",
        }
    }
    result = _run(
        runner,
        payload,
        latest_target_resolver(registry),
        source_model=None,
        max_depth=-1,
        context=None,
    )

    assert result["document"]["version"] == "2025-12-31"


def test_migration_context_layers_resolve_precedence() -> None:
    context = MigrationContext.layered({"a": 1}, {"a": 2, "b": 3})

    assert context["a"] == 1
    assert context["b"] == 3  # noqa: PLR2004
    assert dict(context) == {"a": 1, "b": 3}
    assert len(context) == len(("a", "b"))


def test_step_context_layers_bindings(execution_environment) -> None:
    run = RunContext(
        run_id="run-1",
        environment=execution_environment,
        bindings=MigrationContext.create({"tenant": "acme", "region": "eu"}),
    )
    source = envelope_model(
        PydanticModelAdapter(
            codec=ModelCodec(
                namespace="test", version_property="version", kind_property="kind"
            )
        ),
        None,
        UserV1,
    )
    target = envelope_model(
        PydanticModelAdapter(
            codec=ModelCodec(
                namespace="test", version_property="version", kind_property="kind"
            )
        ),
        None,
        UserV2,
    )
    step = StepContext(
        run=run,
        path=("document",),
        index=0,
        source=source,
        target=target,
        edge=EdgeKey.from_pair(source, target),
        bindings=MigrationContext.create({"tenant": "override"}),
    )

    assert step.view["tenant"] == "override"
    assert step.view["region"] == "eu"


@pytest.mark.parametrize(
    "model_adapter, versioning_settings, source_cls, target_cls, version_type",
    [
        pytest.param(
            PydanticModelAdapter,
            {},
            UserV1,
            UserV2,
            semver.Version,
            id="semver",
        ),
        pytest.param(
            PydanticModelAdapter,
            {},
            UserV20250310,
            UserV20251231,
            pendulum.Date,
            id="date",
        ),
    ],
    indirect=["model_adapter", "versioning_settings"],
)
def test_plan_preserves_version_value(
    model_adapter,
    versioning_settings,
    source_cls,
    target_cls,
    version_type,
) -> None:
    source = envelope_model(model_adapter, versioning_settings, source_cls)
    target = envelope_model(model_adapter, versioning_settings, target_cls)
    entry = PathPlanEntry(
        path=(),
        source=cast("Any", source),
        target=cast("Any", target),
        target_model=target.descriptor.ref,
        steps=(),
        edges=(),
    )
    plan = PathPlan(
        entries=(entry,),
        source_model=None,
    )
    resolved = plan.entries[0]

    assert type(resolved.source.version) is version_type
    assert type(resolved.target.version) is version_type


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [UserV1, UserV2],
                [((UserV1, UserV2), migrate_v1_to_v2)],
            ],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
@pytest.mark.parametrize(
    "runtime_backend",
    [(ThreadedBackend, {"max_workers": 0})],
    indirect=True,
)
def test_runner_rejects_unknown_target_model(
    registry: Registry,
    runner: Runner,
    monkeypatch,
) -> None:
    monkeypatch.setattr(runner.adapter, "identify", lambda _handle: False)

    with pytest.raises(UnknownModelError):
        runner.plan(
            _payload(),
            latest_target_resolver(registry),
            source_model=None,
            max_depth=-1,
        )


async def _async_migrate(data, context):
    data["age"] = None
    return data


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [UserV1, UserV2],
                [((UserV1, UserV2), migrate_v1_to_v2)],
            ],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
@pytest.mark.parametrize(
    "runtime_backend",
    [(AsyncBackend, {"backend": "asyncio", "backend_options": {}, "max_workers": 0})],
    indirect=True,
)
@settings(
    max_examples=25,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(payload=_user_v1_payloads())
def test_runner_async_backend_runs_sync_migration(
    registry: Registry,
    runner: Runner,
    payload: dict,
) -> None:
    result = asyncio.run(
        runner.run(
            payload,
            latest_target_resolver(registry),
            source_model=None,
            max_depth=-1,
            context=None,
        )
    )

    assert result["document"]["version"] == "2.0.0"


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [UserV1, UserV2],
                [((UserV1, UserV2), _async_migrate)],
            ],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
@pytest.mark.parametrize(
    "runtime_backend",
    [(AsyncBackend, {"backend": "asyncio", "backend_options": {}, "max_workers": 0})],
    indirect=True,
)
def test_runner_async_backend_runs_coroutine_migration(
    registry: Registry,
    runner: Runner,
) -> None:
    result = asyncio.run(
        runner.run(
            _payload(),
            latest_target_resolver(registry),
            source_model=None,
            max_depth=-1,
            context=None,
        )
    )

    assert result["document"]["version"] == "2.0.0"
    assert result["document"]["age"] is None


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [UserV1, UserV2],
                [((UserV1, UserV2), _async_migrate)],
            ],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
@pytest.mark.parametrize(
    "runtime_backend", [(ThreadedBackend, {"max_workers": 0})], indirect=True
)
def test_runner_sync_backend_rejects_coroutine_migration(
    registry: Registry,
    runner: Runner,
) -> None:
    with pytest.raises(AsyncExecutionRequired):
        runner.run(
            _payload(),
            latest_target_resolver(registry),
            source_model=None,
            max_depth=-1,
            context=None,
        )


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [UserV1, UserV2],
                [((UserV1, UserV2), migrate_v1_to_v2)],
            ],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
@pytest.mark.parametrize(
    "runtime_backend", [(ThreadedBackend, {"max_workers": 0})], indirect=True
)
def test_runner_calls_sync_hooks(
    engine: Engine,
    registry: Registry,
    runner_factory,
) -> None:
    calls: list[str] = []

    class _Hook:
        def before_migrate(  # noqa: PLR0913
            self, name, from_version, to_version, data, *, migration=None, state=None
        ):
            calls.append("before")

        def after_migrate(  # noqa: PLR0913
            self,
            name,
            from_version,
            to_version,
            original_data,
            migrated_data,
            *,
            migration=None,
            state=None,
        ):
            calls.append("after")

        def on_error(  # noqa: PLR0913
            self,
            name,
            from_version,
            to_version,
            data,
            error,
            *,
            migration=None,
            state=None,
        ):
            calls.append("error")

    source = engine.get_model(engine.adapter.version_key(kind="User", version="1.0.0"))
    target = engine.get_model(engine.adapter.version_key(kind="User", version="2.0.0"))
    edge_key = EdgeKey.from_pair(source, target)
    hook = cast("Any", _Hook())
    binding = getattr(registry, "bindings").add_hook(edge_key, hook)
    engine.add_hook(edge_key, binding.ref)

    _run(
        runner_factory(),
        _payload(),
        latest_target_resolver(registry),
        source_model=None,
        max_depth=-1,
        context=None,
    )

    assert calls == ["before", "after"]


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [UserV1, UserV2],
                [((UserV1, UserV2), migrate_v1_to_v2)],
            ],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
@pytest.mark.parametrize(
    "runtime_backend",
    [(AsyncBackend, {"backend": "asyncio", "backend_options": {}, "max_workers": 0})],
    indirect=True,
)
def test_runner_awaits_async_hooks(
    engine: Engine,
    registry: Registry,
    runner_factory,
) -> None:
    calls: list[str] = []

    class _AsyncHook:
        async def before_migrate(  # noqa: PLR0913
            self, name, from_version, to_version, data, *, migration=None, state=None
        ):
            calls.append("before")

        async def after_migrate(  # noqa: PLR0913
            self,
            name,
            from_version,
            to_version,
            original_data,
            migrated_data,
            *,
            migration=None,
            state=None,
        ):
            calls.append("after")

        def on_error(  # noqa: PLR0913
            self,
            name,
            from_version,
            to_version,
            data,
            error,
            *,
            migration=None,
            state=None,
        ):
            calls.append("error")

    source = engine.get_model(engine.adapter.version_key(kind="User", version="1.0.0"))
    target = engine.get_model(engine.adapter.version_key(kind="User", version="2.0.0"))
    edge_key = EdgeKey.from_pair(source, target)
    hook = cast("Any", _AsyncHook())
    binding = getattr(registry, "bindings").add_hook(edge_key, hook)
    engine.add_hook(edge_key, binding.ref)

    asyncio.run(
        runner_factory().run(
            _payload(),
            latest_target_resolver(registry),
            source_model=None,
            max_depth=-1,
            context=None,
        )
    )

    assert calls == ["before", "after"]
