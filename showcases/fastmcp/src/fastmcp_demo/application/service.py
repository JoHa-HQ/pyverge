"""Application layer: the demo use case and the topology walk.

``DemoService`` receives its collaborators (manager, registry, server) from the
DI container and owns only the runnable lifecycle: it runs the async reflection
phases and drives convergent calls. ``walk_topology`` is the reusable
**time-travel round trip**: migrate a newest-shaped payload down to the oldest
version and back up, asserting every hop yields the correctly-typed container.
Run it against any version graph to catch missing reverse edges, non-idempotent
migrations, and finalize drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pyverge.adapters.otel import OTELHook
from pyverge.types import ManagerMigrationKey

from ..domain import ALL_VERSIONS, V1, V2, V3
from ..settings import DemoSettings

#: Forward edges (anchor-reconstructing), newest first.
_FORWARD_EDGES = ((V2, V3), (V1, V2))


@dataclass(frozen=True)
class TopologyHop:
    """One leg of a topology walk: the version visited and the typed result."""

    version: str
    container: type
    payload: dict


def walk_topology(
    manager: Any, kind: str, versions: tuple[str, ...]
) -> list[TopologyHop]:
    """Walk *versions* from newest to oldest and back, asserting typed hops.

    Starts from a newest-shaped payload, migrates down to the oldest version,
    then back up to newest. Every hop is validated against the version's model
    via ``container=`` so a schema mismatch raises instead of passing silently.

    Returns the down-walk hops; raises ``AssertionError`` when a hop returns the
    wrong container type.
    """
    newest = versions[-1]
    newest_cls = manager.get(kind, newest).model

    start = newest_cls.model_validate(
        {"kind": kind, "version": newest, "city": "Berlin"}
    )

    hops: list[TopologyHop] = []
    for version in reversed(versions):
        cls = manager.get(kind, version).model
        result = manager.migrate(
            start.model_dump(mode="json"), target=version, container=cls
        )
        assert isinstance(result, cls), f"{version} did not yield {cls.__name__}"
        hops.append(TopologyHop(version, cls, result.model_dump(mode="json")))

    back = manager.migrate(hops[-1].payload, target=newest, container=newest_cls)
    assert isinstance(back, newest_cls), (
        f"return trip did not yield {newest_cls.__name__}"
    )
    return hops


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
