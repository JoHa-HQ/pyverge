from __future__ import annotations

from typing import Annotated, Any

from faststream import Context

from pyverge import Manager

#: The versioned input channels the handler consumes.
ORDER_TOPICS: tuple[str, ...] = ("orders.v1", "orders.v2")

#: Route destinations and their target versions.
LEGACY_TOPIC = "orders.legacy"
LEGACY_TARGET = "1.0.0"
CURRENT_TOPIC = "orders.current"
CURRENT_TARGET = "2.0.0"


async def handle_order(
    event: dict[str, Any],
    manager: Annotated[Manager, Context("manager")],
    broker: Annotated[Any, Context("broker")],
) -> None:
    """Converge the event, then route it to each destination's version."""
    data = event.get("data", event)
    await broker.publish(manager.migrate(data, target=LEGACY_TARGET), LEGACY_TOPIC)
    await broker.publish(manager.migrate(data, target=CURRENT_TARGET), CURRENT_TOPIC)
