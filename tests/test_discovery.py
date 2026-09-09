"""Tests for diff discovery: normalizing migrations into diffs."""

from __future__ import annotations

from typing import Literal

import pytest
from pydantic import BaseModel

from pyverge.adapters.json_patch import JsonPatch
from pyverge.migration import PydanticModelAdapter
from pyverge.reflection.discovery import (
    CallableDiffDiscovery,
    CompositeDiffDiscovery,
    JsonPatchDiffDiscovery,
)


class UserV1(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["1.0.0"] = "1.0.0"
    name: str


class UserV2(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["2.0.0"] = "2.0.0"
    name: str
    age: int | None = None


@pytest.fixture
def endpoints(pydantic_model_adapter: PydanticModelAdapter) -> tuple:
    source = pydantic_model_adapter.versionable(UserV1)
    target = pydantic_model_adapter.versionable(UserV2)
    return source, target


def _patch(ops: list[dict]) -> JsonPatch:
    return JsonPatch(ops)


class TestJsonPatchDiffDiscovery:
    def test_add(self, endpoints) -> None:
        source, target = endpoints
        diff = JsonPatchDiffDiscovery().discover(
            _patch([{"op": "add", "path": "/age", "value": None}]), source, target
        )
        assert diff.added_fields == ["age"]
        assert diff.source is source
        assert diff.target is target

    def test_remove(self, endpoints) -> None:
        source, target = endpoints
        diff = JsonPatchDiffDiscovery().discover(
            _patch([{"op": "remove", "path": "/age"}]), source, target
        )
        assert diff.removed_fields == ["age"]

    def test_replace(self, endpoints) -> None:
        source, target = endpoints
        diff = JsonPatchDiffDiscovery().discover(
            _patch([{"op": "replace", "path": "/name", "value": "Bob"}]), source, target
        )
        assert "name" in diff.modified_fields
        assert diff.modified_fields["name"]["value_changed"]["to"] == "Bob"

    def test_move(self, endpoints) -> None:
        source, target = endpoints
        diff = JsonPatchDiffDiscovery().discover(
            _patch([{"op": "move", "from": "/old", "path": "/new"}]), source, target
        )
        assert "old" in diff.removed_fields
        assert "new" in diff.added_fields

    def test_copy(self, endpoints) -> None:
        source, target = endpoints
        diff = JsonPatchDiffDiscovery().discover(
            _patch([{"op": "copy", "from": "/old", "path": "/new"}]), source, target
        )
        assert "old" in diff.removed_fields
        assert "new" in diff.added_fields

    def test_nested_path_maps_to_top_field(self, endpoints) -> None:
        source, target = endpoints
        diff = JsonPatchDiffDiscovery().discover(
            _patch([{"op": "add", "path": "/address/city", "value": "Paris"}]),
            source,
            target,
        )
        assert "address" in diff.added_fields

    def test_empty_path_skipped(self, endpoints) -> None:
        source, target = endpoints
        diff = JsonPatchDiffDiscovery().discover(
            _patch([{"op": "add", "path": "", "value": "x"}]), source, target
        )
        assert diff.added_fields == []


class TestCallableDiffDiscovery:
    def test_dict_unpack(self, endpoints) -> None:
        source, target = endpoints

        def mig(data: dict) -> dict:
            return {**data, "age": None}

        diff = CallableDiffDiscovery().discover(mig, source, target)
        assert "age" in diff.added_fields

    def test_assign_key(self, endpoints) -> None:
        source, target = endpoints

        def mig(data: dict) -> dict:
            data["age"] = None
            return data

        diff = CallableDiffDiscovery().discover(mig, source, target)
        assert "age" in diff.added_fields

    def test_delete_key(self, endpoints) -> None:
        source, target = endpoints

        def mig(data: dict) -> dict:
            del data["age"]
            return data

        diff = CallableDiffDiscovery().discover(mig, source, target)
        assert "age" in diff.removed_fields

    def test_nested_write(self, endpoints) -> None:
        source, target = endpoints

        def mig(data: dict) -> dict:
            data["address"]["city"] = "Paris"
            return data

        diff = CallableDiffDiscovery().discover(mig, source, target)
        assert "address" in diff.modified_fields


class TestCompositeDiffDiscovery:
    def test_dispatches_json_patch(self, endpoints) -> None:
        source, target = endpoints
        diff = CompositeDiffDiscovery().discover(
            _patch([{"op": "add", "path": "/age", "value": None}]), source, target
        )
        assert "age" in diff.added_fields

    def test_dispatches_callable(self, endpoints) -> None:
        source, target = endpoints

        def mig(data: dict) -> dict:
            return {**data, "age": None}

        diff = CompositeDiffDiscovery().discover(mig, source, target)
        assert "age" in diff.added_fields
