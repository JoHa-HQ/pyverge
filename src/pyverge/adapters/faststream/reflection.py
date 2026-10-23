"""Reflect registered subscribers into a manager's graph before start.

FastStream registers subscribers at decoration time, so they are all present on
``broker.subscribers`` before ``app.run()`` — reflection is synchronous and needs
no broker connection. :class:`SubscriberWalker` recovers each handler's declared
payload model; :class:`Reflector` reconciles it into the manager's graph and
validates it, failing fast on a broken graph.
"""

from __future__ import annotations

import inspect
import types
import typing
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pyverge import Manager
from pyverge.providers.types import ModelHandle

if TYPE_CHECKING:
    from faststream import FastStream


def _topic_name(topic: object) -> str:
    """Return the topic name from a plain string or a FastStream topic value."""
    name = getattr(topic, "name", None)
    return name if isinstance(name, str) else str(topic)


@dataclass(frozen=True)
class SubscriberModel:
    """A subscriber's handler plus the payload model it declares."""

    handler: Any
    model: ModelHandle
    topics: tuple[str, ...]


class SubscriberWalker:
    """Walk a broker's subscribers, yielding those with a versioned payload model."""

    def __init__(self, manager: Manager) -> None:
        self._manager = manager

    @staticmethod
    def _original_call(subscriber: Any) -> Any:
        """Return the undecorated handler for *subscriber*, or ``None``."""
        for item in subscriber.calls:
            wrapper = getattr(item, "handler", None)
            original = getattr(wrapper, "_original_call", None)
            if original is not None:
                return original
        return None

    @classmethod
    def _first_model(cls, annotation: Any) -> ModelHandle | None:
        """Return the first concrete model, unwrapping unions."""
        if isinstance(annotation, type):
            return annotation
        if typing.get_origin(annotation) in (typing.Union, types.UnionType):
            for member in typing.get_args(annotation):
                model = cls._first_model(member)
                if model is not None:
                    return model
        return None

    @classmethod
    def declared_model(cls, handler: Any) -> ModelHandle | None:
        """Return the handler's first class-typed parameter annotation.

        Resolves string annotations, unwraps ``Union`` annotations, then returns
        the first parameter annotated with a concrete class.
        """
        if handler is None:
            return None
        original = getattr(handler, "_original_call", handler)
        try:
            hints = typing.get_type_hints(original)
        except Exception:
            hints = {}
        for name, param in inspect.signature(original).parameters.items():
            annotation = hints.get(name, param.annotation)
            model = cls._first_model(annotation)
            if model is not None:
                return model
        return None

    def walk(self, broker: Any) -> Iterator[SubscriberModel]:
        for subscriber in broker.subscribers:
            handler = self._original_call(subscriber)
            model = self.declared_model(handler)
            if model is None or not self._manager.identifies(model):
                continue
            yield SubscriberModel(
                handler=handler,
                model=model,
                topics=tuple(
                    _topic_name(topic) for topic in getattr(subscriber, "topics", ())
                ),
            )


class Reflector:
    """Reconcile a broker's subscriber payload models into a manager's graph."""

    def __init__(self, manager: Manager) -> None:
        self._manager = manager

    def reflect(self, broker: Any) -> list[SubscriberModel]:
        """Reconcile every typed subscriber model into the graph and validate it.

        A missing reference dies before the app serves.
        """
        reflected: list[SubscriberModel] = []
        for found in SubscriberWalker(self._manager).walk(broker):
            registered = self._manager.reconcile_model(found.model)
            self._manager.validate_graph(registered)
            reflected.append(found)
        return reflected

    def __call__(self, app: FastStream) -> None:
        """FastStream ``on_startup`` hook: reflect before consumption."""
        for broker in app.brokers:
            self.reflect(broker)


__all__ = [
    "Reflector",
    "SubscriberModel",
    "SubscriberWalker",
]
