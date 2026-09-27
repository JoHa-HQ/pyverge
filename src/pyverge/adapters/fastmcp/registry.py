"""ToolRegistry — the FastMCP reflection lifecycle in one pipeline.

``ToolRegistry`` is the ``lifespan`` hook the customer hands to FastMCP. One
manager per source: it binds exactly one bounded context, so there is no manager
routing — the manager owns the whole version graph.

It owns four ordered phases over the shared ``_physical`` / ``_paths``
bookkeeping:

* ``search`` — find every physical versioned tool (declares ``version=...``, its
  kind is owned by the manager, and a policy is recorded for that kind),
* ``register`` — materialize each physical tool's signature as its anchor model,
* ``reconcile`` — validate that the reflected signature attaches onto the
  registered tree (no implicit registration of nested models),
* ``enrich`` — precompute convergence paths, materialize virtual tools for the
  versions with no physical declaration, and attach the observer ``hooks`` to
  every migration edge.

Call-time routing lives in :class:`~pyverge.adapters.fastmcp.converger.Converger`,
which the registry also exposes (``path`` / ``delegate`` / ``converge_payload``).
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from pyverge.manager import Manager
from pyverge.types import Attachable

from .converger import Converger
from .discovery import ToolDiscovery
from .injection import InjectionDetector, injected_names
from .reflection import ToolReflection

if TYPE_CHECKING:
    from fastmcp import FastMCP

_SCHEMA_HIDDEN = {"kind", "version"}


class ToolRegistry:
    """Server-wide reflection lifecycle: search, register, reconcile, enrich."""

    def __init__(
        self,
        manager: Manager,
        *,
        policies: dict[str, str] | None = None,
        fallback_policy: str | None = None,
        hooks: Sequence[Attachable] = (),
        injection_detector: InjectionDetector | None = None,
    ) -> None:
        self._manager = manager
        self._hooks = tuple(hooks)
        self._is_injected = injection_detector
        self._physical: dict = {}
        self._paths: dict = {}
        self._discovery = ToolDiscovery()
        self._converger = Converger(
            manager,
            policies=policies,
            fallback_policy=fallback_policy,
            physical=self._physical,
            paths=self._paths,
        )

    @asynccontextmanager
    async def __call__(self, server: FastMCP):
        """FastMCP lifespan entry point."""
        await self.search(server)
        await self.register(server)
        await self.reconcile(server)
        await self.enrich(server)
        yield self

    # -- phase: search ------------------------------------------------------

    async def search(self, server: FastMCP) -> None:
        """Find every physical versioned tool.

        A tool is versioned iff it declares ``version=...``, its kind is owned
        by the manager **and** a policy is recorded for that kind. A tool with
        no recorded policy is plain and is left untouched by the adapter.
        """
        for (kind, version), tool in (await self._discovery.search(server)).items():
            if not self._converger.owns(kind):
                continue
            if self._converger.policy_for(kind) is None:
                continue
            self._physical[(kind, version)] = tool

    # -- phase: register ----------------------------------------------------

    async def register(self, server: FastMCP) -> None:
        """Materialize every physical versioned tool's signature as an anchor.

        A physical tool *is* its own model: its signature is reflected into the
        registered anchor via the model adapter, so there is no separate raw
        registration. Injected parameters are excluded — they are wiring, not
        contract. Nested model parameters must already be registered; only the
        tool's own signature is materialized here, never its nested sub-trees
        (that is checked in ``reconcile``).

        Re-running is idempotent: an already-registered ``(kind, version)`` is
        left untouched. A version whose signature cannot materialize into a
        model (e.g. a typed adapter with no registered class) still raises.
        """
        for (kind, version), tool in self._physical.items():
            if self._has_version(kind, version):
                continue
            anchor = self._reflected_versionable(self._reflection(kind, version, tool))
            if anchor is None:
                raise ValueError(
                    f"tool {kind!r}@{version} is versioned but no model for "
                    "that version is registered and its signature cannot "
                    "materialize one either"
                )
            self._manager.engine.store_model(anchor)

    def _has_version(self, kind: str, version: str) -> bool:
        return any(
            str(versionable.version[1]) == version
            for versionable in self._manager.list_versions(kind)
        )

    # -- phase: reconcile ---------------------------------------------------

    async def reconcile(self, server: FastMCP) -> None:
        """Merge the reflected signature tree onto the registered tree.

        Every versioned tool's signature reflects into a model tree. That
        reflection must attach onto the tree already registered in the manager:

        * the registered contract for ``(kind, version)`` must be complete — a
          nested versioned kind the tool uses but the manager does not own is a
          misconfiguration (no implicit registration, ever),
        * the tool's signature must agree with the registered contract (same
          field surface, minus the identity fields).

        Nothing is written here: the reflected model is transient and never
        registered into the manager.
        """
        for (kind, version), tool in self._physical.items():
            reflected = self._reflection(kind, version, tool)
            self._check_registered_tree_owned(kind, version)
            self._check_reflected_signature(kind, version, reflected)
            self._check_schema_agreement(kind, version, reflected)

    def _reflection(self, kind: str, version: str, tool) -> ToolReflection:
        adapter = self._manager.engine.adapter
        return ToolReflection(
            tool,
            adapter,
            injected=self._injected_names(tool),
        )

    def _injected_names(self, tool) -> set[str]:
        func = getattr(tool, "fn", None)
        if func is None:
            return set()
        return injected_names(func, self._is_injected)

    def _reflected_versionable(self, reflected: ToolReflection):
        """Return the reflected signature's versionable, or ``None`` if unusable.

        Reflection wraps the tool's compliant JSON Schema through the adapter. A
        schema-based adapter (``versionable(dict)``) materializes a transient
        leaf-free model tree for inspection. A typed adapter refuses raw schemas
        — there the tool's signature is the registered model itself, so the
        reflected checks are already covered by the registered-tree walk.
        """
        try:
            return reflected.versionable()
        except (AttributeError, TypeError, ValueError):
            return None

    def _check_registered_tree_owned(self, kind: str, version: str) -> None:
        """Fail when a registered model *uses* a nested versioned model unregistered.

        The registered contract for ``(kind, version)`` may embed another
        versioned model in its field annotations (the nested-arguments case).
        Every such nested model must be registered in the manager — there is no
        implicit registration. Plain (unversioned) nested models are untouched.
        """
        versionable = self._manager.get(kind, version)
        if versionable.model is None:
            return
        adapter = self._manager.engine.adapter
        for nested in self._nested_models(adapter, versionable.model):
            nested_kind = adapter.kind(nested)
            if not nested_kind:
                continue
            if not self._converger.owns(nested_kind):
                raise ValueError(
                    f"tool {kind!r}@{version} uses nested model "
                    f"{nested.__name__!r} (kind {nested_kind!r}) but that kind "
                    "is not registered in the manager; there is no implicit "
                    "registration"
                )

    def _check_reflected_signature(
        self, kind: str, version: str, reflected: ToolReflection
    ) -> None:
        """Fail when the tool's signature uses a nested model that is unregistered.

        A tool whose parameter is typed by a versioned model (not a bare
        ``dict``) reflects that model into its signature tree. Just like the
        registered contract, the lowest sub-trees must already be registered.
        (bare ``dict`` parameters reflect no nested model, so they add no
        constraint.)
        """
        if reflected.version is None:
            return
        for nested_kind in self._signature_nested_kinds(reflected.schema()):
            if nested_kind in _SCHEMA_HIDDEN:
                continue
            if not self._converger.owns(nested_kind):
                raise ValueError(
                    f"tool {kind!r}@{version} signature uses nested model "
                    f"(kind {nested_kind!r}) but that kind is not registered "
                    "in the manager; lowest sub-trees must be registered already"
                )

    @staticmethod
    def _signature_nested_kinds(document: dict[str, Any]) -> list[str]:
        """Return the identity kinds embedded in *document*'s object properties.

        FastMCP flattens a model-typed parameter into a nested JSON-Schema
        object. A nested object that carries ``kind``/``version`` default
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
            kinds.extend(ToolRegistry._signature_nested_kinds(doc))
        return kinds

    def _check_schema_agreement(
        self, kind: str, version: str, reflected: ToolReflection
    ) -> None:
        """Fail when the reflected signature drifts from the registered contract.

        The tool's signature must reflect the model the customer registered for
        ``(kind, version)``: same field names and types, minus the identity
        fields (``kind``/``version``). A drift means the signature no longer
        matches the contract it serves — that is a misconfiguration.
        """
        versionable = self._manager.get(kind, version)
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
            yield from ToolRegistry._nested_models(adapter, nested, _seen)

    # -- phase: enrich ------------------------------------------------------

    async def enrich(self, server: FastMCP) -> None:
        """Precompute convergence paths, materialize virtual tools, attach hooks.

        Every registered version of a policy-marked kind gets a precomputed
        path to its policy target. Versions with **no** physical declaration
        get a virtual tool: calling its schema converges the arguments to the
        target and dispatches to the target's physical handler. A kind with no
        recorded policy is skipped entirely (stays plain).
        """
        for kind, versions in self._versions_by_kind().items():
            policy = self._converger.policy_for(kind)
            if policy is None:
                continue
            target = self._resolve_target(kind, policy)
            for version in versions:
                self._paths[(kind, version)] = target
                if (kind, version) in self._physical:
                    continue
                self._register_virtual(server, kind, version, target)
        self._attach_hooks()

    def _versions_by_kind(self) -> dict[str, list[str]]:
        kinds: dict[str, list[str]] = {}
        for kind, version in self._physical:
            kinds.setdefault(kind, []).append(version)
        for versionable in self._manager.list_versions():
            kind = str(versionable.version[0])
            version = str(versionable.version[1])
            kinds.setdefault(kind, [])
            if version not in kinds[kind]:
                kinds[kind].append(version)
        return kinds

    def _register_virtual(
        self, server: FastMCP, kind: str, version: str, target: str
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

        A concrete version returns its model's schema. A meta version (no
        concrete model) is reconstructed implicitly by the engine on migration
        registration (``on_missing="reconstruct_model"``), so the model is
        already materialized here. The LLM sees the full schema it would have
        called against at that version.
        """
        versionable: Any = self._manager.get(kind, version)
        return versionable.model.model_json_schema()

    def _resolve_target(self, kind: str, policy: str) -> str:
        versions = sorted(self._manager.list_versions(kind), key=lambda v: v.version[1])
        if not versions:
            raise ValueError(f"no registered versions for kind {kind!r}")
        if policy == "latest":
            return str(versions[-1].version[1])
        if policy == "earliest":
            return str(versions[0].version[1])
        return policy

    def _attach_hooks(self) -> None:
        """Attach the observer hooks to every registered migration edge.

        One hook per edge means each migration step is observable: an OTEL hook,
        for instance, opens a span per step that nests under the tool call's
        span. The manager owns the registry, so this is a single loop.
        """
        if not self._hooks:
            return
        registry = self._manager.engine.registry
        for kind in registry.kinds:
            for edge in registry.migrations(kind):
                for hook in self._hooks:
                    registry.add_hook(edge, hook)

    # -- call-time helpers (delegated) -------------------------------------

    def path(self, kind: str, version: str) -> str | None:
        return self._converger.path(kind, version)

    def delegate(self, kind: str, version: str):
        """Return a converging delegate for a call to *kind@version*.

        The delegate converges the call's arguments to the version's policy
        target and invokes the **target's** physical handler, so the consumer
        always gets the tool's current behavior. Returns ``None`` when no
        convergence path is precomputed for the version, or the kind is not
        owned by the manager.
        """
        return self._converger.delegate(kind, version)

    def converge_payload(self, arguments: dict) -> dict | None:
        """Converge an unversioned tool's arguments to the latest models.

        A plain (unversioned) tool may still embed versioned models in its
        arguments. When any embedded kind is owned by the manager, the arguments
        converge to the latest version of every registered chain. Returns
        ``None`` when the payload is not versioned at all.
        """
        return self._converger.converge_payload(arguments)


__all__ = ["ToolRegistry"]
