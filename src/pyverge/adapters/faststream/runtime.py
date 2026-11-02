"""FastStream convergence runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING

from faststream.exceptions import StartupValidationError

from pyverge.adapters.runtime import ConvergenceRuntime
from pyverge.registry.errors import HealthValidationError

if TYPE_CHECKING:
    from pyverge.execution import Runner


class FastStreamRuntime(ConvergenceRuntime):
    """Convergence runtime with FastStream's startup error semantics."""

    def bind(self, runner: Runner, *, validate_health: bool = True) -> None:
        """Bind the runner and optionally validate registry health.

        Args:
            runner: Fully configured runner for this application.
            validate_health: Validate the registry before the app starts.

        Raises:
            StartupValidationError: If registry health fails the fail level.
        """
        super().bind(runner)
        if validate_health:
            try:
                self.validate_health()
            except HealthValidationError as error:
                raise StartupValidationError(str(error)) from error


__all__ = ["FastStreamRuntime"]
