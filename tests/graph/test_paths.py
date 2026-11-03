# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import pendulum
import pytest
import semver

from pyverge.core.registry.errors import MigrationPathError
from pyverge.core.versioning import EdgeKey, NodeRef, VersionKey
from pyverge.migrations.spec import MigrationSpec
from pyverge.schemas import JsonSchemaModelAdapter, PydanticModelAdapter
from pyverge.settings import VersioningSettings
from tests.examples.json import USER_V2025_01_01, USER_V2025_03_10
from tests.examples.pydantic.semver import (
    UserV1,
    UserV2,
    UserV3,
    migrate_v1_to_v2,
)
from tests.utils import edge_from_models, envelope_model, meta_versionable


@pytest.mark.parametrize(
    "model_adapter, registry, models",
    [
        pytest.param(
            PydanticModelAdapter,
            [
                semver.Version,
                "semver_test",
                [UserV1, UserV2, UserV3],
                [
                    ((UserV1, UserV2), lambda d, _: d),
                    ((UserV2, UserV3), lambda d, _: d),
                ],
            ],
            [UserV1, UserV2, UserV3],
            id="pydantic_semver",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_migration_path_forward_and_backward(registry, graph, models) -> None:
    versions = registry.kind_versions("User")
    snapshot = graph()

    forward = snapshot.migration_path(versions[0], versions[2])
    assert forward == [(versions[0], versions[1]), (versions[1], versions[2])]
    assert snapshot.migration_path(versions[0], versions[0]) == []
    with pytest.raises(MigrationPathError):
        snapshot.migration_path(versions[2], versions[0])


def test_migration_path_unregistered_raises(model_adapter, graph) -> None:
    missing = meta_versionable(model_adapter, "User", "9.9.9")
    other = meta_versionable(model_adapter, "User", "9.9.8")
    with pytest.raises(MigrationPathError):
        graph().migration_path(missing, other)


@pytest.mark.parametrize(
    "model_adapter, edge, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            [PydanticModelAdapter, UserV1, UserV2, lambda d, _: d],
            [semver.Version, "semver_test", [], []],
            id="pydantic_key_only_path",
        ),
        pytest.param(
            JsonSchemaModelAdapter,
            [
                JsonSchemaModelAdapter,
                USER_V2025_01_01,
                USER_V2025_03_10,
                lambda d, _: d,
            ],
            [pendulum.Date, "json_chrono_test", [], []],
            id="json_chrono_key_only_path",
        ),
    ],
    indirect=True,
)
def test_key_only_path_forbids_planning_until_hydrated(
    model_adapter, edge, registry, graph
) -> None:
    source, target = edge.source, edge.target
    source_key = VersionKey(
        namespace=source.namespace,
        kind=source.kind,
        version=source.version,
        ref=NodeRef(),
    )
    target_key = VersionKey(
        namespace=target.namespace,
        kind=target.kind,
        version=target.version,
        ref=NodeRef(),
    )
    registry.store(source_key)
    registry.store(target_key)

    with pytest.raises(MigrationPathError):
        graph().migration_path(source, target)

    registry.hydrate(source)
    registry.hydrate(target)
    registry.store_migration(edge)

    assert graph().migration_path(source, target) == [(source, target)]


@pytest.mark.parametrize(
    "model_adapter, edge, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            [PydanticModelAdapter, UserV1, UserV2, lambda d, _: d],
            [semver.Version, "semver_test", [UserV1, UserV2], []],
            id="pydantic_key_only_edge",
        ),
        pytest.param(
            JsonSchemaModelAdapter,
            [
                JsonSchemaModelAdapter,
                USER_V2025_01_01,
                USER_V2025_03_10,
                lambda d, _: d,
            ],
            [
                pendulum.Date,
                "json_chrono_test",
                [USER_V2025_01_01, USER_V2025_03_10],
                [],
            ],
            id="json_chrono_key_only_edge",
        ),
    ],
    indirect=True,
)
def test_key_only_edge_forbids_planning(model_adapter, edge, registry, graph) -> None:
    edge_key = EdgeKey.from_pair(edge.source, edge.target)
    registry.store_migration(edge_key)

    snapshot = graph()
    assert snapshot.has_edge(edge_key)
    assert not snapshot.has_migration(edge_key)
    with pytest.raises(MigrationPathError):
        snapshot.migration_path(edge.source, edge.target)


@pytest.mark.parametrize(
    "model_adapter, edge, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            [PydanticModelAdapter, UserV1, UserV2, lambda d, _: d],
            [semver.Version, "semver_test", [UserV1, UserV2], []],
            id="pydantic_key_only_edge_bound",
        ),
        pytest.param(
            JsonSchemaModelAdapter,
            [
                JsonSchemaModelAdapter,
                USER_V2025_01_01,
                USER_V2025_03_10,
                lambda d, _: d,
            ],
            [
                pendulum.Date,
                "json_chrono_test",
                [USER_V2025_01_01, USER_V2025_03_10],
                [],
            ],
            id="json_chrono_key_only_edge_bound",
        ),
    ],
    indirect=True,
)
def test_key_only_edge_upgrades_when_bound(
    model_adapter, edge, registry, graph
) -> None:
    edge_key = EdgeKey.from_pair(edge.source, edge.target)
    registry.store_migration(edge_key)
    registry.store_migration(edge)

    snapshot = graph()
    assert snapshot.has_migration(edge_key)
    assert snapshot.migration_path(edge.source, edge.target) == [
        (edge.source, edge.target)
    ]


def test_path_requires_complete_hydration(
    model_adapter, versioning_settings, registry, graph
) -> None:
    source = envelope_model(model_adapter, versioning_settings, UserV1)
    target = envelope_model(model_adapter, versioning_settings, UserV2)
    for node in (source, target):
        registry.store(
            VersionKey(
                namespace=node.namespace,
                kind=node.kind,
                version=node.version,
                ref=NodeRef(),
            )
        )

    with pytest.raises(MigrationPathError):
        graph().migration_path(source, target)

    registry.hydrate(source)
    with pytest.raises(MigrationPathError):
        graph().migration_path(source, target)

    registry.hydrate(target)
    with pytest.raises(MigrationPathError):
        graph().migration_path(source, target)

    registry.store_migration(
        edge_from_models(
            model_adapter,
            VersioningSettings(),
            UserV1,
            UserV2,
            func=lambda data, _: data,
        )
    )
    assert graph().migration_path(source, target) == [(source, target)]


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [
                semver.Version,
                "semver_test",
                [UserV1, UserV2],
                [((UserV1, UserV2), lambda d, _: d)],
            ],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_unrelated_key_only_nodes_do_not_block_path(registry, graph) -> None:
    source, target = registry.versions
    unrelated = VersionKey(
        namespace="test",
        kind="User",
        version=semver.Version(3, 0, 0),
        ref=NodeRef(),
    )
    registry.store(unrelated)

    snapshot = graph()

    assert snapshot.has_entry(unrelated)
    assert not snapshot.has_model(unrelated)
    assert snapshot.migration_path(source, target) == [(source, target)]


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [
                semver.Version,
                "semver_test",
                [UserV1, UserV2, UserV3],
                [
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    ((UserV2, UserV3), migrate_v1_to_v2),
                ],
            ],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_edge_path_returns_adjacent_edge_identity(registry, graph) -> None:
    v1, v2, v3 = registry.kind_versions("User")
    snapshot = graph()

    edges = snapshot.edge_path(v1, v3)

    assert [(edge.source, edge.target) for edge in edges] == [
        (v1, v2),
        (v2, v3),
    ]
    assert all(edge.discriminator == "default" for edge in edges)
    assert snapshot.migration_path(v1, v3) == [(v1, v2), (v2, v3)]

    with pytest.raises(MigrationPathError):
        snapshot.edge_path(v1, v3, discriminator="missing")


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [
                semver.Version,
                "semver_test",
                [UserV1, UserV2],
                [((UserV1, UserV2), migrate_v1_to_v2)],
            ],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_edge_path_selects_parallel_discriminator(registry, graph) -> None:
    v1, v2 = registry.kind_versions("User")
    registry.store_migration(
        MigrationSpec(
            (v1, v2),
            migrate_v1_to_v2,
            discriminator="canary",
        )
    )

    snapshot = graph()

    assert snapshot.edge_path(v1, v2)[0].discriminator == "default"
    assert snapshot.edge_path(v1, v2, discriminator="canary")[0].discriminator == (
        "canary"
    )
