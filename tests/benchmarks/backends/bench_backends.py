# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""Backend lock and traversal benchmarks."""

from __future__ import annotations

import pytest
import semver

from pyverge.core.graph import IgraphBackend, IndexedBackend, RustworkxBackend
from pyverge.core.versioning import EdgeKey, NodeRef, VersionKey

pytestmark = pytest.mark.benchmark

SIZES = [1_000, 10_000, 100_000]


def _graph(size: int) -> tuple[tuple[VersionKey, ...], tuple[EdgeKey, ...]]:
    nodes = tuple(
        VersionKey(
            namespace="bench",
            kind="Node",
            version=semver.Version(index, 0, 0),
            ref=NodeRef(),
        )
        for index in range(size)
    )
    edges = tuple(
        EdgeKey.from_pair(nodes[index], nodes[index + 1]) for index in range(size - 1)
    )
    return nodes, edges


@pytest.mark.parametrize("size", SIZES)
def test_lock_indexed(benchmark, size: int) -> None:
    nodes, edges = _graph(size)
    backend = benchmark(IndexedBackend.build, nodes, edges)
    assert len(backend.nodes) == size


@pytest.mark.parametrize("size", SIZES)
def test_lock_rustworkx(benchmark, size: int) -> None:
    pytest.importorskip("rustworkx")
    nodes, edges = _graph(size)
    backend = benchmark(RustworkxBackend.build, nodes, edges)
    assert len(backend.nodes) == size


@pytest.mark.parametrize("size", SIZES)
def test_lock_igraph(benchmark, size: int) -> None:
    pytest.importorskip("igraph")
    nodes, edges = _graph(size)
    backend = benchmark(IgraphBackend.build, nodes, edges)
    assert len(backend.nodes) == size


@pytest.mark.parametrize("size", SIZES)
def test_traversal_indexed(benchmark, size: int) -> None:
    nodes, _edges = _graph(size)
    backend = IndexedBackend.build(nodes, _edges)
    source, target = nodes[0], nodes[-1]

    def run() -> None:
        backend.neighbors(source)
        backend.edges_between(source, nodes[1])
        backend.shortest_path(source, target)
        backend.topological_sort()

    benchmark(run)
