"""Provider capability and compatibility errors."""

from __future__ import annotations

from typing import Self

from pyverge.core.errors import PyvergeError


class ProviderCapabilityError(PyvergeError):
    """Raised when a provider cannot satisfy a requested capability."""

    def __init__(self: Self, message: str) -> None:
        """Initializes ProviderCapabilityError."""
        super().__init__(message)


__all__ = ["ProviderCapabilityError"]
