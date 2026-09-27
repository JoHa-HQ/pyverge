"""ToolRegistry — facade over the FastMCP lifecycle collaborators.

``ToolRegistry`` is the ``lifespan`` hook the customer hands to FastMCP; it
owns no logic of its own beyond wiring the three collaborators over the
shared ``_physical`` / ``_paths`` bookkeeping:

* :class:`~pyverge.adapters.fastmcp.discovery.ToolDiscovery` — reflect the
  server and index the physical versioned tools,
* :class:`~pyverge.adapters.fastmcp.registration.Registrar` — materialize each
  physical tool's signature as its anchor, validate the registered trees,
  precompute paths and materialize virtual tools,
* :class:`~pyverge.adapters.fastmcp.routing.Converger` — call-time routing:
  delegates and payload convergence over the precomputed paths.

Lifecycle phases run in order: ``search`` (find the physical versioned tools),
``register`` (materialize each physical tool's signature as its anchor),
``reconcile`` (validate the reflected signature tree attaches onto the
registered tree), ``enrich`` (precompute paths and materialize virtual tools).
Per-component *reflection* — turning a single tool, prompt or resource into a
compliant model — lives in :mod:`pyverge.adapters.fastmcp.reflection` and
never touches the registry.
"""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from pyverge.manager import Manager

from .discovery import ToolDiscovery
from .registration import Registrar
from .router import ToolManagerRouter
from .routing import Converger

if TYPE_CHECKING:
    from fastmcp import FastMCP


class ToolRegistry:
    """Server-wide reflection lifecycle: search, register, reconcile, enrich."""

    def __init__(
        self,
        managers: Manager | Iterable[Manager],
        *,
        policies: dict[str, str] | None = None,
        fallback_policy: str | None = None,
    ) -> None:
        if isinstance(managers, Manager):
            managers = [managers]
        self._router = ToolManagerRouter(
            managers,
            policies=policies,
            fallback_policy=fallback_policy,
        )
        self._physical: dict = {}
        self._paths: dict = {}
        self._discovery = ToolDiscovery()
        self._converger = Converger(
            self._router,
            physical=self._physical,
            paths=self._paths,
        )
        self._registrar = Registrar(
            self._router,
            physical=self._physical,
            paths=self._paths,
            converger=self._converger,
        )

    @asynccontextmanager
    async def __call__(self, server: FastMCP):
        """FastMCP lifespan entry point."""
        await self.search(server)
        await self.register(server)
        await self.reconcile(server)
        await self.enrich(server)
        yield self

    def _manager_for(self, kind: str) -> Manager | None:
        return self._router.manager_for(kind)

    # -- phases (delegated) ------------------------------------------------

    async def search(self, server: FastMCP) -> None:
        """Find every physical versioned tool.

        A tool is versioned iff it declares ``version=...``, its kind is owned
        by a manager **and** a policy is recorded for that kind.  A tool with
        no recorded policy is plain and is left untouched by the adapter.
        """
        for (kind, version), tool in (await self._discovery.search(server)).items():
            if self._manager_for(kind) is None:
                continue
            if self._router.policy_for(kind) is None:
                continue
            self._physical[(kind, version)] = tool

    async def register(self, server: FastMCP) -> None:
        """Materialize every physical versioned tool's signature as an anchor."""
        await self._registrar.register(server)

    async def reconcile(self, server: FastMCP) -> None:
        """Merge the reflected signature tree onto the registered tree."""
        await self._registrar.reconcile(server)

    async def enrich(self, server: FastMCP) -> None:
        """Precompute convergence paths and materialize virtual tools."""
        await self._registrar.enrich(server)

    # -- call-time helpers (delegated) -------------------------------------

    def path(self, kind: str, version: str) -> str | None:
        return self._converger.path(kind, version)

    def delegate(self, kind: str, version: str):
        """Return a converging delegate for a call to *kind@version*.

        The delegate converges the call's arguments to the version's policy
        target and invokes the **target's** physical handler, so the consumer
        always gets the tool's current behavior.  Returns ``None`` when no
        convergence path is precomputed for the version, or the kind is not
        owned by any manager.
        """
        return self._converger.delegate(kind, version)

    def converge_payload(self, arguments: dict) -> dict | None:
        """Converge an unversioned tool's arguments to the latest models.

        A plain tool (no version param, no versioned chain of its own) may
        still embed versioned models in its arguments.  When any embedded kind
        is owned by a manager, the arguments converge to the latest version of
        every registered chain.  Returns ``None`` when the payload is not
        versioned at all.
        """
        return self._converger.converge_payload(arguments)
