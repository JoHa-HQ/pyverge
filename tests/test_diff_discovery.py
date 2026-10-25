"""Diff discovery from JSON Patch and callable migrations."""

from __future__ import annotations

from typing import Any, cast

from pyverge.discovery.reflection import (
    CallableDiffDiscovery,
    JsonPatchDiffDiscovery,
)
from pyverge.migrations.json_patch import JsonPatch
from pyverge.providers import PydanticModelAdapter
from tests.examples.pydantic.semver import UserV1, UserV2


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
