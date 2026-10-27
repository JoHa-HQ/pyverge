# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""Static source fixtures for discovery tests."""

from __future__ import annotations

from dataclasses import dataclass

from pyverge.discovery import SourceDescriptor, SourceVisitor


@dataclass(frozen=True, slots=True)
class StaticSource:
    """A source that emits a fixed descriptor sequence."""

    descriptors: tuple[SourceDescriptor, ...]
    source_id: str

    def accept(self, visitor: SourceVisitor) -> None:
        for descriptor in self.descriptors:
            visitor.visit(descriptor)
