from __future__ import annotations

from typing import Any, Self

from pyverge.core.errors import PyvergeError


class RevisionMismatchError(PyvergeError):
    """Raised when a requested revision does not match the locked graph."""

    def __init__(self: Self, *, expected: Any, actual: Any) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(
            "Graph revision mismatch: "
            f"expected {expected.content_digest}, got {actual.content_digest}"
        )


class VersionStrategyMismatchError(PyvergeError):
    """Raised when one graph mixes incompatible version value types."""

    def __init__(self: Self, strategies: tuple[str, ...]) -> None:
        self.strategies = strategies
        super().__init__(
            f"Graph mixes version strategies: {', '.join(sorted(strategies))}"
        )


class RevisionConflictError(PyvergeError):
    """Raised when a store CAS check rejects a stale revision or generation."""


__all__ = [
    "RevisionConflictError",
    "RevisionMismatchError",
    "VersionStrategyMismatchError",
]
