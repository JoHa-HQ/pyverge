"""Application layer: the demo use case.

``DemoService`` receives its collaborators (manager, registry, server) from the
DI container and owns only the runnable lifecycle: it runs the async reflection
phases and drives convergent calls. Tracing is wired at the composition root —
the registry carries the per-edge hooks and the server carries the call-level
span factory — so this service knows nothing of OpenTelemetry.
"""

from __future__ import annotations

from typing import Any

from ..domain import ALL_VERSIONS
from ..settings import DemoSettings


class DemoService:
    """Runs the reflection lifecycle over the injected collaborators.

    The collaborators come from the DI container — this class builds nothing.
    """

    def __init__(
        self,
        settings: DemoSettings,
        manager: Any,
        registry: Any,
        server: Any,
    ) -> None:
        self._settings = settings
        self.manager = manager
        self.registry = registry
        self.server = server

    @property
    def kind(self) -> str:
        """The versioned kind this demo exposes."""
        return self._settings.graph.kind

    async def prepare(self) -> None:
        """Run the reflection lifecycle once.

        The server (built by the container) carries the physical anchor tool;
        the registry reflects it, reconciles the signature against the
        registered contract, enriches virtual older tools and attaches the
        tracing hooks. Runs exactly once — re-running would re-materialize the
        virtual tools.
        """
        await self.registry.search(self.server)
        await self.registry.register(self.server)
        await self.registry.reconcile(self.server)
        await self.registry.enrich(self.server)

    async def demo_calls(self) -> list[tuple[str, dict]]:
        """Drive one convergent call per registered version, through the server.

        Calls go via ``server.call_tool`` so they pass the ConvergeMiddleware —
        production's path — which opens the parent span each migration step then
        nests under.
        """
        kind = self._settings.graph.kind
        results: list[tuple[str, dict]] = []
        for version in ALL_VERSIONS:
            call = await self.server.call_tool(
                kind, {"city": "Berlin", "version": version}
            )
            results.append((version, call.structured_content or {}))
        return results
