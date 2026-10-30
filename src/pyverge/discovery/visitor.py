from __future__ import annotations

from pyverge.discovery.descriptors import (
    SourceDescriptor,
    is_registrable,
)
from pyverge.discovery.types import SourceVisitor


class RegistrationCollector(SourceVisitor):
    """Collect registrable descriptors while traversing a source."""

    def __init__(self) -> None:
        self.registrations: list[SourceDescriptor] = []
        self.descriptors = 0
        self.skipped: list[str] = []

    def visit(self, descriptor: SourceDescriptor) -> None:
        if not is_registrable(descriptor):
            self.skipped.append(type(descriptor).__name__)
            return
        self.registrations.append(descriptor)
        self.descriptors += 1


__all__ = ["RegistrationCollector"]
