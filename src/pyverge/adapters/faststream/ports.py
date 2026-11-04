"""Ports for the FastStream adapter."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypeVar

from pyverge.core.graph.planning.targets import TargetSelector

Fn = TypeVar("Fn", bound=Callable[..., Any])


class HandlerBinder(Protocol):
    """Binds a handler's typed payload parameter to a model or union."""

    def bind(self, handler: Any, model: Any) -> None: ...


class ResultConverger(Protocol):
    """Wraps a handler so its return value is converged before publish."""

    def wrap(self, handler: Fn) -> Fn: ...


__all__ = [
    "Fn",
    "HandlerBinder",
    "ResultConverger",
    "TargetSelector",
]
