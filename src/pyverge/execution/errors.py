"""Execution runtime errors."""

from __future__ import annotations

from typing import Self

from pyverge.core.errors import PyvergeError


class ExecutionError(PyvergeError):
    """Raised when runtime execution fails."""

    def __init__(self: Self, msg: str) -> None:
        """Initializes ExecutionError."""
        self.msg = msg
        super().__init__(msg)


class ExecutionModeError(ExecutionError):
    """Raised when execution mode does not match the entrypoint."""


class AsyncExecutionRequired(ExecutionModeError):
    """Raised when a sync entrypoint is used with async execution."""


class SyncExecutionRequired(ExecutionModeError):
    """Raised when an async entrypoint is used with sync execution."""


__all__ = [
    "AsyncExecutionRequired",
    "ExecutionError",
    "ExecutionModeError",
    "SyncExecutionRequired",
]
