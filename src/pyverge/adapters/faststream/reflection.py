"""Reflect registered subscribers into a manager's graph before start.

FastStream registers subscribers at decoration time, so they are all present on
``broker.subscribers`` before ``app.run()`` — reflection is synchronous and needs
no broker connection. A :class:`SubscriberWalker` recovers each handler's
declared payload model; the :class:`Reflector` reconciles it into the manager's
graph and validates it, failing fast on a broken graph.
"""

from __future__ import annotations

import inspect
import typing
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pyverge import Manager
from pyverge.providers.types import ModelHandle

if TYPE_CHECKING:
    from faststream import FastStream


@dataclass(frozen=True)
class SubscriberModel:
    """A subscriber's handler plus the payload model it declares."""

    handler: Any
    model: ModelHandle
    topics: tuple[str, ...]


@dataclass(frozen=True)
class ReflectedSubscriber:
    """A subscriber's handler reflected to its declared payload model."""

    handler: Any
    model: ModelHandle
    topics: tuple[str, ...]


def original_call(subscriber: Any) -> Any:
    """Return the undecorated handler for *subscriber*, or ``None``."""
    for item in subscriber.calls:
        wrapper = getattr(item, "handler", None)
        original = getattr(wrapper, "_original_call", None)
        if original is not None:
            return original
    return None


def typed_model(handler: Any) -> ModelHandle | None:
    """Return the handler's first class-typed parameter annotation.

    Resolves string annotations (modules using ``from __future__ import
    annotations``), then returns the first parameter annotated with a class.
    """
    if handler is None:
        return None
    try:
        hints = typing.get_type_hints(handler)
    except Exception:
        hints = {}
    for name, param in inspect.signature(handler).parameters.items():
        annotation = hints.get(name, param.annotation)
        if isinstance(annotation, type):
            return annotation
    return None


class SubscriberWalker:
    """Walk a broker's subscribers, yielding those with a versioned payload model."""

    def __init__(self, manager: Manager) -> None:
        self._manager = manager

    def walk(self, broker: Any) -> Iterator[SubscriberModel]:
        for subscriber in broker.subscribers:
            handler = original_call(subscriber)
            model = typed_model(handler)
            if model is None or not self._manager.identifies(model):
                continue
            yield SubscriberModel(
                handler=handler,
                model=model,
                topics=tuple(getattr(subscriber, "topics", ())),
            )


class Reflector:
    """Reconcile a broker's subscriber payload models into a manager's graph."""

    def __init__(self, manager: Manager) -> None:
        self._manager = manager

    def reflect(self, broker: Any) -> list[ReflectedSubscriber]:
        """Reconcile every typed subscriber model into the graph and validate it.

        A missing reference dies before the app serves.
        """
        reflected: list[ReflectedSubscriber] = []
        for found in SubscriberWalker(self._manager).walk(broker):
            registered = self._manager.reconcile_model(found.model)
            self._manager.validate_graph(registered)
            reflected.append(
                ReflectedSubscriber(
                    handler=found.handler,
                    model=found.model,
                    topics=found.topics,
                )
            )
        return reflected

    def __call__(self, app: FastStream) -> None:
        """FastStream ``on_startup`` hook: reflect before consumption."""
        for broker in app.brokers:
            self.reflect(broker)


__all__ = [
    "ReflectedSubscriber",
    "Reflector",
    "SubscriberModel",
    "SubscriberWalker",
    "original_call",
    "typed_model",
]
