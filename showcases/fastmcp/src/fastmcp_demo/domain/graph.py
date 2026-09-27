"""The demo version graph — the domain layer.

Defines the versioned kind the demo exposes and builds a fully registered
``Manager`` from it: the anchor model plus every migration edge (forward and
reverse), authored as Python callables. The anchor schema is the source of
truth in ``weather.json``; older versions are reconstructed from it. No FastMCP,
no OpenTelemetry.
"""

from __future__ import annotations

import json
from pathlib import Path

import semver

from pyverge import Manager
from pyverge.migration import JsonSchemaModelAdapter, MigrationSettings
from pyverge.types import ManagerMigrationKey

from ..settings import GraphSettings
from . import migrations

V1, V2, V3 = "1.0.0", "2.0.0", "3.0.0"
ALL_VERSIONS = (V1, V2, V3)
ANCHOR_VERSION = V3

#: The anchor schema document — the newest model's source of truth.
ANCHOR_SCHEMA_PATH = Path(__file__).resolve().parent / "weather.json"

#: Migration edges, newest first: forward edges so the engine reconstructs each
#: older endpoint from the already-materialized newer one, then the reverse
#: edges. Each is a plain ``(dict) -> dict`` callable.
EDGES: tuple[tuple[str, str, migrations.Migration], ...] = (
    (V2, V3, migrations.add_wind),
    (V1, V2, migrations.add_humidity),
    (V3, V2, migrations.drop_wind),
    (V2, V1, migrations.drop_humidity),
)


def schema(kind: str, version: str, extra: dict) -> dict:
    """Build a JSON Schema document for *kind*@*version*.

    Identity fields (``kind``/``version``) get string defaults so the adapter
    can read them back, mirroring a registered raw model.
    """
    properties: dict = {
        "kind": {"type": "string", "default": kind},
        "version": {"type": "string", "default": version},
        "city": {"type": "string"},
        "units": {"type": "string", "default": "celsius"},
    }
    properties.update(extra)
    return {
        "kind": kind,
        "version": version,
        "type": "object",
        "properties": properties,
        "required": ["city"],
    }


def anchor_schema() -> dict:
    """Return the anchor schema document loaded from ``weather.json``."""
    return json.loads(ANCHOR_SCHEMA_PATH.read_text())


def build_manager(graph: GraphSettings) -> Manager[semver.Version]:
    """Return a ``Manager`` with the whole version graph registered.

    The graph is one bounded context: the tool's kind and every kind it
    contains live in a single manager. Only the anchor model is registered
    concretely; ``on_missing="reconstruct_model"`` rebuilds the older endpoints
    from the anchor as each forward edge is registered.
    """
    ToolManager = Manager[semver.Version].configure(
        MigrationSettings(direction="any", on_missing="reconstruct_model"),
        JsonSchemaModelAdapter(
            version_property=graph.version_property,
            kind_property=graph.kind_property,
        ),
    )
    manager = ToolManager()  # ty: ignore[invalid-argument-type]
    manager.store_model(anchor_schema())  # ty: ignore[invalid-argument-type]

    for source, target, func in EDGES:
        manager.store_migration(
            ManagerMigrationKey(graph.kind, source, target),
            func,
        )
    return manager
