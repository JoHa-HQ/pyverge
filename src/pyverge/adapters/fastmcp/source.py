"""FastMCP SourcePort adapter."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from pyverge.discovery import ModelDescriptor, SourceVisitor

from .reflection import ComponentReflection

if TYPE_CHECKING:
    from fastmcp import FastMCP


class FastMCPSource:
    """Expose FastMCP primitives as model descriptors."""

    def __init__(
        self,
        server: FastMCP,
        providers: Sequence[ComponentReflection],
    ) -> None:
        self._server = server
        self._providers = tuple(providers)

    async def accept(self, visitor: SourceVisitor) -> None:
        for provider in self._providers:
            async for node in provider.reflect(self._server):
                visitor.visit(
                    ModelDescriptor(
                        node.versionable(),
                        "fastmcp",
                        {"kind": node.kind, "version": node.version},
                    )
                )


__all__ = ["FastMCPSource"]
