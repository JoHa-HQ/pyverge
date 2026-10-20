from __future__ import annotations

from typing import Any

#: The versioned input channels the handler consumes.
ORDER_TOPICS: tuple[str, ...] = ("orders.v1", "orders.v2")

#: Microcks destinations: <API>-<version>-<channel>.
MICROCKS_TOPICS: tuple[str, ...] = tuple(
    f"Orders-2.0.0-{topic}" for topic in ORDER_TOPICS
)

#: Route destinations and their target versions.
LEGACY_TOPIC = "orders.legacy"
LEGACY_TARGET = "1.0.0"
CURRENT_TOPIC = "orders.current"
CURRENT_TARGET = "2.0.0"


async def handle_order(event: dict[str, Any]) -> dict[str, Any]:
    """Return the event's converged body; the publisher routes it by version."""
    return event.get("data", event)
