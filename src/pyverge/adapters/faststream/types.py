"""Port and type definitions for the FastStream adapter.

Kept apart from the implementations so the seams depend on these abstractions
(and so the concrete adapters — e.g. ``SignatureBinder``, ``ReturnConverger`` —
are imported only where they are wired). Wire parsing is FastStream's; it is not
a port here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypeVar

from pyverge.core.types import ModelData
from pyverge.providers.types import ModelHandle

Fn = TypeVar("Fn", bound=Callable[..., Any])


class HandlerBinder(Protocol):
    """Binds a handler's typed payload parameter to *model*."""

    def bind(self, handler: Any, model: ModelHandle) -> None:
        """Re-annotate *handler*'s payload parameter with *model*."""
        ...


class ResultConverger(Protocol):
    """Wraps a handler so its return value is converged before publish."""

    def wrap(self, handler: Fn) -> Fn:
        """Return a handler whose return is transformed for the publish seam."""
        ...


class PayloadDumper(Protocol):
    """Dumps a handler return value into a payload mapping."""

    def __call__(self, value: object) -> ModelData:
        """Return *value* as a payload dict."""
        ...


__all__ = [
    "Fn",
    "HandlerBinder",
    "PayloadDumper",
    "ResultConverger",
]
