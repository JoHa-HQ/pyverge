from __future__ import annotations

from typing import Any, Self

from pyverge.core.errors import PyvergeError


class ExecutionError(PyvergeError):
    """Raised when runtime execution fails."""

    def __init__(self: Self, msg: str) -> None:
        self.msg = msg
        super().__init__(msg)


class ExecutionModeError(ExecutionError):
    """Raised when execution mode does not match the entrypoint."""


class AsyncExecutionRequired(ExecutionModeError):
    """Raised when a sync entrypoint is used with async execution."""


class SyncExecutionRequired(ExecutionModeError):
    """Raised when an async entrypoint is used with sync execution."""


class TargetValidationError(ExecutionError):
    """A converged target payload failed validation against its model."""

    def __init__(
        self, path: tuple[str | int, ...], target_model: Any, error: Exception
    ) -> None:
        self.path = path
        self.target_model = target_model
        self.error = error
        super().__init__(
            f"Target validation failed at {path!r} for {target_model!r}: {error}"
        )


class UnknownModelError(ExecutionError):
    """A plan entry targets a model the runner cannot identify."""


class AmbiguousModelError(ExecutionError):
    """A model handle is claimed by more than one adapter."""


__all__ = [
    "AmbiguousModelError",
    "AsyncExecutionRequired",
    "ExecutionError",
    "ExecutionModeError",
    "SyncExecutionRequired",
    "TargetValidationError",
    "UnknownModelError",
]
