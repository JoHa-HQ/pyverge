from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pyverge.registry.errors import MigrationPathError
from pyverge.schemas import JsonSchemaModelAdapter, ModelCodec, PydanticModelAdapter
from tests.examples.json import (
    USER_V2025_01_01,
    USER_V2025_03_10,
    USER_V2025_12_31,
    USER_V2026_02_28,
    USER_V2026_03_01,
)
from tests.examples.pydantic.semver import UserV1, UserV2, UserV3
from tests.graph.factories import (
    SyntheticGraphFactory,
    graph_shapes,
    hydration_shapes,
)

_PROFILES = {
    "pydantic": (
        PydanticModelAdapter,
        (UserV1, UserV2, UserV3),
    ),
    "json": (
        JsonSchemaModelAdapter,
        (USER_V2025_01_01, USER_V2025_03_10, USER_V2025_12_31),
    ),
    "json-long": (
        JsonSchemaModelAdapter,
        (
            USER_V2025_01_01,
            USER_V2025_03_10,
            USER_V2025_12_31,
            USER_V2026_02_28,
            USER_V2026_03_01,
        ),
    ),
}


def _factory(profile: str, shape) -> SyntheticGraphFactory:
    adapter_cls, models = _PROFILES[profile]
    adapter = adapter_cls(
        codec=ModelCodec(
            namespace=shape.namespace,
            version_property="version",
            kind_property="kind",
        )
    )
    return SyntheticGraphFactory(adapter, models)


def _assert_graph_paths(built, shape) -> None:
    graph = built.graph
    nodes = built.nodes

    for source_index, source in enumerate(nodes):
        for target_index, target in enumerate(nodes):
            if source_index == target_index:
                assert graph.migration_path(source, target) == []
                continue

            forward = source_index < target_index
            if forward:
                required = {
                    (index, index + 1) for index in range(source_index, target_index)
                }
            else:
                required = {
                    (index, index - 1)
                    for index in range(source_index, target_index, -1)
                }

            if required <= shape.connections:
                step = 1 if forward else -1
                expected = [
                    (nodes[index], nodes[index + step])
                    for index in range(source_index, target_index, step)
                ]
                assert graph.migration_path(source, target) == expected
            else:
                try:
                    graph.migration_path(source, target)
                except MigrationPathError:
                    pass
                else:
                    raise AssertionError(
                        f"expected missing edge for {source} -> {target}"
                    )


@pytest.mark.parametrize("namespace", ("", "orders", "billing"))
@settings(max_examples=10, deadline=None)
@given(data=st.data())
def test_synthetic_graph_paths(namespace: str, data) -> None:
    profile = data.draw(st.sampled_from(tuple(_PROFILES)))
    shape = data.draw(graph_shapes(namespaces=(namespace,)))
    built = _factory(profile, shape).build(shape)
    _assert_graph_paths(built, shape)


@pytest.mark.parametrize("namespace", ("", "orders", "billing"))
@settings(max_examples=10, deadline=None)
@given(data=st.data())
def test_synthetic_key_only_and_hydrated_entries(namespace: str, data) -> None:
    profile = data.draw(st.sampled_from(tuple(_PROFILES)))
    shape = data.draw(hydration_shapes(namespaces=(namespace,)))
    built = _factory(profile, shape).build(shape)

    assert built.graph.versions == [
        node for index, node in enumerate(built.nodes) if index in shape.hydrated
    ]
    for index, key in enumerate(built.keys):
        assert built.graph.has_entry(key)
        assert (built.graph.find_model(key) is not None) is (index in shape.hydrated)


@pytest.mark.parametrize("namespace", ("",))
@settings(max_examples=5, deadline=None)
@given(data=st.data())
def test_synthetic_long_chain(namespace: str, data) -> None:
    shape = data.draw(graph_shapes(namespaces=(namespace,), max_nodes=5))
    built = _factory("json-long", shape).build(shape)

    assert len(built.nodes) == shape.count
    assert built.graph.versions == list(built.nodes)
    _assert_graph_paths(built, shape)
