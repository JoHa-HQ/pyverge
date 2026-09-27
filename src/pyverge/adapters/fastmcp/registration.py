"""Registrar — materialize anchors, validate trees, precompute virtual tools.

The registrar owns the *write* phases of the FastMCP lifecycle over the shared
``_physical`` / ``_paths`` bookkeeping:

* ``register`` — materialize every physical versioned tool's signature as its
  anchor model,
* ``reconcile`` — validate that the reflected signature tree attached onto the
  registered tree (no implicit registration of nested models),
* ``enrich`` — precompute convergence paths and materialize virtual tools for
  the versions that have no physical declaration.

It depends only on the :class:`ToolManagerRouter` (manager routing + policy)
and the shared index dicts; it never talks to the server outside the phases.
Call-time routing (delegates, payload convergence) lives in the sibling
:class:`~pyverge.adapters.fastmcp.routing.Converger`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from pyverge.manager import Manager

from .reflection import ToolReflection
from .router import ToolManagerRouter

_SCHEMA_HIDDEN = {"kind", "version"}


class Registrar:
    """Materialize, validate and enrich the versioned tool surface."""

    def __init__(
        self,
        router: ToolManagerRouter,
        *,
        physical: dict,
        paths: dict,
        converger,
    ) -> None:
        self._router = router
        self._physical = physical
        self._paths = paths
        self._converger = converger

    # -- phase: register ----------------------------------------------------

    async def register(self, server) -> None:
        """Materialize every physical versioned tool's signature as an anchor.

        A physical tool *is* its own model: its signature is reflected into
        the registered anchor via the model adapter, so there is no separate
        raw registration for physical tools.  Nested model parameters must
        already be registered — only the tool's own signature is materialized
        here, never its nested sub-trees (that is checked in ``reconcile``).

        Re-running is idempotent: an already-registered ``(kind, version)``
        is left untouched.  A version whose signature cannot materialize into
        a model (e.g. a typed adapter with no registered class) still raises.
        """
        for (kind, version), tool in self._physical.items():
            manager = self._manager_for(kind)
            if self._has_version(manager, kind, version):
                continue
            assert manager is not None, f"no manager owns kind {kind!r}"
            adapter = manager.engine.adapter
            anchor = self._reflected_versionable(ToolReflection(tool, adapter))
            if anchor is None:
                raise ValueError(
                    f"tool {kind!r}@{version} is versioned but no model for "
                    "that version is registered and its signature cannot "
                    "materialize one either"
                )
            manager.engine.store_model(anchor)

    def _manager_for(self, kind: str) -> Manager | None:
        return self._router.manager_for(kind)

    @staticmethod
    def _has_version(manager: Manager | None, kind: str, version: str) -> bool:
        if manager is None:
            return False
        for versionable in manager.list_versions(kind):
            if str(versionable.version[1]) == version:
                return True
        return False

    # -- phase: reconcile ---------------------------------------------------

    async def reconcile(self, server) -> None:
        """Merge the reflected signature tree onto the registered tree.

        Every versioned tool's signature reflects into a model tree (its
        ``weather.json``).  That reflection must attach onto the tree already
        registered in the managers:

        * the registered contract for ``(kind, version)`` must be complete —
          every lowest sub-tree it uses must be registered (there is no
          implicit registration, ever),
        * the reflected signature tree must agree with the registered contract
          (same field surface, minus the identity fields).

        Nothing is written here: the reflected model is transient and never
        registered into any manager.
        """
        for (kind, version), tool in self._physical.items():
            manager = self._manager_for(kind)
            assert manager is not None, f"no manager owns kind {kind!r}"
            adapter = manager.engine.adapter
            self._check_registered_tree_owned(manager, kind, version)
            reflected = ToolReflection(tool, adapter)
            self._check_reflected_signature(adapter, kind, version, reflected)
            self._check_schema_agreement(adapter, kind, version, reflected)

    def _reflected_versionable(self, reflected: ToolReflection):
        """Return the reflected signature's versionable, or ``None`` if unusable.

        Reflection wraps the tool's compliant JSON Schema through the adapter.
        A schema-based adapter (``versionable(dict)``) materializes a transient
        leaf-free model tree for inspection.  A typed adapter refuses raw
        schemas — there the tool's signature is the registered model itself, so
        the reflected checks are already covered by the registered-tree walk.
        """
        try:
            return reflected.versionable()
        except (AttributeError, TypeError, ValueError):
            return None

    def _check_registered_tree_owned(
        self, manager: Manager, kind: str, version: str
    ) -> None:
        """Fail when a registered model *uses* a nested versioned model unregistered.

        The registered contract for ``(kind, version)`` may embed another
        versioned model in its field annotations (the nested-arguments case).
        Every such nested model must be registered in some manager — there is no
        implicit registration or movement.  Plain (unversioned) nested models
        are untouched.
        """
        versionable = manager.get(kind, version)
        if versionable.model is None:
            return
        adapter = manager.engine.adapter
        for nested in self._nested_models(adapter, versionable.model):
            nested_kind = adapter.kind(nested)
            if not nested_kind:
                continue
            if self._router.manager_for(nested_kind) is None:
                raise ValueError(
                    f"tool {kind!r}@{version} uses nested model "
                    f"{nested.__name__!r} (kind {nested_kind!r}) but that kind "
                    "is not registered in any manager; there is no implicit "
                    "registration"
                )

    def _check_reflected_signature(
        self, adapter, kind: str, version: str, reflected: ToolReflection
    ) -> None:
        """Fail when the tool's signature uses a nested model that is unregistered.

        A tool whose parameter is typed by a versioned model (not a bare
        ``dict``) reflects that model into its signature tree.  Just like the
        registered contract, the lowest sub-trees of the reflected signature
        must already be registered.  (bare ``dict`` parameters reflect no
        nested model, so they add no constraint.)
        """
        if reflected.version is None:
            return
        for nested_kind in self._signature_nested_kinds(reflected.schema()):
            if nested_kind in _SCHEMA_HIDDEN:
                continue
            if self._router.manager_for(nested_kind) is None:
                raise ValueError(
                    f"tool {kind!r}@{version} signature uses nested model "
                    f"(kind {nested_kind!r}) but that kind is not registered "
                    "in any manager; lowest sub-trees must be registered already"
                )

    @staticmethod
    def _signature_nested_kinds(document: dict[str, Any]) -> list[str]:
        """Return the identity kinds embedded in *document*'s object properties.

        FastMCP flattens a model-typed parameter into a nested JSON-Schema
        object.  A nested object that carries ``kind``/``version`` default
        properties is a versioned model used by the signature — its kind is
        collected for the registered-tree merge check.
        """
        kinds: list[str] = []
        for name, doc in document.get("properties", {}).items():
            if name in _SCHEMA_HIDDEN or doc.get("type") != "object":
                continue
            nested = doc.get("properties", {})
            nested_kind = nested.get("kind", {}).get("default")
            nested_version = nested.get("version", {}).get("default")
            if nested_kind and nested_version:
                kinds.append(nested_kind)
            kinds.extend(Registrar._signature_nested_kinds(doc))
        return kinds

    def _check_schema_agreement(
        self, adapter, kind: str, version: str, reflected: ToolReflection
    ) -> None:
        """Fail when the reflected signature drifts from the registered contract.

        The tool's signature must reflect the model the customer registered for
        ``(kind, version)``: same field names and types, minus the identity
        fields (``kind``/``version``).  A drift means the signature no longer
        matches the contract it serves — that is a misconfiguration.
        """
        manager = self._manager_for(kind)
        assert manager is not None, f"no manager owns kind {kind!r}"
        versionable = manager.get(kind, version)
        if versionable.model is None:
            return
        registered = self._schema_card(versionable.model)
        reflected_versionable = self._reflected_versionable(reflected)
        if reflected_versionable is None or reflected_versionable.model is None:
            return
        reflected_card = self._schema_card(reflected_versionable.model)
        if registered != reflected_card:
            raise ValueError(
                f"tool {kind!r}@{version} signature reflects fields "
                f"{sorted(reflected_card)} but its registered model declares "
                f"{sorted(registered)}; register a matching model or align "
                "the signature"
            )

    @staticmethod
    def _schema_card(model: type[BaseModel]) -> set[str]:
        """Return the field-name surface of *model* sans identity fields."""
        return {name for name in model.model_fields if name not in _SCHEMA_HIDDEN}

    @staticmethod
    def _nested_models(adapter, model: type[BaseModel], _seen: set[int] | None = None):
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
            yield from Registrar._nested_models(adapter, nested, _seen)

    # -- phase: enrich ------------------------------------------------------

    async def enrich(self, server) -> None:
        """Precompute convergence paths and materialize virtual tools.

        Every registered version of a policy-marked kind gets a precomputed
        path to its policy target.  Versions with **no** physical declaration
        get a virtual tool: calling its schema converges the arguments to the
        target and dispatches to the target's physical handler.  A kind with
        no recorded policy is skipped entirely (stays plain).
        """
        for kind, versions in self._versions_by_kind().items():
            policy = self._router.policy_for(kind)
            if policy is None:
                continue
            target = self._resolve_target(kind, policy)
            for version in versions:
                self._paths[(kind, version)] = target
                if (kind, version) in self._physical:
                    continue
                self._register_virtual(server, kind, version, target)

    def _versions_by_kind(self) -> dict[str, list[str]]:
        kinds: dict[str, list[str]] = {}
        for kind, version in self._physical:
            kinds.setdefault(kind, []).append(version)
        for manager in self._router.managers():
            for versionable in manager.list_versions():
                kind = str(versionable.version[0])
                version = str(versionable.version[1])
                owner = self._router.manager_for(kind)
                if owner is manager:
                    kinds.setdefault(kind, [])
                    if version not in kinds[kind]:
                        kinds[kind].append(version)
        return kinds

    def _register_virtual(
        self,
        server,
        kind: str,
        version: str,
        target: str,
    ) -> None:
        """Register a virtual tool for *version* exposing the version's schema."""
        from fastmcp.tools.function_tool import FunctionTool  # noqa: PLC0415

        schema = self._schema_for_version(kind, version)
        schema["properties"] = {
            k: v
            for k, v in schema.get("properties", {}).items()
            if k not in _SCHEMA_HIDDEN
        }
        virtual = FunctionTool(
            name=kind,
            version=version,
            parameters=schema,
            fn=self._converger.make_indirection(kind, version, target),
        )
        server.add_tool(virtual)

    def _schema_for_version(self, kind: str, version: str) -> dict:
        """Return the full JSON Schema for a version.

        A concrete version returns its model's schema.  A meta version (no
        concrete model) is reconstructed implicitly by the engine on migration
        registration (``on_missing="reconstruct_model"``), so the model is
        already materialized here.  The LLM sees the full schema it would have
        called against at that version.
        """
        manager = self._manager_for(kind)
        assert manager is not None, f"no manager owns kind {kind!r}"
        versionable: Any = manager.get(kind, version)
        return versionable.model.model_json_schema()

    def _resolve_target(self, kind: str, policy: str) -> str:
        manager = self._manager_for(kind)
        assert manager is not None, f"no manager owns kind {kind!r}"
        versions = sorted(manager.list_versions(kind), key=lambda v: v.version[1])
        if not versions:
            raise ValueError(f"no registered versions for kind {kind!r}")
        if policy == "latest":
            return str(versions[-1].version[1])
        if policy == "earliest":
            return str(versions[0].version[1])
        return policy
