# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import pytest
import semver

from pyverge.core.registry.errors import CatalogError
from pyverge.core.versioning import EdgeKey, NodeRef, VersionKey
from pyverge.migrations.spec import MigrationSpec
from pyverge.schemas import PydanticModelAdapter
from pyverge.settings import VersioningSettings
from tests.examples.migrations import USER_JSONATA_V2_TO_V3, USER_JSONPATCH_V1_TO_V2
from tests.examples.pydantic.semver import UserV1, UserV2, UserV3, migrate_v1_to_v2
from tests.utils import envelope_model
from tests.utils.engine import edge_from_models


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
def test_graph_snapshots_catalog(model_adapter, registry, graph) -> None:
    source, target = registry.versions
    snapshot = graph()

    assert snapshot.versions == registry.versions
    assert snapshot.get_model(source) is source
    assert snapshot.migrations("User") == registry.migrations("User")
    assert type(snapshot.migrations("User")[0]) is EdgeKey
    assert not hasattr(snapshot, "hooks")
    assert snapshot.migration_path(source, target) == [(source, target)]


def test_graph_snapshots_key_only_entries(registry, graph) -> None:
    key = VersionKey(
        namespace="test", kind="User", version=semver.Version(1, 0, 0), ref=NodeRef()
    )
    registry.store(key)
    snapshot = graph()

    assert snapshot.entries[0] == key
    assert snapshot.has_entry(key)
    assert not snapshot.has_model(key)


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
def test_engine_snapshot_matches_registry_versions(engine, registry, graph) -> None:
    source, target = registry.versions
    snapshot = graph()

    assert snapshot.versions_for("User") == engine.registry.kind_versions("User")
    assert snapshot.path(source, target) == [(source, target)]


@pytest.mark.parametrize(
    "model_adapter, registry, migration, source_model, target_model, strategy",
    [
        pytest.param(
            PydanticModelAdapter,
            [semver.Version, "jsonpatch_test", [UserV1, UserV2], []],
            USER_JSONPATCH_V1_TO_V2,
            UserV1,
            UserV2,
            "jsonpatch",
            id="jsonpatch",
        ),
        pytest.param(
            PydanticModelAdapter,
            [semver.Version, "jsonata_test", [UserV2, UserV3], []],
            USER_JSONATA_V2_TO_V3,
            UserV2,
            UserV3,
            "jsonata",
            id="jsonata",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_graph_snapshots_declarative_migration_keys(  # noqa: PLR0913, PLR0917
    model_adapter,
    registry,
    graph,
    migration,
    source_model,
    target_model,
    strategy: str,
) -> None:
    registry.store_migration(
        edge_from_models(
            model_adapter,
            VersioningSettings(),
            source_model,
            target_model,
            func=migration,
        )
    )
    snapshot = graph()
    edge = next(iter(snapshot.migrations("User")))

    assert snapshot.has_migration(edge)
    assert snapshot.edge_metadata[edge]["strategy"] == strategy


def test_snapshot_is_immutable_after_registry_mutation(
    model_adapter, versioning_settings, registry, graph
) -> None:
    snapshot = graph()
    node = envelope_model(model_adapter, versioning_settings, UserV1)
    key = VersionKey(
        namespace=node.namespace,
        kind=node.kind,
        version=node.version,
        ref=NodeRef(),
    )

    target = envelope_model(model_adapter, versioning_settings, UserV2)
    registry.store(key)
    registry.hydrate(node)
    registry.hydrate(target)
    registry.store_migration(
        edge_from_models(
            model_adapter,
            VersioningSettings(),
            UserV1,
            UserV2,
            func=migrate_v1_to_v2,
        )
    )

    assert snapshot.entries == ()
    assert snapshot.versions == []


def test_empty_graph(registry, graph) -> None:
    snapshot = graph()

    assert snapshot.entries == ()
    assert snapshot.versions == []
    assert snapshot.kinds == []


def test_graph_rejects_mixed_namespaces(
    model_adapter, versioning_settings, registry, graph
) -> None:
    first = envelope_model(model_adapter, versioning_settings, UserV1).with_namespace(
        "orders"
    )
    second = envelope_model(model_adapter, versioning_settings, UserV2).with_namespace(
        "billing"
    )
    registry.store(first)
    registry.store(second)

    with pytest.raises(CatalogError, match="mix namespaces"):
        graph()


def test_graph_accepts_one_nonempty_namespace(
    model_adapter, versioning_settings, registry, graph
) -> None:
    node = envelope_model(model_adapter, versioning_settings, UserV1).with_namespace(
        "orders"
    )
    registry.store(node)

    snapshot = graph()

    assert snapshot.versions == [node]
    assert snapshot.get_model(node) is node


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [semver.Version, "test", [UserV1, UserV2], []],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_graph_preserves_edge_discriminators(registry, graph) -> None:
    source, target = registry.kind_versions("User")
    registry.store_migration(
        MigrationSpec(
            (source, target), migrate_v1_to_v2, discriminator="canary"
        )
    )
    registry.store_migration(
        MigrationSpec(
            (source, target), migrate_v1_to_v2, discriminator="stable"
        )
    )

    snapshot = graph()
    edges = snapshot.edges("User")

    assert {edge.discriminator for edge in edges} == {"canary", "stable"}
    default = EdgeKey.from_pair(source, target)
    canary = EdgeKey.from_pair(source, target, discriminator="canary")
    assert not snapshot.has_edge(default)
    assert snapshot.has_edge(canary)
    assert snapshot.get_edge(canary).discriminator == "canary"
    assert snapshot.edge_metadata[canary]["strategy"]


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
def test_snapshot_lookup_flags(registry, graph) -> None:
    snapshot = graph()

    assert len(snapshot.node_entries(full=True)) == 2  # noqa: PLR2004
    assert len(snapshot.node_entries(connected=True)) == 2  # noqa: PLR2004
    assert snapshot.node_entries(orphaned=True) == ()
    assert len(snapshot.edge_entries(executable=True)) == 1
    assert snapshot.edge_entries(executable=False) == ()
    assert snapshot.edge_entries(origin="unset") == ()


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [semver.Version, "test", [], []],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_snapshot_lookup_flags_identify_orphans(registry, graph) -> None:
    for version in ("1.0.0", "2.0.0"):
        registry.store(
            VersionKey(
                namespace="test",
                kind="User",
                version=semver.Version.parse(version),
                ref=NodeRef(),
            )
        )

    snapshot = graph()

    assert len(snapshot.node_entries(full=False)) == 2  # noqa: PLR2004
    assert len(snapshot.node_entries(orphaned=True)) == 2  # noqa: PLR2004
    assert len(snapshot.node_entries(connected=False)) == 2  # noqa: PLR2004
