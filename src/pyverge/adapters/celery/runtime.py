"""Celery convergence runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING

from celery.exceptions import CeleryError

if TYPE_CHECKING:
    from pyverge.runtime import Runner

from pyverge.adapters.runtime import ConvergenceRuntime
from pyverge.core.registry.errors import HealthValidationError


class CeleryRuntime(ConvergenceRuntime):
    """Convergence runtime with Celery's startup error semantics."""

    def bind(self, runner: Runner, *, validate_health: bool = True) -> None:
        """Bind the runner and optionally validate registry health.

        Args:
            runner: Fully configured runner for the worker.
            validate_health: Validate the registry before the worker starts.

        Raises:
            CeleryError: If registry health fails the fail level.
        """
        super().bind(runner)
        if validate_health:
            try:
                self.validate_health()
            except HealthValidationError as error:
                raise CeleryError(str(error)) from error


__all__ = ["CeleryRuntime"]
