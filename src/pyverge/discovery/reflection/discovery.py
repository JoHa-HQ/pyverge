from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Any, Generic

from pyverge.core.types import MigrationFunc, VersionValue
from pyverge.discovery.reflection.types import DiffDiscovery
from pyverge.migrations.json_patch import JsonPatch
from pyverge.versioning import (
    Comparable,
    Diff,
    DiffOrigin,
    FieldChange,
    FieldStatus,
    FrozenMap,
    Versionable,
)


class JsonPatchDiffDiscovery(Generic[VersionValue]):
    """Discover a :class:`Diff` from an RFC 6902 :class:`JsonPatch`.

    Reads the patch operations and maps them onto the diff predicates:

    - ``add``      → ``added_fields``
    - ``remove``   → ``removed_fields``
    - ``replace``  → ``modified_fields``
    - ``move``/``copy`` → ``removed_fields`` (source) + ``added_fields`` (target)

    Only top-level paths (``/field``) are mapped to diff predicates; nested
    paths (``/a/b``) are recorded as modifications of their top-level field.
    """

    def discover(
        self,
        migration: JsonPatch,
        source: Versionable[VersionValue],
        target: Comparable[VersionValue],
    ) -> Diff[VersionValue]:
        added, removed, modified = self._collect(migration)
        return Diff(
            source=source,
            target=target,
            fields=FrozenMap(_fields(added, removed, modified)),
            origin=DiffOrigin.MIGRATION,
        )

    def _collect(
        self, migration: JsonPatch
    ) -> tuple[list[str], list[str], dict[str, dict[str, Any]]]:
        added: list[str] = []
        removed: list[str] = []
        modified: dict[str, dict[str, Any]] = {}
        for op in migration.patch:
            self._record(op, added, removed, modified)
        return added, removed, modified

    @staticmethod
    def _record(
        op: dict[str, Any],
        added: list[str],
        removed: list[str],
        modified: dict[str, dict[str, Any]],
    ) -> None:
        path = op.get("path", "")
        field = path.lstrip("/").split("/", 1)[0]
        if not field:
            return
        kind = op.get("op")
        if kind == "add":
            if field not in added:
                added.append(field)
        elif kind == "remove":
            if field not in removed:
                removed.append(field)
        elif kind == "replace":
            modified.setdefault(field, {})["value_changed"] = {
                "from": None,
                "to": op.get("value"),
            }
        elif kind in ("move", "copy"):
            from_field = op.get("from", "").lstrip("/").split("/", 1)[0]
            if from_field and from_field not in removed:
                removed.append(from_field)
            if field not in added:
                added.append(field)


class CallableDiffDiscovery(Generic[VersionValue]):
    """Discover a :class:`Diff` from a Python callable migration.

    Parses the function's source AST and collects the keys written into the
    payload dict:

    - ``data["field"] = value``  → ``added_fields``
    - ``del data["field"]``      → ``removed_fields``
    - ``{**data, "field": v}``   → ``added_fields``
    - ``data["field"] = ...`` on an existing key is indistinguishable from an
      add at the AST level, so it is reported as an addition; the adapter
      decides whether the field already exists on the anchor.

    Nested writes (``data["a"]["b"]``) are recorded as modifications of their
    top-level field.
    """

    def discover(
        self,
        migration: MigrationFunc,
        source: Versionable[VersionValue],
        target: Comparable[VersionValue],
    ) -> Diff[VersionValue]:
        try:
            src = inspect.getsource(migration)
        except (OSError, TypeError):
            return Diff(
                source=source,
                target=target,
                fields=FrozenMap(),
                origin=DiffOrigin.MIGRATION,
            )
        added, removed, modified = self._collect(ast.parse(textwrap.dedent(src)))
        return Diff(
            source=source,
            target=target,
            fields=FrozenMap(_fields(added, removed, modified)),
            origin=DiffOrigin.MIGRATION,
        )

    def _collect(
        self, tree: ast.AST
    ) -> tuple[list[str], list[str], dict[str, dict[str, Any]]]:
        added: list[str] = []
        removed: list[str] = []
        modified: dict[str, dict[str, Any]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                self._assign(node, added, modified)
            elif isinstance(node, ast.Delete):
                self._delete(node, removed)
            elif isinstance(node, ast.Return):
                self._return(node, added)
        return added, removed, modified

    @staticmethod
    def _assign(
        node: ast.Assign,
        added: list[str],
        modified: dict[str, dict[str, Any]],
    ) -> None:
        for target_node in node.targets:
            if isinstance(target_node, ast.Subscript) and isinstance(
                target_node.value, ast.Name
            ):
                if target_node.value.id != "data":
                    continue
                key = _subscript_key(target_node.slice)
                if key is not None and key not in added:
                    added.append(key)
            elif isinstance(target_node, ast.Subscript) and isinstance(
                target_node.value, ast.Subscript
            ):
                outer = target_node.value
                if isinstance(outer.value, ast.Name) and outer.value.id == "data":
                    key = _subscript_key(outer.slice)
                    if key is not None:
                        modified.setdefault(key, {})["nested_changed"] = True

    @staticmethod
    def _delete(node: ast.Delete, removed: list[str]) -> None:
        for target_node in node.targets:
            if isinstance(target_node, ast.Subscript) and isinstance(
                target_node.value, ast.Name
            ):
                if target_node.value.id != "data":
                    continue
                key = _subscript_key(target_node.slice)
                if key is not None and key not in removed:
                    removed.append(key)

    @staticmethod
    def _return(node: ast.Return, added: list[str]) -> None:
        if not isinstance(node.value, ast.Dict):
            return
        for key in node.value.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                if key.value not in added:
                    added.append(key.value)


class CompositeDiffDiscovery(Generic[VersionValue]):
    """Dispatch to a format-specific strategy based on the migration type.

    A :class:`JsonPatch` is read by :class:`JsonPatchDiffDiscovery`; anything
    else is treated as a Python callable.
    """

    def __init__(
        self,
        json_patch: DiffDiscovery[VersionValue, JsonPatch] | None = None,
        callable_: DiffDiscovery[VersionValue, MigrationFunc] | None = None,
    ) -> None:
        self._json_patch = json_patch or JsonPatchDiffDiscovery()
        self._callable = callable_ or CallableDiffDiscovery()

    def discover(
        self,
        migration: JsonPatch | MigrationFunc,
        source: Versionable[VersionValue],
        target: Comparable[VersionValue],
    ) -> Diff[VersionValue]:
        if isinstance(migration, JsonPatch):
            return self._json_patch.discover(migration, source, target)
        patch = getattr(migration, "patch", None)
        if isinstance(patch, JsonPatch):
            return self._json_patch.discover(patch, source, target)
        return self._callable.discover(migration, source, target)


def _fields(
    added: list[str],
    removed: list[str],
    modified: dict[str, dict[str, Any]],
) -> dict[str, FieldChange]:
    return {
        **{name: FieldChange(FieldStatus.ADDED, {}) for name in sorted(added)},
        **{name: FieldChange(FieldStatus.REMOVED, {}) for name in sorted(removed)},
        **{
            name: FieldChange(FieldStatus.MODIFIED, changes)
            for name, changes in modified.items()
        },
    }


def _subscript_key(slice_: ast.expr) -> str | None:
    if isinstance(slice_, ast.Constant) and isinstance(slice_.value, str):
        return slice_.value
    return None
