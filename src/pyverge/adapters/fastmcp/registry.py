"""ToolRegistry — facade over the FastMCP lifecycle collaborators.

``ToolRegistry`` is the ``lifespan`` hook the customer hands to FastMCP. One
manager per source: it binds exactly one bounded context, so there is no
manager routing. It wires the collaborators over the shared ``_physical`` /
``_paths`` bookkeeping:

* :class:`~pyverge.adapters.fastmcp.discovery.ToolDiscovery` — reflect the
  server and index the physical versioned tools,
* :class:`~pyverge.adapters.fastmcp.registration.Registrar` — materialize each
  physical tool's signature as its anchor, validate the registered trees,
  precompute paths and materialize virtual tools,
* :class:`~pyverge.adapters.fastmcp.converger.Converger` — call-time routing:
  delegates and payload convergence over the precomputed paths.

Lifecycle phases run in order: ``search`` (find the physical versioned tools),
``register`` (materialize each physical tool's signature as its anchor),
``reconcile`` (validate the reflected signature tree attaches onto the
registered tree), ``enrich`` (precompute paths and materialize virtual tools,
and attach the observer ``hooks`` to every migration edge).
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from pyverge.manager import Manager
from pyverge.types import Attachable

from .converger import Converger
from .discovery import ToolDiscovery
from .registration import Registrar

if TYPE_CHECKING:
    from fastmcp import FastMCP


class ToolRegistry:
    """Server-wide reflection lifecycle: search, register, reconcile, enrich."""

    def __init__(
        self,
        manager: Manager,
        *,
        policies: dict[str, str] | None = None,
        fallback_policy: str | None = None,
        hooks: Sequence[Attachable] = (),
    ) -> None:
        self._manager = manager
        self._hooks = tuple(hooks)
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
        self._registrar = Registrar(
            self._converger,
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

    # -- phases (delegated) ------------------------------------------------

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

    async def register(self, server: FastMCP) -> None:
        """Materialize every physical versioned tool's signature as an anchor."""
        await self._registrar.register(server)

    async def reconcile(self, server: FastMCP) -> None:
        """Merge the reflected signature tree onto the registered tree."""
        await self._registrar.reconcile(server)

    async def enrich(self, server: FastMCP) -> None:
        """Precompute convergence paths, materialize virtual tools, attach hooks."""
        await self._registrar.enrich(server)
        self._attach_hooks()

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
