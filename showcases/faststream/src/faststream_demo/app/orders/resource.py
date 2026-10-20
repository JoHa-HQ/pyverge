"""The Order feature: components plus routing inside its handler.

``wire`` registers the feature's models, migrations, and subscriber on the shared
manager instance and the broker. The app assembly calls it after instantiating
the manager.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pyverge import Manager
from pyverge.adapters.faststream import subscriber
from pyverge.types import ManagerMigrationKey, TargetPolicy

from .domain import Order, add_currency, drop_currency
from .handlers import ORDER_TOPICS, handle_order


@dataclass(frozen=True)
class OrdersFeature:
    """The Order feature: consume the input topics and route by version."""

    topics: Sequence[str] = ORDER_TOPICS
    target: TargetPolicy = "latest"

    def wire(self, broker: object, manager: Manager) -> None:
        """Register the Order graph and the routing handler."""
        manager.store_model(Order)
        manager.store_migration(
            ManagerMigrationKey("Order", "1.0.0", "2.0.0"), add_currency
        )
        manager.store_migration(
            ManagerMigrationKey("Order", "2.0.0", "1.0.0"), drop_currency
        )
        subscriber(broker, *self.topics, manager=manager, target=self.target)(
            handle_order
        )


__all__ = ["OrdersFeature"]
