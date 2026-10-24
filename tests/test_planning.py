"""Planning policies and path resolution."""

from __future__ import annotations

import pytest
import semver

from pyverge.execution import (
    AnyDirection,
    BackwardDirection,
    ExtractedEntry,
    ForwardDirection,
    PathResolver,
    direction_policy,
    earliest_target_resolver,
    fixed_target_resolver,
    latest_target_resolver,
    multi_target_resolver,
    skip_target_resolver,
)
from pyverge.migration import Engine, PydanticModelAdapter
from tests.examples.pydantic.semver import (
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
