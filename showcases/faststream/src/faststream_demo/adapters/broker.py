"""FastStream broker adapter.

Builds a broker and the ``FastStream`` app, wiring the pyverge convergence seams
to the domain manager. This is the only module that imports FastStream.

The broker is chosen from settings by name and constructed with FastStream's own
broker classes — no pyverge abstraction sits over brokers; the adapter stays
broker-agnostic. The same domain graph and the same seams are used whichever
broker runs, which is the demo's point.

Two seams, both from ``pyverge.adapters.faststream``:

* :func:`subscriber` — per-endpoint convergence via the subscriber ``decoder``;
  the handler's typed parameter names the kind and is bound to the served version.
* :class:`Reflector` — on-startup reflection of each handler's payload model into
  the manager graph, before consumption begins.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

from faststream import FastStream

from pyverge import Manager
from pyverge.adapters.faststream import Reflector, subscriber

from ..domain.models import Order
from ..settings import BrokerSettings


def _kafka(url: str) -> Any:
    from faststream.kafka import KafkaBroker  # noqa: PLC0415

    return KafkaBroker(url)


def _rabbitmq(url: str) -> Any:
    from faststream.rabbit import RabbitBroker  # noqa: PLC0415

    return RabbitBroker(url)


def _nats(url: str) -> Any:
    from faststream.nats import NatsBroker  # noqa: PLC0415

    return NatsBroker(url)


def _redis(url: str) -> Any:
    from faststream.redis import RedisBroker  # noqa: PLC0415

    return RedisBroker(url)


#: Broker name -> FastStream broker constructor.
BROKERS: dict[str, Callable[[str], Any]] = {
    "kafka": _kafka,
    "rabbitmq": _rabbitmq,
    "nats": _nats,
    "redis": _redis,
}


def build_broker(settings: BrokerSettings) -> Any:
    """Return the FastStream broker named by *settings*."""
    try:
        factory = BROKERS[settings.name]
    except KeyError:
        raise ValueError(
            f"Unknown broker {settings.name!r}; expected one of "
            f"{', '.join(sorted(BROKERS))}"
        ) from None
    return factory(settings.url)


#: Broker name -> (module, class) of FastStream's telemetry middleware.
_TELEMETRY: dict[str, tuple[str, str]] = {
    "kafka": ("faststream.kafka.opentelemetry", "KafkaTelemetryMiddleware"),
    "rabbitmq": ("faststream.rabbit.opentelemetry", "RabbitTelemetryMiddleware"),
    "nats": ("faststream.nats.opentelemetry", "NatsTelemetryMiddleware"),
    "redis": ("faststream.redis.opentelemetry", "RedisTelemetryMiddleware"),
}


def _telemetry_middleware(name: str, provider: Any) -> Any:
    """Return FastStream's telemetry middleware for *name*, or ``None``."""
    entry = _TELEMETRY.get(name)
    if provider is None or entry is None:
        return None
    module_name, class_name = entry
    middleware = getattr(importlib.import_module(module_name), class_name)
    return middleware(tracer_provider=provider)


def build_app(
    manager: Manager,
    settings: BrokerSettings,
    provider: Any = None,
    *,
    topic: str = "orders",
) -> FastStream:
    """Return a ``FastStream`` app whose handler sees converged payloads.

    The broker is built from *settings*; when *provider* is given, FastStream's
    telemetry middleware is attached so each consume opens a parent span (the
    migration hooks nest under it).
    """
    broker = build_broker(settings)
    middleware = _telemetry_middleware(settings.name, provider)
    if middleware is not None:
        broker.add_middleware(middleware)

    @subscriber(broker, topic, manager=manager, target=settings.target)
    async def handle_order(order: Order) -> None:
        """Business logic — always receives the target-version payload."""
        print("order", order)

    return FastStream(broker, on_startup=[Reflector(manager)])


__all__ = ["BROKERS", "build_app", "build_broker"]
