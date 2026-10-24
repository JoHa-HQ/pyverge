"""Identifier factory port for runs and steps."""

from __future__ import annotations

import uuid
from typing import Protocol


class IdFactory(Protocol):
    """Generate opaque, sortable-enough identifiers."""

    def new(self, prefix: str = "") -> str:
        """Return a fresh identifier, optionally prefixed."""
        ...


class UuidIdFactory:
    """Default UUID4-based factory."""

    def new(self, prefix: str = "") -> str:
        """Return ``prefix + uuid4`` (no separator added)."""
        value = uuid.uuid4().hex
        return f"{prefix}{value}" if prefix else value


__all__ = ["IdFactory", "UuidIdFactory"]
