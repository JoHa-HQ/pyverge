# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import pytest
import semver

from pyverge.core.graph import (
    GraphCycleError,
    IndexedBackend,
    MigrationGraph,
)
from pyverge.core.registry.errors import MigrationPathError
from pyverge.core.versioning import EdgeId, EdgeKey, NodeRef, VersionKey
from pyverge.migrations.spec import MigrationSpec
from pyverge.schemas import PydanticModelAdapter
from tests.examples.pydantic.semver import (
    UserV1,
    UserV2,
    UserV3,
    migrate_v1_to_v2,
    migrate_v2_to_v3,
)

REGISTRY = [
    semver.Version,
    "test",
    [UserV1, UserV2, UserV3],
    [
        ((UserV1, UserV2), migrate_v1_to_v2),
        ((UserV2, UserV3), migrate_v2_to_v3),
    ],
]


@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, REGISTRY]],
    indirect=["model_adapter", "registry"],
)
def test_graph_state_locks_native_entries(registry, graph) -> None:
    snapshot = graph()
    state = snapshot.state

    assert isinstance(snapshot, MigrationGraph)
    assert isinstance(snapshot.backend, IndexedBackend)
    assert state.namespace == snapshot.namespace == "test"
    assert set(state.nodes) == {entry.id for entry in snapshot.nodes}
    assert set(state.edges) == {edge.id for edge in snapshot.edges("User")}
    assert state.executable_edges == snapshot.executable_edges

    edge = snapshot.migrations("User")[0]
    assert state.edge_key(edge.id) == edge
    assert state.is_executable(edge)
    assert snapshot.executable_edge_ids == frozenset(
        edge.id for edge in snapshot.migrations("User")
    )


@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, REGISTRY]],
    indirect=["model_adapter", "registry"],
)
def test_indexed_backend_traversal(registry, graph) -> None:
    snapshot = graph()
    backend = snapshot.backend
    v1, v2, v3 = registry.kind_versions("User")

    assert backend.has_node(v1)
    assert backend.index_of(v1) == 0
    assert backend.index_of(v2) == 1
    assert backend.index_of(v3) == 2  # noqa: PLR2004
    assert backend.neighbors(v1, direction="out") == (v2.id,)
    assert backend.neighbors(v2, direction="in") == (v1.id,)
    assert backend.neighbors(v2, direction="both") == (v1.id, v3.id)
    assert backend.incident(v2) == backend.outgoing(v2) | backend.incoming(v2)
    assert len(backend.edges_between(v1, v2)) == 1
    assert backend.has_edge(EdgeId.from_pair(v1, v2))


@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, REGISTRY]],
    indirect=["model_adapter", "registry"],
)
def test_backend_shortest_path_and_topological_sort(registry, graph) -> None:
    snapshot = graph()
    backend = snapshot.backend
    v1, v2, v3 = registry.kind_versions("User")

    path = backend.shortest_path(v1, v3)
    assert path is not None
    assert [(edge.source, edge.target) for edge in path] == [(v1, v2), (v2, v3)]

    first_hop = backend.shortest_path(
        v1,
        v2,
        predicate=lambda edge: edge.target == v2,
    )
    assert first_hop is not None
    assert len(first_hop) == 1
    assert first_hop[0].target == v2
    assert backend.topological_sort() == (v1.id, v2.id, v3.id)


@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, REGISTRY]],
    indirect=["model_adapter", "registry"],
)
def test_edge_path_replaces_migration_path(registry, graph) -> None:
    snapshot = graph()
    v1, v2, v3 = registry.kind_versions("User")

    edges = snapshot.edge_path(v1, v3)
    assert [(edge.source, edge.target) for edge in edges] == [(v1, v2), (v2, v3)]
    assert all(isinstance(edge, EdgeKey) for edge in edges)
    assert all(edge.discriminator == "default" for edge in edges)
    assert snapshot.migration_path(v1, v3) == [(v1, v2), (v2, v3)]

    with pytest.raises(MigrationPathError):
        snapshot.edge_path(v1, v3, discriminator="missing")


@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, REGISTRY]],
    indirect=["model_adapter", "registry"],
)
def test_edge_path_selects_parallel_discriminator(registry, graph) -> None:
    v1, v2, _ = registry.kind_versions("User")
    registry.store_migration(
        MigrationSpec(
            (v1, v2),
            migrate_v1_to_v2,
            discriminator="canary",
        )
    )

    snapshot = graph()
    canary = snapshot.edge_path(v1, v2, discriminator="canary")

    assert len(canary) == 1
    assert canary[0].discriminator == "canary"
    assert snapshot.edge_path(v1, v2)[0].discriminator == "default"


@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, REGISTRY]],
    indirect=["model_adapter", "registry"],
)
def test_lookup_flags(registry, graph) -> None:
    snapshot = graph()

    assert len(snapshot.node_entries(full=True)) == 3  # noqa: PLR2004
    assert len(snapshot.node_entries(connected=True)) == 3  # noqa: PLR2004
    assert snapshot.node_entries(orphaned=True) == ()

    executable = snapshot.edge_entries(executable=True)
    assert len(executable) == 2  # noqa: PLR2004
    assert snapshot.edge_entries(executable=False) == ()
    assert snapshot.edge_entries(origin="unset") == ()


@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, [semver.Version, "test", [], []]]],
    indirect=["model_adapter", "registry"],
)
def test_lookup_flags_identify_orphans(registry, graph) -> None:
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


@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, REGISTRY]],
    indirect=["model_adapter", "registry"],
)
def test_parallel_edges_are_sorted_by_discriminator(registry) -> None:
    v1, v2, _ = registry.kind_versions("User")

    backend = IndexedBackend.build(
        registry.entries,
        [
            EdgeKey.from_pair(v1, v2, discriminator="stable"),
            EdgeKey.from_pair(v1, v2, discriminator="canary"),
        ],
    )

    assert [edge.discriminator for edge in backend.edges_between(v1, v2)] == [
        "canary",
        "stable",
    ]
    assert backend.has_edge(
        EdgeId.from_pair(v1, v2, discriminator="stable")
    )


@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, REGISTRY]],
    indirect=["model_adapter", "registry"],
)
def test_topological_sort_rejects_cycles(registry) -> None:
    v1, v2, _ = registry.kind_versions("User")
    backend = IndexedBackend.build(
        registry.entries,
        [
            EdgeKey.from_pair(v1, v2),
            EdgeKey.from_pair(v2, v1),
        ],
    )

    with pytest.raises(GraphCycleError):
        backend.topological_sort()
