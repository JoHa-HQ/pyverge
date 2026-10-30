from __future__ import annotations

from typing import Any

import pytest

from pyverge.execution.migrations import MigrationBindings
from pyverge.graph import AnyDirection, PathFinder, PolicyEngine, TargetCompiler
from tests.utils import envelope_model


@pytest.fixture
def graph(engine):
    return engine.snapshot


@pytest.fixture
def nodes(request, model_adapter, versioning_settings):
    models = getattr(request, "param", ())
    return tuple(
        envelope_model(model_adapter, versioning_settings, model) for model in models
    )


@pytest.fixture
def path_finder(request, engine, graph, model_adapter) -> PathFinder:
    options: dict[str, Any] = getattr(request, "param", {})
    snapshot = graph()
    return PathFinder(
        graph=snapshot,
        targets=TargetCompiler(snapshot, model_adapter),
        migrations=MigrationBindings.from_catalog(engine.registry),
        policy=PolicyEngine(
            direction=options.get("direction", AnyDirection()),
            on_direction_violation=options.get("on_direction_violation", "raise"),
            on_missing_path=options.get("on_missing_path", "raise"),
            depth_limit=options.get("depth_limit", -1),
            on_depth_violation=options.get("on_depth_violation", "raise"),
        ),
    )
