"""Ports for the FastMCP adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Any, Protocol

from .domain import Entrance, Policy, VirtualComponent

if TYPE_CHECKING:
    from fastmcp import FastMCP


class ComponentKind(Protocol):
    """Port: one FastMCP primitive family."""

    @property
    def name(self) -> str:
        """Stable family name used by the provider and policy map."""
        ...

    def components(self, server: FastMCP) -> AsyncIterator[Any]:
        """Yield every component of this family on *server*."""
        ...

    def kind(self, component: Any) -> str:
        """Return the graph kind represented by *component*."""
        ...

    def version(self, component: Any) -> str | None:
        """Return the graph version represented by *component*."""
        ...

    def policy(self, component: Any) -> Policy | None:
        """Return the policy declared by *component*, if any."""
        ...

    def handler(self, component: Any) -> Callable[..., Any] | None:
        """Return the callable behind *component*, if any."""
        ...

    def entrance(
        self,
        component: Any,
        *,
        policy: Policy | None = None,
        explicit: bool = False,
    ) -> Entrance | None:
        """Bind *component* to a graph entrance, or ``None`` if unversioned."""
        ...

    def materialize(self, server: FastMCP, virtual: VirtualComponent) -> Any:
        """Create the host primitive for *virtual*."""
        ...


__all__ = ["ComponentKind"]
