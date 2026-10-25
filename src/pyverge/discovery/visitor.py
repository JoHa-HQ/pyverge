from __future__ import annotations

from pyverge.discovery.descriptors import SourceDescriptor, descriptor_commands
from pyverge.discovery.types import RegistrationCommand, SourceVisitor


class RegistrationCollector(SourceVisitor):
    """Collect registration commands while traversing a source."""

    def __init__(self) -> None:
        self.commands: list[RegistrationCommand] = []
        self.descriptors = 0
        self.skipped: list[str] = []

    def visit(self, descriptor: SourceDescriptor) -> None:
        commands = descriptor_commands(descriptor)
        if not commands:
            self.skipped.append(type(descriptor).__name__)
            return
        self.commands.extend(commands)
        self.descriptors += 1


__all__ = ["RegistrationCollector"]
