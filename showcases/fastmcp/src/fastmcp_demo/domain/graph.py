"""The demo version graph — the domain layer.

Defines the versioned kind the demo exposes and builds a fully registered
``Manager`` from it: the anchor model plus every migration edge (forward and
reverse), authored as Python callables. The anchor is the Pydantic model in
:mod:`fastmcp_demo.domain.models`; older versions are reconstructed from it. No
FastMCP, no OpenTelemetry.
"""

from __future__ import annotations

import semver

from pyverge import Manager
from pyverge.migration import MigrationSettings, PydanticModelAdapter
from pyverge.types import ManagerMigrationKey

from ..settings import GraphSettings
from . import migrations
from .models import SearchWeather

V1, V2, V3 = "1.0.0", "2.0.0", "3.0.0"
ALL_VERSIONS = (V1, V2, V3)
ANCHOR_VERSION = V3

#: The anchor model — the newest version's source of truth.
ANCHOR_MODEL = SearchWeather

#: Migration edges, newest first: forward edges so the engine reconstructs each
#: older endpoint from the already-materialized newer one, then the reverse
#: edges. Each is a plain ``(dict) -> dict`` callable.
EDGES: tuple[tuple[str, str, migrations.Migration], ...] = (
    (V2, V3, migrations.add_wind),
    (V1, V2, migrations.add_humidity),
    (V3, V2, migrations.drop_wind),
    (V2, V1, migrations.drop_humidity),
)


def build_manager(graph: GraphSettings) -> Manager[semver.Version]:
    """Return a ``Manager`` with the whole version graph registered.

    The graph is one bounded context: the tool's kind and every kind it
    contains live in a single manager. Only the anchor model is registered
    concretely; ``on_missing="reconstruct_model"`` rebuilds the older endpoints
    from the anchor as each forward edge is registered.
    """
    ToolManager = Manager[semver.Version].configure(
        MigrationSettings(direction="any", on_missing="reconstruct_model"),
        PydanticModelAdapter(
            version_property=graph.version_property,
            kind_property=graph.kind_property,
        ),
    )
    manager = ToolManager()  # ty: ignore[invalid-argument-type]
    manager.store_model(ANCHOR_MODEL)  # ty: ignore[invalid-argument-type]

    for source, target, func in EDGES:
        manager.store_migration(
            ManagerMigrationKey(graph.kind, source, target),
            func,
        )
    return manager
