"""ToolRegistry — the FastMCP reflection lifecycle in one pipeline.

The `lifespan` hook the customer hands to FastMCP. It owns the FastMCP-specific
wiring only: discovery (``list_tools``), the four ordered phases, virtual-tool
materialization and hook attachment. The framework-agnostic work — injection
detection, schema reflection, contract checks, call convergence — lives in
:mod:`pyverge.serving`.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from pyverge.manager import Manager
from pyverge.serving import SchemaReflection, ServingContract, injected_names
from pyverge.serving.convergence import Converger
from pyverge.serving.reflection import IDENTITY
from pyverge.types import Attachable

from .discovery import ToolDiscovery

if TYPE_CHECKING:
    from fastmcp import FastMCP


def _tool_handler(tool: Any):
    """Return the callable behind a FastMCP tool (its wired ``fn``)."""
    return getattr(tool, "fn", None) or tool.run


def _tool_schema(tool: Any) -> dict:
    """Return a FastMCP tool's reflected input schema."""
    return dict(tool.parameters)


class ToolRegistry:
    """Server-wide reflection lifecycle: search, register, reconcile, enrich."""

    def __init__(
        self,
        manager: Manager,
        *,
        policies: dict[str, str] | None = None,
        fallback_policy: str | None = None,
        hooks: Sequence[Attachable] = (),
        injection_detector=None,
    ) -> None:
        self._manager = manager
        self._hooks = tuple(hooks)
        self._detector = injection_detector
        self._physical: dict = {}
        self._paths: dict = {}
        self._converger = Converger(
            manager,
            physical=self._physical,
            paths=self._paths,
            handler_for=_tool_handler,
            policies=policies,
            fallback_policy=fallback_policy,
        )
        self._contract = ServingContract(manager, self._converger.owns)

    @asynccontextmanager
    async def __call__(self, server: FastMCP):
        await self.search(server)
        await self.register(server)
        await self.reconcile(server)
        await self.enrich(server)
        yield self

    def _reflection(self, kind: str, version: str, tool: Any) -> SchemaReflection:
        adapter = self._manager.engine.adapter
        return SchemaReflection(
            adapter,
            kind=kind,
            version=version,
            schema=_tool_schema(tool),
            injected=frozenset(injected_names(_tool_handler(tool), self._detector)),
        )

    # -- phase: search ------------------------------------------------------

    async def search(self, server: FastMCP) -> None:
        """Index every physical versioned tool the manager owns and marks."""
        for (kind, version), tool in (await ToolDiscovery().search(server)).items():
            if not self._converger.owns(kind):
                continue
            if self._converger.policy_for(kind) is None:
                continue
            self._physical[(kind, version)] = tool

    # -- phase: register ----------------------------------------------------

    async def register(self, server: FastMCP) -> None:
        """Materialize each physical tool's reflected signature as its anchor."""
        for (kind, version), tool in self._physical.items():
            if self._has_version(kind, version):
                continue
            anchor = self._materialize(self._reflection(kind, version, tool))
            if anchor is None:
                raise ValueError(
                    f"tool {kind!r}@{version} is versioned but no model for that "
                    "version is registered and its signature cannot materialize one"
                )
            self._manager.engine.store_model(anchor)

    def _has_version(self, kind: str, version: str) -> bool:
        return any(
            str(v.version[1]) == version for v in self._manager.list_versions(kind)
        )

    @staticmethod
    def _materialize(reflection: SchemaReflection):
        try:
            return reflection.versionable()
        except (AttributeError, TypeError, ValueError):
            return None

    # -- phase: reconcile ---------------------------------------------------

    async def reconcile(self, server: FastMCP) -> None:
        """Validate each reflected signature against the registered contract."""
        for (kind, version), tool in self._physical.items():
            schema_reflection = self._reflection(kind, version, tool)
            self._contract.check_registered(kind, version)
            self._contract.check_signature(kind, version, schema_reflection.schema)
            self._contract.check_agreement(kind, version, schema_reflection)

    # -- phase: enrich ------------------------------------------------------

    async def enrich(self, server: FastMCP) -> None:
        """Precompute paths, materialize virtual tools, attach hooks."""
        for kind, versions in self._versions_by_kind().items():
            policy = self._converger.policy_for(kind)
            if policy is None:
                continue
            target = self._resolve_target(kind, policy)
            for version in versions:
                self._paths[(kind, version)] = target
                if (kind, version) not in self._physical:
                    self._register_virtual(server, kind, version, target)
        self._attach_hooks()

    def _versions_by_kind(self) -> dict[str, list[str]]:
        kinds: dict[str, list[str]] = {}
        for kind, version in self._physical:
            kinds.setdefault(kind, []).append(version)
        for versionable in self._manager.list_versions():
            kind, version = str(versionable.version[0]), str(versionable.version[1])
            bucket = kinds.setdefault(kind, [])
            if version not in bucket:
                bucket.append(version)
        return kinds

    def _register_virtual(
        self, server: FastMCP, kind: str, version: str, target: str
    ) -> None:
        from fastmcp.tools.function_tool import FunctionTool  # noqa: PLC0415

        model = self._manager.get(kind, version).model
        schema = model.model_json_schema()
        schema["properties"] = {
            k: v for k, v in schema.get("properties", {}).items() if k not in IDENTITY
        }
        server.add_tool(
            FunctionTool(
                name=kind,
                version=version,
                parameters=schema,
                fn=self._converger.make_indirection(kind, version, target),
            )
        )

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
        """Attach the observer hooks to every registered migration edge."""
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
        return self._converger.delegate(kind, version)

    def converge_payload(self, arguments: dict) -> dict | None:
        return self._converger.converge_payload(arguments)


__all__ = ["ToolRegistry"]
