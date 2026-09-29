"""Application layer: the demo use case.

``DemoService`` receives its collaborators (manager, discovery, server) from the
DI container and exposes the runnable surface. The discovery lifecycle runs as
the server's **lifespan** — FastMCP enters it when the server is served or
driven through a client. Tracing is wired at the composition root, so this
service knows nothing of OpenTelemetry.
"""

from __future__ import annotations

import logging
from typing import Any

from ..settings import DemoSettings

logger = logging.getLogger(__name__)


class DemoService:
    """The runnable demo app: collaborators from the DI container.

    The collaborators come from the DI container — this class builds nothing.
    The server carries the discovery lifecycle as its lifespan.
    """

    def __init__(
        self,
        settings: DemoSettings,
        manager: Any,
        discovery: Any,
        server: Any,
    ) -> None:
        self._settings = settings
        self.manager = manager
        self.discovery = discovery
        self.server = server

    @property
    def kind(self) -> str:
        """The versioned kind this demo exposes."""
        return self._settings.graph.kind
