"""Tests for the JSON Schema model adapter."""

from __future__ import annotations

import semver
from pydantic import BaseModel

from pyverge.core import (
    MigrationSettings,
    VersionNode,
)
from pyverge.migration import (
    Diff,
    JsonSchemaModelAdapter,
    Registry,
    latest_target_resolver,
)
from tests.utils import make_engine


def _schema(version: str, props: dict, required: list[str] | None = None) -> dict:
    return {
        "kind": "User",
        "version": version,
        "type": "object",
        "properties": {
            "kind": {"type": "string", "default": "User"},
            "version": {"type": "string", "default": version},
            **props,
        },
        "required": required or [],
    }


class TestJsonSchemaModelAdapter:
    def test_version_and_kind(self) -> None:
        adapter = JsonSchemaModelAdapter()
        schema = _schema("1.0.0", {"name": {"type": "string"}})
        model = adapter.to_pydantic(schema)
        assert adapter.version(model) == "1.0.0"
        assert adapter.kind(model) == "User"

    def test_versionable(self) -> None:
        adapter = JsonSchemaModelAdapter()
        schema = _schema("1.0.0", {"name": {"type": "string"}})
        model = adapter.to_pydantic(schema)
        versionable = adapter.versionable(model)
        assert versionable.model is model
        assert str(versionable.version[1]) == "1.0.0"

    def test_validate_valid_payload(self) -> None:
        adapter = JsonSchemaModelAdapter()
        schema = _schema("1.0.0", {"name": {"type": "string"}}, required=["name"])
        model = adapter.to_pydantic(schema)
        result = adapter.validate({"name": "Alice"}, model)
        assert result["name"] == "Alice"

    def test_validate_invalid_payload_raises(self) -> None:
        adapter = JsonSchemaModelAdapter()
        schema = _schema("1.0.0", {"name": {"type": "string"}}, required=["name"])
        model = adapter.to_pydantic(schema)
        try:
            adapter.validate({}, model)
        except Exception as exc:
            assert "name" in str(exc)
        else:
            raise AssertionError("expected validation error")

    def test_finalize_applies_defaults(self) -> None:
        adapter = JsonSchemaModelAdapter()
        schema = _schema(
            "1.0.0",
            {"name": {"type": "string"}, "age": {"type": "integer", "default": 0}},
        )
        model = adapter.to_pydantic(schema)
        result = adapter.finalize(model, {"name": "Alice"})
        assert result["name"] == "Alice"
        assert result["age"] == 0

    def test_meta_endpoint_empty_diff(self) -> None:
        adapter = JsonSchemaModelAdapter()
        meta_node = VersionNode[semver.Version, BaseModel](
            _model=None, _value=semver.Version(0, 1, 0), _kind="User"
        )
        real = adapter.versionable(
            adapter.to_pydantic(_schema("1.0.0", {"name": {"type": "string"}}))
        )
        diff = adapter.diff(meta_node, real)
        assert isinstance(diff, Diff)
        assert not diff.has_additions
        assert not diff.has_removals
        assert not diff.has_modifications


class TestJsonSchemaDiff:
    def test_detects_added_and_removed(self) -> None:
        adapter = JsonSchemaModelAdapter()
        source = adapter.versionable(
            adapter.to_pydantic(_schema("1.0.0", {"name": {"type": "string"}}))
        )
        target = adapter.versionable(
            adapter.to_pydantic(
                _schema(
                    "2.0.0",
                    {"name": {"type": "string"}, "age": {"type": "integer"}},
                )
            )
        )
        diff = adapter.diff(source, target)
        assert "age" in diff.added_fields
        assert diff.has_additions

    def test_detects_modified_type(self) -> None:
        adapter = JsonSchemaModelAdapter()
        source = adapter.versionable(
            adapter.to_pydantic(_schema("1.0.0", {"age": {"type": "string"}}))
        )
        target = adapter.versionable(
            adapter.to_pydantic(_schema("2.0.0", {"age": {"type": "integer"}}))
        )
        diff = adapter.diff(source, target)
        assert diff.has_modifications
        assert "type_changed" in diff.modified_fields["age"]

    def test_cross_kind_raises(self) -> None:
        adapter = JsonSchemaModelAdapter()
        source = adapter.versionable(adapter.to_pydantic(_schema("1.0.0", {})))
        target = adapter.versionable(
            adapter.to_pydantic(
                {
                    "kind": "Other",
                    "version": "2.0.0",
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "default": "Other"},
                        "version": {"type": "string", "default": "2.0.0"},
                    },
                }
            )
        )
        try:
            adapter.diff(source, target)
        except ValueError:
            pass
        else:
            raise AssertionError("expected cross-kind error")


class TestJsonSchemaEngineIntegration:
    def test_register_and_migrate(self) -> None:
        adapter = JsonSchemaModelAdapter()
        registry = Registry[semver.Version, BaseModel]()
        eng = make_engine(registry, MigrationSettings(), adapter=adapter)

        v1 = adapter.versionable(
            adapter.to_pydantic(_schema("1.0.0", {"name": {"type": "string"}}))
        )
        v2 = adapter.versionable(
            adapter.to_pydantic(
                _schema(
                    "2.0.0",
                    {
                        "name": {"type": "string"},
                        "age": {"type": "integer", "default": 0},
                    },
                )
            )
        )
        eng.store_model(v1)
        eng.store_model(v2)
        eng.store_migration((v1, v2), lambda d: {**d, "version": "2.0.0"})

        result = eng.migrate(
            {"kind": "User", "version": "1.0.0", "name": "Alice"},
            target=latest_target_resolver(registry),
        )
        assert result["version"] == "2.0.0"
        assert result["age"] == 0
