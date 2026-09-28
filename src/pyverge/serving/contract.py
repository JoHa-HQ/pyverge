"""Contract checks — validate a reflected schema against the registered graph.

A host reflects a primitive's schema and wants to register it as the anchor of a
version graph. Two invariants must hold:

* the registered contract for ``(kind, version)`` must be complete — a nested
  versioned kind the schema uses but the manager does not own is a
  misconfiguration (no implicit registration, ever);
* the reflected schema must agree with the registered contract (same field
  surface, minus the identity fields).

Both are pure checks over a manager and a schema document; the host supplies the
reflected document and the adapter reads models.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from pyverge.manager import Manager

from .reflection import IDENTITY

if TYPE_CHECKING:
    from .reflection import SchemaReflection


def nested_kinds(schema: dict[str, Any]) -> list[str]:
    """Return the versioned kinds embedded in *schema*'s object properties.

    A nested object carrying ``kind``/``version`` default properties is a
    versioned model used by the schema — its kind is collected for the
    registered-tree check.
    """
    kinds: list[str] = []
    for name, doc in schema.get("properties", {}).items():
        if name in IDENTITY or doc.get("type") != "object":
            continue
        nested = doc.get("properties", {})
        nested_kind = nested.get("kind", {}).get("default")
        nested_version = nested.get("version", {}).get("default")
        if nested_kind and nested_version:
            kinds.append(nested_kind)
        kinds.extend(nested_kinds(doc))
    return kinds


def nested_models(adapter, model: type[BaseModel], _seen: set[int] | None = None):
    """Yield every model class embedded in *model*'s field annotations."""
    if _seen is None:
        _seen = set()
    if id(model) in _seen:
        return
    _seen.add(id(model))
    for name in model.model_fields:
        nested = adapter.field_model(model, name)
        if nested is None or nested is model or id(nested) in _seen:
            continue
        yield nested
        yield from nested_models(adapter, nested, _seen)


def check_owned(manager: Manager, owns, kind: str, version: str) -> None:
    """Fail when a registered model uses a nested versioned kind unregistered."""
    versionable = manager.get(kind, version)
    if versionable.model is None:
        return
    adapter = manager.engine.adapter
    for nested in nested_models(adapter, versionable.model):
        nested_kind = adapter.kind(nested)
        if not nested_kind or owns(nested_kind):
            continue
        raise ValueError(
            f"tool {kind!r}@{version} uses nested model {nested.__name__!r} "
            f"(kind {nested_kind!r}) but that kind is not registered in the "
            "manager; there is no implicit registration"
        )


def check_signature_owned(owns, kind: str, version: str, schema: dict) -> None:
    """Fail when a reflected schema uses a nested versioned kind unregistered."""
    for nested_kind in nested_kinds(schema):
        if nested_kind in IDENTITY or owns(nested_kind):
            continue
        raise ValueError(
            f"tool {kind!r}@{version} signature uses nested model "
            f"(kind {nested_kind!r}) but that kind is not registered in the "
            "manager; lowest sub-trees must be registered already"
        )


def check_agreement(
    registered: set[str] | None, kind: str, version: str, reflected: set[str]
) -> None:
    """Fail when a reflected field surface drifts from the registered contract."""
    if registered is None or registered == reflected:
        return
    raise ValueError(
        f"tool {kind!r}@{version} signature reflects fields "
        f"{sorted(reflected)} but its registered model declares "
        f"{sorted(registered)}; register a matching model or align the signature"
    )


class ServingContract:
    """The registered-graph checks a host runs before serving a reflected schema.

    Binds the manager and the "owns a kind" predicate so a host can call the
    three checks without threading them through.
    """

    def __init__(self, manager: Manager, owns) -> None:
        self._manager = manager
        self._owns = owns

    def check_registered(self, kind: str, version: str) -> None:
        """Fail when a registered model uses a nested versioned kind unregistered."""
        check_owned(self._manager, self._owns, kind, version)

    def check_signature(self, kind: str, version: str, schema: dict) -> None:
        """Fail when a reflected schema uses a nested versioned kind unregistered."""
        check_signature_owned(self._owns, kind, version, schema)

    def check_agreement(
        self, kind: str, version: str, reflection: SchemaReflection
    ) -> None:
        """Fail when a reflected schema drifts from the registered contract.

        The reflected schema is materialized through the same adapter; a typed
        adapter that refuses raw schemas yields no model, so the check is
        skipped and the registered-tree walk already covers it.
        """
        field_model = self._manager.get(kind, version).model
        if field_model is None:
            return
        try:
            reflected_model = reflection.versionable().model
        except (AttributeError, TypeError, ValueError):
            return
        if reflected_model is None:
            return
        registered = {n for n in field_model.model_fields if n not in IDENTITY}
        reflected = {n for n in reflected_model.model_fields if n not in IDENTITY}
        check_agreement(registered, kind, version, reflected)


__all__ = [
    "ServingContract",
    "check_agreement",
    "check_owned",
    "check_signature_owned",
    "nested_kinds",
    "nested_models",
]
