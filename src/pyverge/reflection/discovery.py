"""Migration-format discovery: turn a migration into a :class:`Diff`.

A migration can be authored in different formats — an RFC 6902 JSON Patch
(:class:`~pyverge.adapters.json_patch.JsonPatch`) or a plain Python callable.
Discovery normalizes either format into the same provider-agnostic
:class:`Diff`, so the engine and the model adapters never need to know how a
migration was written.

The discovery strategies are the "migration-format adapters": they are the
only place that understands a migration's internal representation.  The model
adapters consume the resulting :class:`Diff` via ``materialize`` and stay
completely decoupled from the migration format.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Any, Generic, Protocol, runtime_checkable

from pyverge.adapters.json_patch import JsonPatch
from pyverge.core.types import (
    MigrationFunc,
    MigrationFunc_co,
    Versionable,
    VersionValue,
    VSource_co,
    VTarget_co,
)
from pyverge.reflection.diff import Diff


@runtime_checkable
class DiffDiscovery(Protocol[VersionValue, MigrationFunc_co]):
    """Discover the structural change a migration encodes as a :class:`Diff`.

    Implementations are format-specific: one reads a JSON Patch, another
    parses a Python callable's AST.  The engine selects a strategy per
    migration and uses the resulting :class:`Diff` to reconstruct missing
    model versions.
    """

    def discover(
        self,
        migration: MigrationFunc_co,
        source: Versionable[VersionValue, VSource_co],
        target: Versionable[VersionValue, VTarget_co],
    ) -> Diff[VersionValue, VSource_co, VTarget_co]: ...


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
        source: Versionable[VersionValue, VSource_co],
        target: Versionable[VersionValue, VTarget_co],
    ) -> Diff[VersionValue, VSource_co, VTarget_co]:
        added: list[str] = []
        removed: list[str] = []
        modified: dict[str, dict[str, Any]] = {}
        for op in migration.patch:
            path = op.get("path", "")
            field = path.lstrip("/").split("/", 1)[0]
            if not field:
                continue
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
        return Diff(
            source=source,
            target=target,
            added_fields=sorted(added),
            removed_fields=sorted(removed),
            modified_fields=modified,
        )


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
        source: Versionable[VersionValue, VSource_co],
        target: Versionable[VersionValue, VTarget_co],
    ) -> Diff[VersionValue, VSource_co, VTarget_co]:
        try:
            src = inspect.getsource(migration)
        except (OSError, TypeError):
            return Diff(source=source, target=target)
        tree = ast.parse(textwrap.dedent(src))
        added: list[str] = []
        removed: list[str] = []
        modified: dict[str, dict[str, Any]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target_node in node.targets:
                    if isinstance(target_node, ast.Subscript) and isinstance(
                        target_node.value, ast.Name
                    ):
                        if target_node.value.id != "data":
                            continue
                        key = _subscript_key(target_node.slice)
                        if key is None:
                            continue
                        if key not in added:
                            added.append(key)
                    elif isinstance(target_node, ast.Subscript) and isinstance(
                        target_node.value, ast.Subscript
                    ):
                        outer = target_node.value
                        if (
                            isinstance(outer.value, ast.Name)
                            and outer.value.id == "data"
                        ):
                            key = _subscript_key(outer.slice)
                            if key is not None:
                                modified.setdefault(key, {})["nested_changed"] = True
            elif isinstance(node, ast.Delete):
                for target_node in node.targets:
                    if isinstance(target_node, ast.Subscript) and isinstance(
                        target_node.value, ast.Name
                    ):
                        if target_node.value.id != "data":
                            continue
                        key = _subscript_key(target_node.slice)
                        if key is not None and key not in removed:
                            removed.append(key)
            elif isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
                for key in node.value.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        if key.value not in added:
                            added.append(key.value)
        return Diff(
            source=source,
            target=target,
            added_fields=sorted(added),
            removed_fields=sorted(removed),
            modified_fields=modified,
        )


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
        source: Versionable[VersionValue, VSource_co],
        target: Versionable[VersionValue, VTarget_co],
    ) -> Diff[VersionValue, VSource_co, VTarget_co]:
        if isinstance(migration, JsonPatch):
            return self._json_patch.discover(migration, source, target)
        return self._callable.discover(migration, source, target)


def _subscript_key(slice_: ast.expr) -> str | None:
    """Return the string key of a subscript slice, if it is a constant."""
    if isinstance(slice_, ast.Constant) and isinstance(slice_.value, str):
        return slice_.value
    return None
