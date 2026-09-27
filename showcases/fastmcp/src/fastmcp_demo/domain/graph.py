"""The demo version graph — the domain layer.

Defines the versioned kind the demo exposes and builds a fully registered
``Manager`` from it: the anchor model plus every migration edge (forward and
reverse). The anchor schema is the source of truth in ``weather.json``; older
versions are reconstructed from it. No FastMCP, no OpenTelemetry.
"""

from __future__ import annotations

import json
from pathlib import Path

import semver

from pyverge import Manager
from pyverge.migration import (
    JsonPatchMigration,
    JsonSchemaModelAdapter,
    MigrationSettings,
)
from pyverge.types import ManagerMigrationKey

from ..settings import GraphSettings

V1, V2, V3 = "1.0.0", "2.0.0", "3.0.0"
ALL_VERSIONS = (V1, V2, V3)
ANCHOR_VERSION = V3

#: The anchor schema document — the newest model's source of truth.
ANCHOR_SCHEMA_PATH = Path(__file__).resolve().parent / "weather.json"


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


def _spec_name(kind: str, source: str, target: str) -> str:
    stem = lambda v: v.replace(".", "")  # noqa: E731
    return f"{kind.replace('.', '_')}_{stem(source)}_{stem(target)}.json"


def migration_files(graph: GraphSettings) -> list[Path]:
    """Return the migration spec files present for the graph, newest edge first.

    Edges are registered newest-first so the engine reconstructs each older
    endpoint from the already-materialized newer one. Reverse edges (if
    present) are registered last.
    """
    edges = [(V2, V3), (V1, V2), (V3, V2), (V2, V1)]
    paths = [graph.migrations_dir / _spec_name(graph.kind, a, b) for a, b in edges]
    return [path for path in paths if path.exists()]


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

    for path in migration_files(graph):
        spec = json.loads(path.read_text())
        manager.store_migration(
            ManagerMigrationKey(graph.kind, spec["from"], spec["to"]),
            JsonPatchMigration(spec).patch,
        )
    return manager
