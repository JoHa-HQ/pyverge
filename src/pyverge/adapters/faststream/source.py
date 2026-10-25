"""FastStream SourcePort adapter."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any, Protocol

from pyverge.discovery import ModelDescriptor, SourceDescriptor, SourceVisitor
from pyverge.schemas.types import ModelAdapter

from .views import FastStreamSubscriber, HandlerView


class FastStreamProvider(Protocol):
    """Yield descriptors from one FastStream source family."""

    def descriptors(self, broker: Any) -> Iterator[SourceDescriptor]: ...


class SubscriberProvider:
    """Yield subscriber payload models."""

    def __init__(self, adapter: ModelAdapter | None = None) -> None:
        self._adapter = adapter

    def descriptors(self, broker: Any) -> Iterator[SourceDescriptor]:
        for raw in broker.subscribers:
            subscriber = FastStreamSubscriber(raw)
            model = subscriber.input_model
            if model is None:
                continue
            if self._adapter is not None and not self._adapter.identify(model):
                continue
            yield ModelDescriptor(
                model,
                "faststream",
                {"topics": subscriber.topics, "role": "subscriber"},
            )


class PublisherProvider:
    """Yield publisher return models from registered publisher calls."""

    def __init__(self, adapter: ModelAdapter | None = None) -> None:
        self._adapter = adapter

    def descriptors(self, broker: Any) -> Iterator[SourceDescriptor]:
        for publisher in broker.publishers:
            topics = tuple(
                getattr(topic, "name", None) or str(topic)
                for topic in getattr(publisher, "topics", ())
            )
            for call in publisher.specification.calls:
                model = HandlerView(call).return_model
                if model is None:
                    continue
                if self._adapter is not None and not self._adapter.identify(model):
                    continue
                yield ModelDescriptor(
                    model,
                    "faststream",
                    {"topics": topics, "role": "publisher"},
                )


class FastStreamSource:
    """Expose FastStream subscriber and publisher models as descriptors."""

    def __init__(
        self,
        app: Any,
        *,
        adapter: ModelAdapter | None = None,
        providers: Sequence[FastStreamProvider] | None = None,
    ) -> None:
        if providers is None:
            if adapter is None:
                raise ValueError(
                    "FastStreamSource requires adapter or explicit providers"
                )
            providers = (
                SubscriberProvider(adapter),
                PublisherProvider(adapter),
            )
        self._app = app
        self._providers = tuple(providers)

    def accept(self, visitor: SourceVisitor) -> None:
        for broker in getattr(self._app, "brokers", ()):
            for provider in self._providers:
                for descriptor in provider.descriptors(broker):
                    visitor.visit(descriptor)


__all__ = [
    "FastStreamProvider",
    "FastStreamSource",
    "PublisherProvider",
    "SubscriberProvider",
]
