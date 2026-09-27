"""Application layer: the demo use case.

``DemoService`` receives its collaborators (manager, registry, server) from the
DI container and owns only the runnable lifecycle: it runs the async reflection
phases and drives convergent calls.
"""

from __future__ import annotations

from typing import Any

from pyverge.adapters.otel import OTELHook
from pyverge.types import ManagerMigrationKey

from ..domain import ALL_VERSIONS, V1, V2, V3
from ..settings import DemoSettings

#: Forward edges (anchor-reconstructing), newest first.
_FORWARD_EDGES = ((V2, V3), (V1, V2))


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
        tracer: Any | None = None,
    ) -> None:
        self._settings = settings
        self.manager = manager
        self.registry = registry
        self.server = server
        self._tracer = tracer

    @property
    def kind(self) -> str:
        """The versioned kind this demo exposes."""
        return self._settings.graph.kind

    def _attach_hooks(self) -> None:
        """Attach an OTEL hook to every forward edge once the registrations exist."""
        if self._tracer is None:
            return
        for source, target in _FORWARD_EDGES:
            self.manager.add_hook(
                ManagerMigrationKey(self._settings.graph.kind, source, target),
                OTELHook(
                    tracer=self._tracer,
                    service=self._settings.telemetry.service_name,
                ),
            )

    async def prepare(self) -> None:
        """Run the reflection lifecycle, then expose the tracing hook.

        The server (built by the container) carries the physical anchor tool;
        the registry reflects it, reconciles the signature against the
        registered contract, and enriches virtual older tools. Runs exactly
        once — re-running would re-materialize the virtual tools.
        """
        await self.registry.search(self.server)
        await self.registry.register(self.server)
        await self.registry.reconcile(self.server)
        await self.registry.enrich(self.server)
        self._attach_hooks()

    def demo_calls(self) -> list[tuple[str, dict]]:
        """Drive one convergent call per registered version and return the results."""
        kind = self._settings.graph.kind
        results: list[tuple[str, dict]] = []
        for version in ALL_VERSIONS:
            delegate = self.registry.delegate(kind, version)
            assert delegate is not None, f"no delegate for {kind}@{version}"
            results.append((version, delegate(city="Berlin")))
        return results
