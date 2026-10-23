"""Reflect registered subscribers into a manager's graph before start.

FastStream registers subscribers at decoration time, so they are all present on
``broker.subscribers`` before ``app.run()`` — reflection is synchronous and needs
no broker connection. :class:`SubscriberWalker` recovers each handler's declared
payload model; :class:`Reflector` reconciles it into the manager's graph and
validates it, failing fast on a broken graph.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pyverge import Manager
from pyverge.providers.types import ModelHandle

from .views import FastStreamSubscriber, HandlerView

if TYPE_CHECKING:
    from faststream import FastStream


@dataclass(frozen=True)
class SubscriberModel:
    """A subscriber's handler plus the payload model it declares."""

    handler: Any
    model: ModelHandle
    topics: tuple[str, ...]

    @property
    def input_model(self) -> ModelHandle:
        """The declared payload model, matching :class:`SubscriberPort`."""
        return self.model


class SubscriberWalker:
    """Walk a broker's subscribers, yielding those with a versioned payload model."""

    def __init__(self, manager: Manager) -> None:
        self._manager = manager

    @staticmethod
    def declared_model(handler: Any) -> ModelHandle | None:
        """Return the handler's first class-typed parameter annotation."""
        return HandlerView(handler).input_model

    def walk(self, broker: Any) -> Iterator[SubscriberModel]:
        for raw in broker.subscribers:
            subscriber = FastStreamSubscriber(raw)
            model = subscriber.input_model
            handler = subscriber.handler
            if handler is None or model is None:
                continue
            if not self._manager.identifies(model):
                continue
            yield SubscriberModel(
                handler=handler,
                model=model,
                topics=subscriber.topics,
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
