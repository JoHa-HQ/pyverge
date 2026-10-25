"""Shared kernel errors: payload traversal vocabulary and root type."""

from __future__ import annotations

from typing import Self


class PyvergeError(Exception):
    """Base exception for every pyverge domain error."""


class CatalogError(PyvergeError):
    """Raised when a catalog operation fails."""

    def __init__(self: Self, catalog_name: str, message: str) -> None:
        """Initializes CatalogError."""
        self.catalog_name = catalog_name
        super().__init__(message)


class PayloadError(PyvergeError):
    """Raised when payload traversal or extraction fails."""


class PayloadValidationError(PayloadError):
    """Raised when a payload does not conform to the container schema."""

    def __init__(
        self: Self,
        path: tuple[str | int, ...],
        message: str,
    ) -> None:
        """Initializes PayloadValidationError."""
        self.path = path
        super().__init__(f"Payload validation failed at {path}: {message}")


class MaxDepthExceededError(PayloadError):
    """Raised when an entry is deeper than the configured traversal limit."""

    def __init__(
        self: Self,
        path: tuple[str | int, ...],
        depth: int,
        kind: str,
        version: str,
        max_depth: int,
    ) -> None:
        """Initializes MaxDepthExceededError."""
        self.path = path
        self.depth = depth
        self.kind = kind
        self.version = version
        self.max_depth = max_depth
        super().__init__(
            f"Versioned entry {kind}@{version} at path {path} (depth {depth}) "
            f"exceeds max_migration_depth ({max_depth})."
        )


__all__ = [
    "CatalogError",
    "MaxDepthExceededError",
    "PayloadError",
    "PayloadValidationError",
    "PyvergeError",
]
