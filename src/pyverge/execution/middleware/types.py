"""Execution middleware contracts."""

from __future__ import annotations

from typing import Any, Protocol


class BackendMiddleware(Protocol):
    """Wrap one execution backend with cross-cutting behavior."""

    def wrap(self, inner: Any) -> Any: ...


__all__ = ["BackendMiddleware"]
