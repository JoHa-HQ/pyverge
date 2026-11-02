"""The Order feature: components plus routing inside its handler.

``wire`` registers the feature's models, migrations, and subscriber on the shared
manager instance and the broker. The app assembly calls it after instantiating
the manager.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pyverge import Manager
from pyverge.adapters.faststream import PyvergeBroker
from pyverge.types import ManagerMigrationKey, TargetPolicy

from .domain import Order, add_currency, drop_currency
from .handlers import (
    CURRENT_TARGET,
    CURRENT_TOPIC,
    LEGACY_TARGET,
    LEGACY_TOPIC,
    ORDER_TOPICS,
    handle_order,
)


@dataclass(frozen=True)
class OrdersFeature:
    """The Order feature: consume the input topics and route by version."""

    topics: Sequence[str] = ORDER_TOPICS
    target: TargetPolicy = "latest"
    version_header: str | None = "accept-version"

    def wire(self, broker: PyvergeBroker) -> None:
        """Register the Order graph and the routing handler."""
        manager: Manager = broker.manager
        manager.store_model(Order)
        manager.store_migration(
            ManagerMigrationKey("Order", "1.0.0", "2.0.0"), add_currency
        )
        manager.store_migration(
            ManagerMigrationKey("Order", "2.0.0", "1.0.0"), drop_currency
        )
        routed = broker.publish_to(
            routes={
                LEGACY_TOPIC: LEGACY_TARGET,
                CURRENT_TOPIC: CURRENT_TARGET,
            },
        )(handle_order)
        broker.subscriber(
            *self.topics,
            target=self.target,
            header=self.version_header,
        )(routed)


__all__ = ["OrdersFeature"]
