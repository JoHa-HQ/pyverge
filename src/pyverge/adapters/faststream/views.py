"""Concrete FastStream wrappers.

FastStream object access stays here. Reflection and decorators consume the
ports from :mod:`.ports`, not FastStream internals.
"""

from __future__ import annotations

import inspect
import types
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pyverge.schemas.types import ModelHandle


def _original_call(handler: Any) -> Any:
    return getattr(handler, "_original_call", handler)


def _first_model(annotation: Any) -> ModelHandle | None:
    """Return the first concrete model in *annotation*, unwrapping unions."""
    if isinstance(annotation, type):
        return annotation
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        for member in typing.get_args(annotation):
            model = _first_model(member)
            if model is not None:
                return model
    return None


def _resolved_hints(handler: Any) -> dict[str, Any]:
    try:
        return typing.get_type_hints(handler)
    except Exception:
        return {}


@dataclass(frozen=True)
class HandlerView:
    """A callable's declared payload and return models."""

    handler: Callable[..., Any]

    @property
    def input_model(self) -> ModelHandle | None:
        original = _original_call(self.handler)
        hints = _resolved_hints(original)
        for name, param in inspect.signature(original).parameters.items():
            annotation = hints.get(name, param.annotation)
            model = _first_model(annotation)
            if model is not None:
                return model
        return None

    @property
    def return_model(self) -> ModelHandle | None:
        original = _original_call(self.handler)
        hints = _resolved_hints(original)
        annotation = hints.get("return")
        if annotation is None:
            annotation = inspect.signature(original).return_annotation
        return annotation if isinstance(annotation, type) else None


@dataclass(frozen=True)
class FastStreamSubscriber:
    """A FastStream subscriber, reduced to stable reflected properties."""

    subscriber: Any

    @property
    def topics(self) -> tuple[str, ...]:
        names = []
        for topic in getattr(self.subscriber, "topics", ()):
            name = getattr(topic, "name", None)
            names.append(name if isinstance(name, str) else str(topic))
        return tuple(names)

    @property
    def handler(self) -> Callable[..., Any] | None:
        for item in getattr(self.subscriber, "calls", ()):
            wrapper = getattr(item, "handler", None)
            original = getattr(wrapper, "_original_call", None)
            if original is not None:
                return original
        return None

    @property
    def input_model(self) -> ModelHandle | None:
        handler = self.handler
        return HandlerView(handler).input_model if handler is not None else None


@dataclass(frozen=True)
class PublisherView:
    """A publisher handler plus the topics it publishes to."""

    handler: Callable[..., Any]
    topics: tuple[str, ...]

    @property
    def return_model(self) -> ModelHandle | None:
        return HandlerView(self.handler).return_model


__all__ = [
    "FastStreamSubscriber",
    "HandlerView",
    "PublisherView",
]
