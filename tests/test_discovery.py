"""Build discovery and manager source reflection."""

from __future__ import annotations

import asyncio

import pytest

from pyverge import Manager
from pyverge.discovery import (
    MigrationDescriptor,
    MigrationSpec,
    ModelDescriptor,
    SourceDescriptor,
)
from pyverge.discovery.reflection import (
    CallableDiffDiscovery,
    JsonPatchDiffDiscovery,
)
from pyverge.migrations.json_patch import JsonPatch
from pyverge.registry.errors import GraphLockedError
from pyverge.schemas import ModelCodec, PydanticModelAdapter
from pyverge.versioning import EdgeKey
from tests.examples.pydantic.semver import UserV1, UserV2, migrate_v1_to_v2
from tests.utils.source import StaticSource

_ADAPTER = PydanticModelAdapter(codec=ModelCodec())
_MIGRATION = MigrationDescriptor(
    MigrationSpec(
        (_ADAPTER.versionable(UserV1), _ADAPTER.versionable(UserV2)),
        migrate_v1_to_v2,
    ),
    "test",
    {},
)


@pytest.mark.parametrize(
    "source, expected_models, expected_migrations",
    [
        pytest.param(
            (
                [
                    ModelDescriptor(UserV1, "test", {}),
                    ModelDescriptor(UserV2, "test", {}),
                    _MIGRATION,
                ],
                "test",
            ),
            len((UserV1, UserV2)),
            1,
            id="models-and-migration",
        ),
        pytest.param(
            ([ModelDescriptor(UserV1, "test", {})], "test"),
            1,
            0,
            id="single-model",
        ),
    ],
    indirect=["source"],
)
def test_reflect_registers(
    manager: type[Manager],
    source: StaticSource,
    expected_models: int,
    expected_migrations: int,
) -> None:
    report = manager.reflect(source)

    assert report.registered_models == expected_models
    assert report.registered_migrations == expected_migrations
    assert len(manager._default_engine.registry.versions) == expected_models


@pytest.mark.parametrize(
    "source",
    [
        (
            [
                ModelDescriptor(UserV1, "test", {}),
                ModelDescriptor(UserV2, "test", {}),
                _MIGRATION,
            ],
            "test",
        )
    ],
    indirect=["source"],
)
def test_reflect_registers_migration_edge(
    manager: type[Manager],
    source: StaticSource,
) -> None:
    engine = manager._default_engine
    manager.reflect(source)

    edge = EdgeKey.from_pair(
        engine.get_model(engine.adapter.version_key(kind="User", version="1.0.0")),
        engine.get_model(engine.adapter.version_key(kind="User", version="2.0.0")),
    )
    assert engine.registry.has_migration(edge)


@pytest.mark.parametrize(
    "source",
    [([SourceDescriptor(None, "test", {})], "test")],
    indirect=["source"],
)
def test_reflect_skips_unknown_descriptor(
    manager: type[Manager], source: StaticSource
) -> None:
    report = manager.reflect(source)

    assert report.descriptors == 0
    assert report.skipped == ("SourceDescriptor",)


@pytest.mark.parametrize("source", [([], "test")], indirect=["source"])
def test_reflect_after_instance_raises(
    manager: type[Manager],
    source: StaticSource,
) -> None:
    manager()

    with pytest.raises(GraphLockedError, match="locked"):
        manager.reflect(source)


class _AsyncSource:
    def __init__(self, descriptors: list[SourceDescriptor]) -> None:
        self._descriptors = descriptors

    async def accept(self, visitor) -> None:
        for descriptor in self._descriptors:
            visitor.visit(descriptor)


def test_areflect_async_source(manager: type[Manager]) -> None:
    source = _AsyncSource([ModelDescriptor(UserV1, "test", {})])
    report = asyncio.run(manager.areflect(source))

    assert report.registered_models == 1
    assert [str(version) for version in manager._default_engine.registry.versions] == [
        "User@1.0.0"
    ]


def _patch(*ops: dict) -> JsonPatch:
    return JsonPatch(list(ops))


def _callable_migration(data: dict, context=None) -> dict:
    data["added"] = 1
    data["nested"]["field"] = 2
    del data["removed"]
    return {**data, "returned": 3}


@pytest.mark.parametrize(
    "discovery, migration, added, removed, modified",
    [
        pytest.param(
            JsonPatchDiffDiscovery(),
            _patch(
                {"op": "add", "path": "/added", "value": 1},
                {"op": "remove", "path": "/removed"},
                {"op": "replace", "path": "/changed", "value": 2},
                {"op": "move", "from": "/old", "path": "/new"},
                {"op": "copy", "from": "/source", "path": "/copy"},
                {"op": "add", "path": "/nested/field", "value": 3},
                {"op": "add", "path": "", "value": 4},
            ),
            {"added", "new", "copy", "nested"},
            {"removed", "old", "source"},
            {"changed"},
            id="json-patch",
        ),
        pytest.param(
            CallableDiffDiscovery(),
            _callable_migration,
            {"added", "returned"},
            {"removed"},
            {"nested"},
            id="callable",
        ),
    ],
)
def test_diff_discovery(discovery, migration, added, removed, modified) -> None:
    adapter = PydanticModelAdapter(codec=ModelCodec())
    diff = discovery.discover(
        migration,
        adapter.versionable(UserV1),
        adapter.versionable(UserV2),
    )

    assert diff.origin == "migration"
    assert set(diff.added_fields) == added
    assert set(diff.removed_fields) == removed
    assert set(diff.modified_fields) == modified
