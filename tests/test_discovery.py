"""Build discovery and manager source reflection."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from pyverge import Manager
from pyverge.discovery import (
    MigrationDescriptor,
    MigrationSpec,
    ModelDescriptor,
    RegistrationContext,
    SourceDescriptor,
)
from pyverge.discovery.reflection import (
    CallableDiffDiscovery,
    JsonPatchDiffDiscovery,
)
from pyverge.manager.types import Reflectable
from pyverge.migrations.json_patch import JsonPatch
from pyverge.providers import PydanticModelAdapter
from pyverge.registry.errors import GraphLockedError
from pyverge.versioning import EdgeKey
from tests.examples.pydantic.semver import UserV1, UserV2, migrate_v1_to_v2
from tests.utils.source import StaticSource

_ADAPTER = PydanticModelAdapter()
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


def test_manager_is_reflectable(manager: type[Manager]) -> None:
    assert isinstance(manager, Reflectable)


def test_registration_context_requires_validation_flag() -> None:
    with pytest.raises(TypeError):
        RegistrationContext(source_id="test", logger=None, clock=None)  # ty: ignore[missing-argument, invalid-argument-type]


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


def test_json_patch_discovers_all_top_level_ops() -> None:
    adapter = PydanticModelAdapter()
    source = adapter.versionable(UserV1)
    target = adapter.versionable(UserV2)
    diff = JsonPatchDiffDiscovery().discover(
        _patch(
            {"op": "add", "path": "/added", "value": 1},
            {"op": "remove", "path": "/removed"},
            {"op": "replace", "path": "/changed", "value": 2},
            {"op": "move", "from": "/old", "path": "/new"},
            {"op": "copy", "from": "/source", "path": "/copy"},
            {"op": "add", "path": "/nested/field", "value": 3},
            {"op": "add", "path": "", "value": 4},
        ),
        source,
        target,
    )
    assert diff.origin == "migration"
    assert set(diff.added_fields) == {"added", "new", "copy", "nested"}
    assert set(diff.removed_fields) == {"removed", "old", "source"}
    assert "changed" in diff.modified_fields


def test_callable_discovers_assignments_deletes_and_return_dict() -> None:
    adapter = PydanticModelAdapter()
    source = adapter.versionable(UserV1)
    target = adapter.versionable(UserV2)
    diff = CallableDiffDiscovery().discover(_callable_migration, source, target)
    assert set(diff.added_fields) == {"added", "returned"}
    assert diff.removed_fields == ["removed"]
    assert "nested" in diff.modified_fields


def test_callable_without_source_returns_empty_diff() -> None:
    adapter = PydanticModelAdapter()
    source = adapter.versionable(UserV1)
    target = adapter.versionable(UserV2)
    diff = CallableDiffDiscovery().discover(cast(Any, len), source, target)
    assert diff.fields == {}
    assert diff.origin == "migration"
