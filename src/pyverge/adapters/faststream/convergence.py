"""Convergence application service.

Binds a pyverge ``Manager`` (domain service) to a target policy and exposes a
single use case: converge a payload mapping to that target. Framework seams
depend on this, not on the manager directly.
"""

from __future__ import annotations

from pyverge import Manager
from pyverge.core.types import ModelData
from pyverge.manager.types import TargetPolicy


class Converger:
    """Converge payload mappings through a manager under a bound target policy."""

    def __init__(self, manager: Manager, target: TargetPolicy = "latest") -> None:
        self._manager = manager
        self._target = target

    def converge(self, payload: ModelData) -> ModelData:
        """Return *payload* converged to the bound target version."""
        return self._manager.migrate(payload, target=self._target)


__all__ = ["Converger"]
