"""The demo version graph — the domain layer.

Defines the versioned kind the demo exposes and builds a fully registered
``Manager`` from it: the anchor model plus the migration edge, authored as a
Python callable. The anchor is the Pydantic model in
:mod:`faststream_demo.domain.models`; the older version is reconstructed from
it. No FastStream.

    Order  v1 -> v2 (+currency)
"""

from __future__ import annotations

import semver

from pyverge import Manager
from pyverge.migration import MigrationSettings, PydanticModelAdapter
from pyverge.types import ManagerMigrationKey

from . import migrations
from .models import Order

V1, V2 = "1.0.0", "2.0.0"

#: Versions of the versioned kind.
ALL_VERSIONS = (V1, V2)
ANCHOR_VERSION = V2

#: The kind's anchor model — the newest version's source of truth.
ANCHOR_MODEL = Order

#: Migration edges: the forward edge so the engine reconstructs the older
#: endpoint from the already-materialized newer one.
EDGES: tuple[tuple[str, str, str, migrations.Migration], ...] = (
    ("Order", V1, V2, migrations.add_currency),
    ("Order", V2, V1, migrations.drop_currency),
)


def build_manager() -> Manager[semver.Version]:
    """Return a ``Manager`` with the whole version graph registered.

    The graph is one schema registry (a reference-closed set of kinds). Only the
    anchor model is registered concretely; ``on_missing="reconstruct_model"``
    rebuilds the older endpoint from the anchor as the forward edge is registered.
    """
    OrderManager = Manager[semver.Version].configure(
        MigrationSettings(direction="any", on_missing="reconstruct_model"),
        PydanticModelAdapter(),
    )
    manager = OrderManager()  # ty: ignore[invalid-argument-type]
    manager.store_model(ANCHOR_MODEL)  # ty: ignore[invalid-argument-type]

    for kind, source, target, func in EDGES:
        manager.store_migration(
            ManagerMigrationKey(kind, source, target),
            func,
        )
    return manager
