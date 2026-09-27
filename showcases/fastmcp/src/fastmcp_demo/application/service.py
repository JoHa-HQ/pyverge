"""Application layer: the demo use case.

``DemoService`` receives its collaborators (manager, registry, server) from the
DI container and owns only the runnable lifecycle: it runs the async reflection
phases. Tracing is wired at the composition root — the registry carries the
per-edge hooks and the server carries the call-level span factory — so this
service knows nothing of OpenTelemetry.
"""

from __future__ import annotations

import logging
from typing import Any

from ..settings import DemoSettings

logger = logging.getLogger(__name__)


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
        logger.info("reflection lifecycle: search -> register -> reconcile -> enrich")
        await self.registry.search(self.server)
        await self.registry.register(self.server)
        await self.registry.reconcile(self.server)
        await self.registry.enrich(self.server)
        logger.info("reflection lifecycle complete")
