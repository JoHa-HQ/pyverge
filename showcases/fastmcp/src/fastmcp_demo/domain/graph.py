"""The demo version graph — the domain layer.

Defines the versioned kinds the demo exposes and builds a fully registered
``Manager`` from them: an anchor model per kind plus every migration edge
(forward and reverse), authored as Python callables. Each anchor is the Pydantic
model in :mod:`fastmcp_demo.domain.models`; older versions are reconstructed
from it. No FastMCP, no OpenTelemetry.

Three kinds — one per FastMCP primitive type — so every reflection provider
(tool, prompt, resource) has a physical anchor, plus the nested ``coordinates``
kind the tool embeds::

    search_weather    tool     v1 -> v2 (+humidity) -> v3 (+wind) -> v4 (+coordinates)
    coordinates       nested   v1 (latitude, longitude)
    weather_briefing  prompt   v1 -> v2 (+style)
    weather_reading   resource v1 -> v2 (+units)
"""

from __future__ import annotations

import semver

from pyverge import Manager
from pyverge.migration import MigrationSettings, PydanticModelAdapter
from pyverge.types import ManagerMigrationKey

from ..settings import GraphSettings
from . import migrations
from .models import Coordinates, SearchWeather, WeatherBriefing, WeatherReading

V1, V2, V3, V4 = "1.0.0", "2.0.0", "3.0.0", "4.0.0"

#: Versions of the versioned tool.
ALL_VERSIONS = (V1, V2, V3, V4)
ANCHOR_VERSION = V4

#: The tool's anchor model — the newest version's source of truth.
ANCHOR_MODEL = SearchWeather

#: Anchor models per kind (registered concretely; older endpoints reconstructed).
ANCHOR_MODELS = (SearchWeather, Coordinates, WeatherBriefing, WeatherReading)

#: Migration edges, newest first: forward edges so the engine reconstructs each
#: older endpoint from the already-materialized newer one, then the reverse
#: edges. Each is a plain ``(dict) -> dict`` callable.
EDGES: tuple[tuple[str, str, str, migrations.Migration], ...] = (
    ("search_weather", V3, V4, migrations.add_coordinates),
    ("search_weather", V2, V3, migrations.add_wind),
    ("search_weather", V1, V2, migrations.add_humidity),
    ("search_weather", V4, V3, migrations.drop_coordinates),
    ("search_weather", V3, V2, migrations.drop_wind),
    ("search_weather", V2, V1, migrations.drop_humidity),
    ("weather_briefing", V1, V2, migrations.add_style),
    ("weather_briefing", V2, V1, migrations.drop_style),
    ("weather_reading", V1, V2, migrations.add_units),
    ("weather_reading", V2, V1, migrations.drop_units),
)


def build_manager(graph: GraphSettings) -> Manager[semver.Version]:
    """Return a ``Manager`` with the whole version graph registered.

    The graph is one bounded context: every versioned kind lives in a single
    manager. Only the anchor models are registered concretely;
    ``on_missing="reconstruct_model"`` rebuilds the older endpoints from each
    anchor as the forward edge is registered.
    """
    ToolManager = Manager[semver.Version].configure(
        MigrationSettings(direction="any", on_missing="reconstruct_model"),
        PydanticModelAdapter(
            version_property=graph.version_property,
            kind_property=graph.kind_property,
        ),
    )
    manager = ToolManager()  # ty: ignore[invalid-argument-type]
    for anchor in ANCHOR_MODELS:
        manager.store_model(anchor)  # ty: ignore[invalid-argument-type]

    for kind, source, target, func in EDGES:
        manager.store_migration(
            ManagerMigrationKey(kind, source, target),
            func,
        )
    return manager
