"""Runtime planning, execution, policies, and backend adapters."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, cast

import pendulum
import pytest
import semver

from pyverge.core import MaxDepthExceededError, PayloadValidationError
from pyverge.execution import (
    AnyDirection,
    BackendDeclaration,
    BackwardDirection,
    CompositeExtractor,
    ExecutionPlanner,
    ExtractedEntry,
    ForwardDirection,
    PathPlan,
    PathPlanEntry,
    PathResolver,
    PolicyEngine,
    Runner,
    direction_policy,
    earliest_target_resolver,
    fixed_target_resolver,
    latest_target_resolver,
    multi_target_resolver,
    skip_target_resolver,
)
from pyverge.execution.backends import PlainBackend, ProcessBackend
from pyverge.migration import (
    Engine,
    JsonSchemaModelAdapter,
    PydanticModelAdapter,
    Registry,
)
from pyverge.registry import GraphCatalog
from pyverge.registry.errors import CatalogError
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
@pytest.mark.parametrize("runtime_backend", [(PlainBackend, {})], indirect=True)
def test_runner_plans_and_executes(
    registry: Registry,
    runner: Runner,
    snapshot,
) -> None:
    payload = _payload()

    plan = runner.plan(
        payload,
        latest_target_resolver(registry),
        container=None,
        max_depth=-1,
    )
    result = runner.execute(plan, context=None)

    assert result == snapshot


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
@pytest.mark.parametrize("runtime_backend", [(PlainBackend, {})], indirect=True)
def test_runner_migrates_with_target_container(
    registry: Registry,
    runner: Runner,
    snapshot,
) -> None:
    plan = runner.plan(
        _payload(),
        latest_target_resolver(registry),
        container=UserContainer,
        max_depth=-1,
    )
    result = runner.execute(plan, context=None)

    assert plan.path.container is UserContainer
    assert result == snapshot


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
@pytest.mark.parametrize("runtime_backend", [(PlainBackend, {})], indirect=True)
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
        container=UserContainer,
        max_depth=-1,
    )

    result = runner.execute(plan, context=None)

    assert result == _payload()


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [UserV1, UserV2, UserV3],
                [
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    ((UserV2, UserV3), migrate_v2_to_v3),
                ],
            ],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_path_resolver_builds_chain(
    engine: Engine,
    model_adapter,
    versioning_settings,
) -> None:
    source = envelope_model(model_adapter, versioning_settings, UserV1)
    entry = ExtractedEntry(path=("document",), node=source)
    resolver = PathResolver(engine.registry)

    plan = resolver.plan(
        [entry],
        latest_target_resolver(engine.registry),
        container=None,
        target_fields=frozenset(),
    )

    assert len(plan.entries) == 1
    resolved = plan.entries[0]
    assert resolved.target.version[1] == engine.adapter.of("3.0.0")
    assert len(resolved.steps) == 2  # noqa: PLR2004
    assert len(resolved.migrations) == 2  # noqa: PLR2004
    assert resolved.target_model is UserV3
    assert resolved.hooks == ((), ())


def test_direction_policies(model_adapter, versioning_settings) -> None:
    low = envelope_model(model_adapter, versioning_settings, UserV1)
    high = envelope_model(model_adapter, versioning_settings, UserV2)

    assert AnyDirection().allows(low, high)
    assert AnyDirection().allows(high, low)
    assert ForwardDirection().allows(low, high)
    assert not ForwardDirection().allows(high, low)
    assert BackwardDirection().allows(high, low)
    assert not BackwardDirection().allows(low, high)
    assert isinstance(direction_policy("any"), AnyDirection)
    assert isinstance(direction_policy("forward"), ForwardDirection)
    assert isinstance(direction_policy("backward"), BackwardDirection)


def test_unknown_direction_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown direction"):
        direction_policy("sideways")  # ty: ignore[invalid-argument-type]


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
@pytest.mark.parametrize(
    "resolver_factory, expected",
    [
        pytest.param(latest_target_resolver, "3.0.0", id="latest"),
        pytest.param(earliest_target_resolver, "1.0.0", id="earliest"),
        pytest.param(skip_target_resolver, None, id="skip"),
    ],
)
def test_target_resolvers(
    engine: Engine,
    model_adapter,
    versioning_settings,
    resolver_factory,
    expected: str | None,
) -> None:
    source = envelope_model(model_adapter, versioning_settings, UserV1)
    target = resolver_factory(engine.registry)(source)

    if expected is None:
        assert target is None
    else:
        assert target.version[1] == engine.adapter.of(expected)


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


class _GraphStub:
    name = "test"


def _graph() -> GraphCatalog:
    return cast("GraphCatalog", _GraphStub())


def _path_entry(
    source,
    target,
    *,
    path: tuple[str | int, ...],
    steps=(),
):
    return PathPlanEntry(
        path=path,
        source=source,
        target=target,
        target_model=target.model,
        steps=steps,
        hooks=(),
        migrations=(),
    )


def test_policy_engine_skips_direction_violations(
    model_adapter,
    versioning_settings,
) -> None:
    low = envelope_model(model_adapter, versioning_settings, UserV1)
    high = envelope_model(model_adapter, versioning_settings, UserV2)
    entry = _path_entry(high, low, path=())
    plan = PathPlan(entries=(entry,), container=None, target_fields=frozenset())
    policy = PolicyEngine(
        direction=ForwardDirection(),
        on_direction_violation="skip",
        on_missing_path="raise",
        depth_limit=-1,
        on_depth_violation="skip",
    )

    filtered = policy.apply(plan, graph=_graph())

    assert filtered.entries == ()


def test_policy_engine_raises_direction_violations(
    model_adapter,
    versioning_settings,
) -> None:
    low = envelope_model(model_adapter, versioning_settings, UserV1)
    high = envelope_model(model_adapter, versioning_settings, UserV2)
    entry = _path_entry(high, low, path=())
    plan = PathPlan(entries=(entry,), container=None, target_fields=frozenset())
    forward = PolicyEngine(
        direction=ForwardDirection(),
        on_direction_violation="raise",
        on_missing_path="raise",
        depth_limit=-1,
        on_depth_violation="skip",
    )
    with pytest.raises(CatalogError, match="direction policy"):
        forward.apply(plan, graph=_graph())


def test_policy_engine_skips_missing_path(
    model_adapter,
    versioning_settings,
) -> None:
    low = envelope_model(model_adapter, versioning_settings, UserV1)
    high = envelope_model(model_adapter, versioning_settings, UserV2)
    entry = _path_entry(low, high, path=())
    plan = PathPlan(entries=(entry,), container=None, target_fields=frozenset())
    policy = PolicyEngine(
        direction=AnyDirection(),
        on_direction_violation="skip",
        on_missing_path="skip",
        depth_limit=-1,
        on_depth_violation="skip",
    )

    assert policy.apply(plan, graph=_graph()).entries == ()


def test_policy_engine_depth_limit(
    model_adapter,
    versioning_settings,
) -> None:
    low = envelope_model(model_adapter, versioning_settings, UserV1)
    high = envelope_model(model_adapter, versioning_settings, UserV2)
    entry = _path_entry(
        low,
        high,
        path=(),
        steps=((low, high), (high, high)),
    )
    plan = PathPlan(entries=(entry,), container=None, target_fields=frozenset())
    policy = PolicyEngine(
        direction=AnyDirection(),
        on_direction_violation="skip",
        on_missing_path="raise",
        depth_limit=1,
        on_depth_violation="skip",
    )

    assert policy.apply(plan, graph=_graph()).entries == ()


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
        container=None,
        target_fields=frozenset(),
    )
    planner = ExecutionPlanner(
        backend=BackendDeclaration(name="local", strategy="parallel", middleware=()),
    )

    execution = planner.build(plan, {})

    assert execution.levels[0] == (child, sibling)
    assert execution.levels[1] == (parent,)
    assert execution.backend.name == "local"
    assert execution.backend.strategy == "parallel"


def test_plain_backend_runs_sync_and_async() -> None:
    backend = PlainBackend()

    assert backend.run(lambda: 1) == 1
    assert asyncio.run(backend.arun(_one)) == 1


async def _one() -> int:
    return 1


def _plus_one(value: int) -> int:
    return value + 1


def test_process_backend_runs_picklable_sync_work() -> None:
    backend = ProcessBackend(max_workers=1)
    try:
        assert backend.run(_plus_one, 1) == 2  # noqa: PLR2004
    finally:
        backend.close()


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
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            (semver.Version, "test", (), ()),
            id="pydantic_semver_empty_compound_key",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_extractor_empty_payload_returns_no_entries(
    model_adapter,
    discovery_settings,
    registry,
) -> None:
    extractor = CompositeExtractor[semver.Version](
        registry,
        validation_mode=discovery_settings.validation_mode,
        adapter=model_adapter,
    )
    assert list(extractor.extract({}, max_depth=-1)) == []


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
    extractor = CompositeExtractor(
        registry,
        validation_mode=discovery_settings.validation_mode,
        adapter=model_adapter,
    )
    entries = list(extractor.extract(_payload(), container=container, max_depth=-1))

    assert len(entries) == 1
    assert entries[0][0] == ("document",)
    assert entries[0][2].model is UserV1


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
    extractor = CompositeExtractor(
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
    extractor = CompositeExtractor(
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
    extractor = CompositeExtractor(
        registry,
        validation_mode=discovery_settings.validation_mode,
        adapter=model_adapter,
    )

    with pytest.raises(PayloadValidationError, match="recognized model type"):
        list(extractor.extract({}, container=dict))


def test_extractor_containerless_when_none(
    model_adapter,
    discovery_settings,
    registry,
) -> None:
    extractor = CompositeExtractor(
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
    extractor = CompositeExtractor(
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
        list(extractor.extract(payload, container=UserContainer))


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
    extractor = CompositeExtractor(
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

    assert len(list(extractor.extract(payload, container=UserContainer))) == 1


@pytest.mark.parametrize(
    "model_adapter, registry, expected_version, expected_age",
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
            "3.0.0",
            0,
            id="engine_migrate_latest",
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
            "2.0.0",
            None,
            id="engine_migrate_latest_json_schema",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
@pytest.mark.parametrize("runtime_backend", [(PlainBackend, {})], indirect=True)
def test_runner_migrates_to_latest(
    registry: Registry,
    runner: Runner,
    expected_version: str,
    expected_age: int | None,
) -> None:
    plan = runner.plan(
        _payload(),
        latest_target_resolver(registry),
        container=None,
        max_depth=-1,
    )
    result = runner.execute(plan, context=None)

    assert result["document"]["version"] == expected_version
    assert result["document"]["age"] == expected_age


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
@pytest.mark.parametrize("runtime_backend", [(PlainBackend, {})], indirect=True)
def test_runner_container_guided_migration(
    registry: Registry,
    runner: Runner,
) -> None:
    plan = runner.plan(
        _payload(),
        latest_target_resolver(registry),
        container=UserContainer,
        max_depth=-1,
    )
    result = runner.execute(plan, context=None)

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
@pytest.mark.parametrize("runtime_backend", [(PlainBackend, {})], indirect=True)
def test_runner_explicit_target_versionable(
    registry: Registry,
    model_adapter: PydanticModelAdapter,
    runner: Runner,
    discovery_settings,
) -> None:
    target_model = envelope_model(model_adapter, discovery_settings, UserV2)
    target = fixed_target_resolver(registry, target_model)

    plan = runner.plan(_payload(), target, container=None, max_depth=-1)
    result = runner.execute(plan, context=None)

    assert result["document"]["version"] == "2.0.0"
    assert result["document"]["age"] is None


@pytest.mark.parametrize(
    "model_adapter, registry, resolver_factory, expected_version",
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
            latest_target_resolver,
            "3.0.0",
            id="latest",
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
            skip_target_resolver,
            "1.0.0",
            id="skip",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
@pytest.mark.parametrize("runtime_backend", [(PlainBackend, {})], indirect=True)
def test_runner_target_policy(
    registry: Registry,
    runner: Runner,
    resolver_factory: Callable[[Registry[semver.Version]], Any],
    expected_version: str,
) -> None:
    plan = runner.plan(
        _payload(),
        resolver_factory(registry),
        container=None,
        max_depth=-1,
    )
    result = runner.execute(plan, context=None)

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
            id="engine_noop_same_version",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
@pytest.mark.parametrize("runtime_backend", [(PlainBackend, {})], indirect=True)
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
    plan = runner.plan(
        payload,
        latest_target_resolver(registry),
        container=None,
        max_depth=-1,
    )

    assert runner.execute(plan, context=None)["document"]["version"] == "3.0.0"


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
@pytest.mark.parametrize("runtime_backend", [(PlainBackend, {})], indirect=True)
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
    plan = runner.plan(
        payload,
        latest_target_resolver(registry),
        container=None,
        max_depth=-1,
    )

    assert runner.execute(plan, context=None)["document"]["version"] == "2025-12-31"
