from __future__ import annotations

from typing import Any

from fastmcp.server.extensions import ServerExtension

from pyverge.manager import Manager


class PyvergeExtension(ServerExtension):
    """Advertise pyverge graph capabilities to FastMCP clients."""

    identifier = "com.joha/pyverge"
    auto_register = True

    def __init__(self, manager: Manager) -> None:
        self._manager = manager

    @property
    def manager(self) -> Manager:
        return self._manager

    def settings(self) -> dict[str, Any]:
        return {
            "namespace": self._manager.engine.namespace,
            "models": self._manager.engine.model_count,
            "migrations": self._manager.engine.migration_count,
        }


__all__ = ["PyvergeExtension"]
