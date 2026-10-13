"""Migration-format tests: RFC 6902 ops, diff adapters, and adapter primitives."""

from __future__ import annotations

import jsonpatch
import pendulum
import pytest
import semver

from pyverge import types
from pyverge.core import (
    VersioningSettings,
    VersionNode,
)
from pyverge.migration import (
    Diff,
    JsonPatchMigration,
    JsonSchemaModelAdapter,
    PydanticDiff,
    PydanticModelAdapter,
    Registry,
)
from pyverge.providers.types import (
    ModelHandle,
)
from tests.examples.pydantic.chrono import (
    UserV20250310,
    UserV20251231,
)
from tests.examples.pydantic.semver import (
    UserV1,
    UserV2,
    UserV3,
    UserV123,
)
from tests.utils import envelope_model, meta_versionable


def _migrate(ops: list[dict], data: dict) -> dict:
    return JsonPatchMigration({"from": "0.1.0", "to": "0.2.0", "ops": ops}).patch(data)


class TestCoreOps:
    def test_add_inserts_new_member(self) -> None:
        result = _migrate([{"op": "add", "path": "/tags", "value": []}], {})
        assert result == {"tags": []}

    def test_add_replaces_existing_member(self) -> None:
        result = _migrate(
            [{"op": "add", "path": "/name", "value": "Bob"}], {"name": "Alice"}
        )
        assert result == {"name": "Bob"}

    def test_add_appends_to_array_with_dash(self) -> None:
        result = _migrate(
            [{"op": "add", "path": "/items/-", "value": 3}], {"items": [1, 2]}
        )
        assert result == {"items": [1, 2, 3]}

    def test_remove_deletes_member(self) -> None:
        result = _migrate([{"op": "remove", "path": "/age"}], {"name": "A", "age": 3})
        assert result == {"name": "A"}

    def test_remove_missing_member_raises(self) -> None:
        with pytest.raises(jsonpatch.JsonPatchException):
            _migrate([{"op": "remove", "path": "/nope"}], {})

    def test_replace_overwrites_value(self) -> None:
        result = _migrate([{"op": "replace", "path": "/age", "value": 4}], {"age": 3})
        assert result == {"age": 4}

    def test_move_relocates_value(self) -> None:
        result = _migrate(
            [{"op": "move", "from": "/old", "to": "/new"}], {"old": "x", "keep": 1}
        )
        assert result == {"new": "x", "keep": 1}

    def test_copy_duplicates_value(self) -> None:
        result = _migrate([{"op": "copy", "from": "/a", "to": "/b"}], {"a": [1, 2]})
        assert result == {"a": [1, 2], "b": [1, 2]}

    def test_test_passes_on_equal_value(self) -> None:
        result = _migrate(
            [{"op": "test", "path": "/type", "value": "X"}], {"type": "X"}
        )
        assert result == {"type": "X"}

    def test_test_fails_on_unequal_value(self) -> None:
        with pytest.raises(jsonpatch.JsonPatchException):
            _migrate([{"op": "test", "path": "/type", "value": "X"}], {"type": "Y"})


class TestPointer:
    def test_escaped_key_resolves(self) -> None:
        result = _migrate([{"op": "add", "path": "/a~1b", "value": 1}], {})
        assert result == {"a/b": 1}

    def test_tilde_escape_resolves(self) -> None:
        result = _migrate([{"op": "add", "path": "/a~0b", "value": 1}], {})
        assert result == {"a~b": 1}

    def test_nested_path_resolves(self) -> None:
        result = _migrate(
            [{"op": "add", "path": "/a/b/c", "value": 1}], {"a": {"b": {}}}
        )
        assert result == {"a": {"b": {"c": 1}}}

    def test_array_index_path_resolves(self) -> None:
        result = _migrate(
            [{"op": "replace", "path": "/items/1", "value": 9}], {"items": [1, 2, 3]}
        )
        assert result == {"items": [1, 9, 3]}


class TestExtendedOps:
    def test_set_default_on_absent_path(self) -> None:
        result = _migrate([{"op": "set_default", "path": "/tags", "value": []}], {})
        assert result == {"tags": []}

    def test_set_default_leaves_existing_value(self) -> None:
        result = _migrate(
            [{"op": "set_default", "path": "/tags", "value": []}], {"tags": ["x"]}
        )
        assert result == {"tags": ["x"]}

    def test_coerce_numeric_string_to_integer(self) -> None:
        result = _migrate(
            [{"op": "coerce", "path": "/age", "type": "integer"}], {"age": "42"}
        )
        assert result == {"age": 42}

    def test_coerce_string_to_boolean(self) -> None:
        result = _migrate(
            [{"op": "coerce", "path": "/active", "type": "boolean"}], {"active": "true"}
        )
        assert result == {"active": True}

    def test_coerce_fails_on_unconvertible_value(self) -> None:
        with pytest.raises(jsonpatch.JsonPatchException):
            _migrate(
                [{"op": "coerce", "path": "/age", "type": "integer"}], {"age": "abc"}
            )

    def test_map_mapped_value_replaced(self) -> None:
        result = _migrate(
            [{"op": "map", "path": "/status", "mapping": {"applied": 3}}],
            {"status": "applied"},
        )
        assert result == {"status": 3}

    def test_map_unmapped_value_uses_default(self) -> None:
        result = _migrate(
            [{"op": "map", "path": "/status", "mapping": {"applied": 3}, "default": 0}],
            {"status": "other"},
        )
        assert result == {"status": 0}

    def test_map_unmapped_without_default_raises(self) -> None:
        with pytest.raises(jsonpatch.JsonPatchException):
            _migrate(
                [{"op": "map", "path": "/status", "mapping": {"applied": 3}}],
                {"status": "other"},
            )

    def test_split_into_fields(self) -> None:
        result = _migrate(
            [
                {
                    "op": "split",
                    "path": "/name",
                    "sep": " ",
                    "fields": ["/first", "/last"],
                }
            ],
            {"name": "John Doe"},
        )
        assert result == {"name": "John Doe", "first": "John", "last": "Doe"}

    def test_split_missing_parts_become_null(self) -> None:
        result = _migrate(
            [
                {
                    "op": "split",
                    "path": "/name",
                    "sep": " ",
                    "fields": ["/first", "/last"],
                }
            ],
            {"name": "John"},
        )
        assert result == {"name": "John", "first": "John", "last": None}


class TestCompiler:
    def test_ops_apply_in_order(self) -> None:
        result = _migrate(
            [
                {"op": "add", "path": "/a", "value": 1},
                {"op": "replace", "path": "/a", "value": 2},
            ],
            {},
        )
        assert result == {"a": 2}

    def test_input_payload_not_mutated(self) -> None:
        data = {"name": "Alice"}
        result = _migrate([{"op": "add", "path": "/age", "value": 3}], data)
        assert data == {"name": "Alice"}
        assert result == {"name": "Alice", "age": 3}

    def test_extended_op_does_not_mutate_input(self) -> None:
        data = {"name": "Alice"}
        result = _migrate([{"op": "set_default", "path": "/age", "value": 3}], data)
        assert data == {"name": "Alice"}
        assert result == {"name": "Alice", "age": 3}

    def test_rejects_missing_from(self) -> None:
        with pytest.raises(ValueError):
            JsonPatchMigration({"to": "0.2.0", "ops": []})

    def test_rejects_missing_ops(self) -> None:
        with pytest.raises(ValueError):
            JsonPatchMigration({"from": "0.1.0", "to": "0.2.0"})

    def test_rejects_unknown_op(self) -> None:
        with pytest.raises(jsonpatch.InvalidJsonPatch):
            JsonPatchMigration(
                {"from": "0.1.0", "to": "0.2.0", "ops": [{"op": "nope", "path": "/a"}]}
            )


class TestPydanticDiff:
    """Tests for ``PydanticDiff`` — construction, predicates, rendering."""

    @pytest.mark.parametrize(
        "source_model, target_model",
        [
            (UserV1, UserV123),
            (UserV20250310, UserV20251231),
        ],
        ids=["semver", "date"],
    )
    def test_from_pair_detects_added_field(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        source_model: ModelHandle,
        target_model: ModelHandle,
    ) -> None:
        """from_pair detects a field present in target but not source."""
        source = envelope_model(model_adapter, versioning_settings, source_model)
        target = envelope_model(model_adapter, versioning_settings, target_model)

        diff = PydanticDiff.from_pair(source=source, target=target)
        assert diff.has_additions
        assert "last_name" in diff.added_fields

    @pytest.mark.parametrize(
        "source_model, target_model",
        [
            (UserV123, UserV1),
            (UserV20251231, UserV20250310),
        ],
        ids=["semver", "date"],
    )
    def test_from_pair_detects_removed_field(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        source_model: ModelHandle,
        target_model: ModelHandle,
    ) -> None:
        """from_pair detects a field present in source but not target."""
        source = envelope_model(model_adapter, versioning_settings, source_model)
        target = envelope_model(model_adapter, versioning_settings, target_model)

        diff = PydanticDiff.from_pair(source=source, target=target)
        assert diff.has_removals
        assert "last_name" in diff.removed_fields

    def test_is_identity_for_same_model(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        """from_pair returns identity diff when models are identical."""
        version = envelope_model(model_adapter, versioning_settings, UserV1)

        diff = PydanticDiff.from_pair(source=version, target=version)
        assert diff.is_identity
        assert not diff.has_additions
        assert not diff.has_removals
        assert not diff.has_modifications

    def test_added_default(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        """added_default returns the default for a newly added field."""
        source = envelope_model(model_adapter, versioning_settings, UserV1)
        target = envelope_model(model_adapter, versioning_settings, UserV2)

        diff = PydanticDiff.from_pair(source=source, target=target)
        assert diff.added_default("age") is None

    def test_added_required(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        """is_added_required identifies required new fields."""
        source = envelope_model(model_adapter, versioning_settings, UserV1)
        target = envelope_model(model_adapter, versioning_settings, UserV3)

        diff = PydanticDiff.from_pair(source=source, target=target)
        assert "status" in diff.added_fields
        assert diff.added_default("status") == "active"

    def test_render_json_patch(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        """Default renderer produces RFC 6902 JSON Patch."""
        source = envelope_model(model_adapter, versioning_settings, UserV1)
        target = envelope_model(model_adapter, versioning_settings, UserV2)

        diff = PydanticDiff.from_pair(source=source, target=target)
        serialized = diff.render()
        assert isinstance(serialized, list)
        add_ops = [op for op in serialized if op["op"] == "add"]
        assert any(op["path"] == "/age" for op in add_ops)

    def test_source_and_target_on_diff(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        """The diff stores source and target Versionable references."""
        source = envelope_model(model_adapter, versioning_settings, UserV1)
        target = envelope_model(model_adapter, versioning_settings, UserV2)

        diff = PydanticDiff.from_pair(source=source, target=target)
        assert diff.source is source
        assert diff.target is target

    def test_edge_property(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        """edge returns the (source_version, target_version) MigrationKey tuple."""
        source = envelope_model(model_adapter, versioning_settings, UserV1)
        target = envelope_model(model_adapter, versioning_settings, UserV2)

        diff = PydanticDiff.from_pair(source=source, target=target)
        assert diff.edge == (source, target)

    @pytest.mark.parametrize(
        "registry, version",
        [
            [Registry[semver.Version](), "0.1.0"],
            [Registry[pendulum.Date](), "2024-01-01"],
        ],
    )
    def test_meta_endpoint_produces_empty_diff(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        version: str,
    ) -> None:
        """A meta endpoint yields a plain Diff with empty predicates."""
        meta = meta_versionable(model_adapter, "User", version)
        real = envelope_model(model_adapter, versioning_settings, UserV1)

        diff = model_adapter.diff(meta, real)
        assert isinstance(diff, Diff)
        assert not diff.has_additions
        assert not diff.has_removals
        assert not diff.has_modifications


class TestOfIdempotency:
    """``ModelAdapter.of`` is idempotent across the parse boundary."""

    def test_of_parses_semver_string(self, model_adapter: PydanticModelAdapter) -> None:
        """A semver string parses to a ``semver.Version``."""
        assert model_adapter.of("1.0.0") == semver.Version(1, 0, 0)

    def test_of_returns_parsed_semver_unchanged(
        self, model_adapter: PydanticModelAdapter
    ) -> None:
        """An already-parsed ``semver.Version`` is returned as-is."""
        parsed = semver.Version(1, 0, 0)
        assert model_adapter.of(parsed) is parsed

    def test_of_returns_parsed_date_unchanged(
        self, model_adapter: PydanticModelAdapter
    ) -> None:
        """An already-parsed ``pendulum.Date`` is returned as-is."""
        parsed = pendulum.Date(2025, 3, 10)
        assert model_adapter.of(parsed) is parsed


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
        meta_node = VersionNode[semver.Version](
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
