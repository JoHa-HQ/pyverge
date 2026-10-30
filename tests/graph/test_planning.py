from __future__ import annotations

from itertools import pairwise

import pytest
import semver

from pyverge.core.types import MigrationDirectionStrategy
from pyverge.execution.migrations import MigrationBindings
from pyverge.execution.plan import ExtractedEntry
from pyverge.graph import (
    AnyDirection,
    BackwardDirection,
    ForwardDirection,
    GraphBuilder,
    PathFinder,
    PathPlan,
    PolicyEngine,
    TargetCompiler,
    direction_policy,
)
from pyverge.registry import Registry
from pyverge.registry.errors import CatalogError
from pyverge.schemas import ModelCodec, PydanticModelAdapter
from pyverge.settings import VersioningSettings
from pyverge.versioning import EdgeKey, default_content_hasher, parse_version
from tests.examples.migrations import USER_JSONATA_V2_TO_V3, USER_JSONPATCH_V1_TO_V2
from tests.examples.pydantic.semver import (
    UserV1,
    UserV2,
    UserV3,
    migrate_v1_to_v2,
    migrate_v2_to_v3,
)
from tests.graph.factories import PolicyCase, make_path_entry
from tests.utils.engine import edge_from_models


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
@pytest.mark.parametrize("nodes", [[UserV1]], indirect=True)
@pytest.mark.parametrize(
    "target, expected_version, expected_steps, expected_migrations",
    [
        pytest.param("latest", "3.0.0", 2, 2, id="latest"),
        pytest.param("earliest", "1.0.0", 0, 0, id="earliest"),
        pytest.param(UserV2, "2.0.0", 1, 1, id="fixed-model"),
        pytest.param("skip", None, None, None, id="skip"),
    ],
)
def test_path_finder(  # noqa: PLR0913, PLR0917
    path_finder,
    nodes,
    target,
    expected_version: str | None,
    expected_steps: int | None,
    expected_migrations: int | None,
) -> None:
    entry = ExtractedEntry(path=("document",), node=nodes[0])

    plan = path_finder.find(
        [entry],
        target,
        container=None,
        target_fields=frozenset(),
    )

    if expected_version is None:
        assert plan.entries == ()
        return

    assert len(plan.entries) == 1
    resolved = plan.entries[0]
    assert resolved.target.version == parse_version(expected_version)
    assert len(resolved.steps) == expected_steps
    assert len(resolved.migrations) == expected_migrations
    assert resolved.hooks == ((),) * (expected_steps or 0)


@pytest.mark.parametrize("nodes", [[UserV1, UserV2]], indirect=True)
@pytest.mark.parametrize(
    "policy_cls, source_index, target_index, allowed",
    [
        pytest.param(AnyDirection, 0, 1, True, id="any-forward"),
        pytest.param(AnyDirection, 1, 0, True, id="any-backward"),
        pytest.param(ForwardDirection, 0, 1, True, id="forward-up"),
        pytest.param(ForwardDirection, 1, 0, False, id="forward-down"),
        pytest.param(BackwardDirection, 1, 0, True, id="backward-down"),
        pytest.param(BackwardDirection, 0, 1, False, id="backward-up"),
    ],
)
def test_direction_policy_allows(
    nodes,
    policy_cls,
    source_index: int,
    target_index: int,
    allowed: bool,
) -> None:
    assert policy_cls().allows(nodes[source_index], nodes[target_index]) is allowed


@pytest.mark.parametrize(
    "name, policy_cls",
    [
        ("any", AnyDirection),
        ("forward", ForwardDirection),
        ("backward", BackwardDirection),
    ],
)
def test_direction_policy_names(
    name: MigrationDirectionStrategy, policy_cls: type
) -> None:
    assert isinstance(direction_policy(name), policy_cls)


def test_unknown_direction_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown direction"):
        direction_policy("sideways")  # ty: ignore[invalid-argument-type]


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
@pytest.mark.parametrize("nodes", [[UserV1]], indirect=True)
@pytest.mark.parametrize(
    "target, expected_version",
    [
        pytest.param("latest", "3.0.0", id="latest"),
        pytest.param("earliest", "1.0.0", id="earliest"),
        pytest.param(UserV2, "2.0.0", id="model-class"),
        pytest.param("2.0.0", "2.0.0", id="version-string"),
        pytest.param({"User": UserV2, "*": "skip"}, "2.0.0", id="multi-kind"),
        pytest.param({"*": "latest"}, "3.0.0", id="multi-fallback"),
        pytest.param("skip", None, id="skip"),
    ],
)
def test_path_finder_target_forms(
    path_finder, nodes, target, expected_version: str | None
) -> None:
    entry = ExtractedEntry(path=("document",), node=nodes[0])

    plan = path_finder.find([entry], target, container=None, target_fields=frozenset())

    if expected_version is None:
        assert plan.entries == ()
    else:
        assert plan.entries[0].target.version == parse_version(expected_version)


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
@pytest.mark.parametrize("nodes", [[UserV1]], indirect=True)
def test_path_finder_cache_reuses_resolved_steps(path_finder, nodes) -> None:
    entry = ExtractedEntry(path=("document",), node=nodes[0])

    latest_once = path_finder.find(
        [entry], "latest", container=None, target_fields=frozenset()
    )
    latest_twice = path_finder.find(
        [entry], "latest", container=None, target_fields=frozenset()
    )
    earliest = path_finder.find(
        [entry], "earliest", container=None, target_fields=frozenset()
    )

    assert latest_once.entries[0].steps == latest_twice.entries[0].steps
    assert latest_once.entries[0].migrations == latest_twice.entries[0].migrations
    assert latest_once.entries[0].target.version == parse_version("3.0.0")
    assert earliest.entries[0].target.version == parse_version("1.0.0")


class _Hook:
    def before_migrate(self, name, from_version, to_version, data) -> None:
        pass

    def after_migrate(
        self, name, from_version, to_version, original_data, migrated_data
    ) -> None:
        pass

    def on_error(self, name, from_version, to_version, data, error) -> None:
        pass


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
@pytest.mark.parametrize("nodes", [[UserV1]], indirect=True)
def test_path_finder_resolves_hooks_per_step(
    engine, model_adapter, graph, nodes, registry
) -> None:
    hook = _Hook()
    versions = registry.kind_versions("User")
    for source, target in pairwise(versions):
        registry.add_hook(EdgeKey.from_pair(source, target), hook)

    snapshot = graph()
    finder = PathFinder(
        graph=snapshot,
        targets=TargetCompiler(snapshot, model_adapter),
        migrations=MigrationBindings.from_catalog(engine.registry),
        policy=PolicyEngine(
            direction=AnyDirection(),
            on_direction_violation="raise",
            on_missing_path="raise",
            depth_limit=-1,
            on_depth_violation="raise",
        ),
    )
    plan = finder.find(
        [ExtractedEntry(path=("document",), node=nodes[0])],
        "latest",
        container=None,
        target_fields=frozenset(),
    )

    assert plan.entries[0].hooks == ((hook,), (hook,))


@pytest.mark.parametrize(
    "migration, source_model, target_model, strategy",
    [
        pytest.param(
            USER_JSONPATCH_V1_TO_V2,
            UserV1,
            UserV2,
            "jsonpatch",
            id="jsonpatch",
        ),
        pytest.param(
            USER_JSONATA_V2_TO_V3,
            UserV2,
            UserV3,
            "jsonata",
            id="jsonata",
        ),
    ],
)
def test_path_finder_resolves_declarative_migrations(
    migration, source_model, target_model, strategy
) -> None:
    adapter = PydanticModelAdapter(
        codec=ModelCodec(
            namespace="",
            version_property="version",
            kind_property="kind",
        )
    )
    registry = Registry(namespace="", hasher=default_content_hasher())
    source = adapter.versionable(source_model)
    target = adapter.versionable(target_model)
    registry.store(source)
    registry.store(target)
    registry.store_migration(
        edge_from_models(
            adapter,
            VersioningSettings(),
            source_model,
            target_model,
            func=migration,
        )
    )
    snapshot = GraphBuilder().build(registry)
    finder = PathFinder(
        graph=snapshot,
        targets=TargetCompiler(snapshot, adapter),
        migrations=MigrationBindings.from_catalog(registry),
        policy=PolicyEngine(
            direction=AnyDirection(),
            on_direction_violation="raise",
            on_missing_path="raise",
            depth_limit=-1,
            on_depth_violation="raise",
        ),
    )

    plan = finder.find(
        [ExtractedEntry(path=("document",), node=source)],
        target,
        container=None,
        target_fields=frozenset(),
    )

    assert plan.entries[0].migrations == (migration,)
    descriptor = plan.entries[0].migration_descriptors[0]
    assert descriptor.strategy == strategy
    assert descriptor.identity
    assert plan.entries[0].steps[-1][1] == target
    edge = next(iter(snapshot.migrations("User")))
    assert snapshot.edge_metadata[edge]["strategy"] == strategy


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [
                semver.Version,
                "policy_test",
                [UserV1, UserV2],
                [((UserV1, UserV2), migrate_v1_to_v2)],
            ],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
@pytest.mark.parametrize("nodes", [[UserV1, UserV2]], indirect=True)
@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            PolicyCase(
                ForwardDirection(), 1, 0, (), "skip", "raise", -1, "skip", "empty"
            ),
            id="direction-skip",
        ),
        pytest.param(
            PolicyCase(
                ForwardDirection(), 1, 0, (), "raise", "raise", -1, "skip", "raise"
            ),
            id="direction-raise",
        ),
        pytest.param(
            PolicyCase(
                ForwardDirection(), 0, 1, ((0, 1),), "skip", "raise", -1, "skip", "kept"
            ),
            id="direction-allow",
        ),
        pytest.param(
            PolicyCase(
                AnyDirection(),
                0,
                1,
                ((0, 1),),
                "skip",
                "raise",
                1,
                "skip",
                "kept",
            ),
            id="depth-exact-limit",
        ),
        pytest.param(
            PolicyCase(
                AnyDirection(),
                0,
                1,
                ((1, 0),),
                "skip",
                "skip",
                -1,
                "skip",
                "empty",
            ),
            id="unbound-migration-skip",
        ),
        pytest.param(
            PolicyCase(
                AnyDirection(),
                0,
                1,
                ((1, 0),),
                "skip",
                "raise",
                -1,
                "skip",
                "raise",
            ),
            id="unbound-migration-raise",
        ),
        pytest.param(
            PolicyCase(AnyDirection(), 0, 1, (), "skip", "skip", -1, "skip", "empty"),
            id="missing-skip",
        ),
        pytest.param(
            PolicyCase(AnyDirection(), 0, 1, (), "skip", "raise", -1, "skip", "raise"),
            id="missing-raise",
        ),
        pytest.param(
            PolicyCase(
                AnyDirection(),
                0,
                1,
                ((0, 1), (1, 1)),
                "skip",
                "raise",
                1,
                "skip",
                "empty",
            ),
            id="depth-skip",
        ),
        pytest.param(
            PolicyCase(
                AnyDirection(),
                0,
                1,
                ((0, 1), (1, 1)),
                "skip",
                "raise",
                1,
                "raise",
                "raise",
            ),
            id="depth-raise",
        ),
    ],
)
def test_policy_engine(nodes, graph, case: PolicyCase) -> None:
    entry = make_path_entry(
        nodes[case.source_index],
        nodes[case.target_index],
        steps=tuple(
            (nodes[source_index], nodes[target_index])
            for source_index, target_index in case.steps
        ),
    )
    plan = PathPlan(entries=(entry,), container=None, target_fields=frozenset())
    policy = PolicyEngine(
        direction=case.direction,
        on_direction_violation=case.on_direction_violation,
        on_missing_path=case.on_missing_path,
        depth_limit=case.depth_limit,
        on_depth_violation=case.on_depth_violation,
    )

    if case.expected == "raise":
        with pytest.raises(CatalogError):
            policy.apply(plan, graph=graph())
    elif case.expected == "empty":
        assert policy.apply(plan, graph=graph()).entries == ()
    else:
        assert policy.apply(plan, graph=graph()).entries == (entry,)
