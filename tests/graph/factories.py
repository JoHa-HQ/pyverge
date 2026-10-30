from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from hypothesis import strategies as st

from pyverge.core.types import (
    DepthViolationStrategy,
    DirectionViolationStrategy,
    VersionMissingStrategy,
    VersionValue,
)
from pyverge.graph import (
    DirectionPolicy,
    GraphBuilder,
    MigrationGraph,
    PathPlanEntry,
)
from pyverge.registry import Registry
from pyverge.schemas.types import ModelAdapter
from pyverge.versioning import (
    MigrationDescriptor,
    VersionEdge,
    VersionKey,
    VersionNode,
    default_content_hasher,
)


@dataclass(frozen=True, slots=True)
class GraphShape:
    """Synthetic graph inputs independent of any adapter or fixture."""

    namespace: str
    count: int
    connections: frozenset[tuple[int, int]]
    hydrated: frozenset[int]

    @property
    def node_indexes(self) -> range:
        return range(self.count)

    def edge_pairs(self) -> tuple[tuple[int, int], ...]:
        return tuple(sorted(self.connections))


@dataclass(frozen=True, slots=True)
class PolicyCase:
    """Behavioral policy scenario."""

    direction: DirectionPolicy
    source_index: int
    target_index: int
    steps: tuple[tuple[int, int], ...]
    on_direction_violation: DirectionViolationStrategy
    on_missing_path: VersionMissingStrategy
    depth_limit: int
    on_depth_violation: DepthViolationStrategy
    expected: str


def make_path_entry(
    source: VersionNode[Any],
    target: VersionNode[Any],
    *,
    path: tuple[str | int, ...] = (),
    steps: tuple[tuple[VersionNode[Any], VersionNode[Any]], ...] = (),
) -> PathPlanEntry:
    return PathPlanEntry(
        path=path,
        source=source,
        target=target,
        target_model=target.descriptor.ref,
        steps=steps,
        hooks=(),
        migrations=(),
    )


@dataclass(frozen=True, slots=True)
class BuiltGraph:
    registry: Registry
    nodes: tuple[VersionNode[Any], ...]
    keys: tuple[VersionKey[Any], ...]
    graph: MigrationGraph


def _noop(data: dict, context=None) -> dict:
    return data


class SyntheticGraphFactory:
    """Build synthetic registries and graphs from an injected adapter."""

    def __init__(
        self,
        adapter: ModelAdapter,
        models: Sequence[Any],
    ) -> None:
        self._adapter = adapter
        self._models = tuple(models)

    def build(self, shape: GraphShape) -> BuiltGraph:
        if shape.count > len(self._models):
            raise ValueError("shape requires more models than the factory owns")
        nodes = tuple(
            self._adapter.versionable(model).with_namespace(shape.namespace)
            for model in self._models[: shape.count]
        )
        keys = tuple(
            VersionKey(
                namespace=node.namespace,
                kind=node.kind,
                version=node.version,
            )
            for node in nodes
        )
        registry = Registry(
            name="synthetic",
            namespace=shape.namespace,
            hasher=default_content_hasher(),
        )
        for key in keys:
            registry.store(key)
        for index, node in enumerate(nodes):
            if index in shape.hydrated:
                registry.hydrate(node)
        for source_index, target_index in shape.edge_pairs():
            if source_index in shape.hydrated and target_index in shape.hydrated:
                registry.store_migration(
                    self._migration(nodes[source_index], nodes[target_index])
                )
        return BuiltGraph(
            registry=registry,
            nodes=nodes,
            keys=keys,
            graph=GraphBuilder().build(registry),
        )

    def _migration(
        self,
        source: VersionNode[VersionValue],
        target: VersionNode[VersionValue],
    ) -> VersionEdge:
        return VersionEdge(
            source=source,
            target=target,
            diff=self._adapter.diff(source, target),
            func=_noop,
            migration=MigrationDescriptor(
                strategy="synthetic",
                identity=f"{source}->{target}",
            ),
        )


def _connections(count: int) -> st.SearchStrategy[frozenset[tuple[int, int]]]:
    pairs = [
        (source, target)
        for source in range(count)
        for target in range(count)
        if source != target
    ]
    if not pairs:
        return st.just(frozenset())
    return st.frozensets(st.sampled_from(pairs))


@st.composite
def graph_shapes(draw, *, namespaces: Sequence[str], max_nodes: int = 3) -> GraphShape:
    count = draw(st.integers(min_value=1, max_value=max_nodes))
    return GraphShape(
        namespace=draw(st.sampled_from(namespaces)),
        count=count,
        connections=draw(_connections(count)),
        hydrated=frozenset(range(count)),
    )


@st.composite
def hydration_shapes(
    draw, *, namespaces: Sequence[str], max_nodes: int = 3
) -> GraphShape:
    count = draw(st.integers(min_value=1, max_value=max_nodes))
    return GraphShape(
        namespace=draw(st.sampled_from(namespaces)),
        count=count,
        connections=frozenset(),
        hydrated=draw(
            st.frozensets(
                st.integers(min_value=0, max_value=count - 1),
            )
        ),
    )
