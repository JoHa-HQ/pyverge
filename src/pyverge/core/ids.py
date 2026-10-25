from __future__ import annotations

import uuid
from typing import Protocol


class IdFactory(Protocol):
    """Generate opaque, sortable-enough identifiers."""

    def new(self, prefix: str = "") -> str: ...


class UuidIdFactory:
    """Default UUID4-based factory."""

    def new(self, prefix: str = "") -> str:
        value = uuid.uuid4().hex
        return f"{prefix}{value}" if prefix else value


__all__ = ["IdFactory", "UuidIdFactory"]
