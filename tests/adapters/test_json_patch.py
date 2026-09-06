"""Tests for declarative migration ops: RFC 6902 core ops + extended ops."""

from __future__ import annotations

import jsonpatch
import pytest

from pyverge.migration import JsonPatchMigration


def _migrate(ops: list[dict], data: dict) -> dict:
    return JsonPatchMigration({"from": "0.1.0", "to": "0.2.0", "ops": ops})(data)


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
