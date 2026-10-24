"""Build discovery and manager source reflection."""

from __future__ import annotations

import pytest

from pyverge import Manager
from pyverge.discovery import RegistrationContext
from pyverge.manager.types import Reflectable
from pyverge.registry.errors import GraphLockedError
from pyverge.sources import SourceDescriptor
from pyverge.versioning import EdgeKey
from tests.examples.pydantic.semver import UserV1, UserV2, migrate_v1_to_v2
from tests.utils.source import StaticSource


@pytest.mark.parametrize(
    "source, expected_models, expected_migrations",
    [
        pytest.param(
            (
                [
                    SourceDescriptor("model", UserV1, "test", {}),
                    SourceDescriptor("model", UserV2, "test", {}),
                    SourceDescriptor(
                        "migration",
                        ((UserV1, UserV2), migrate_v1_to_v2),
                        "test",
                        {},
                    ),
                ],
                "test",
            ),
            len((UserV1, UserV2)),
            1,
            id="models-and-migration",
        ),
        pytest.param(
            ([SourceDescriptor("model", UserV1, "test", {})], "test"),
            1,
            0,
            id="single-model",
        ),
    ],
    indirect=["source"],
)
def test_reflect_registers(
    manager: type[Manager],
    source: StaticSource,
    expected_models: int,
    expected_migrations: int,
) -> None:
    report = manager.reflect(source)

    assert report.registered_models == expected_models
    assert report.registered_migrations == expected_migrations
    assert len(manager._default_engine.registry.versions) == expected_models


@pytest.mark.parametrize(
    "source",
    [
        (
            [
                SourceDescriptor("model", UserV1, "test", {}),
                SourceDescriptor("model", UserV2, "test", {}),
                SourceDescriptor(
                    "migration",
                    ((UserV1, UserV2), migrate_v1_to_v2),
                    "test",
                    {},
                ),
            ],
            "test",
        )
    ],
    indirect=["source"],
)
def test_reflect_registers_migration_edge(
    manager: type[Manager],
    source: StaticSource,
) -> None:
    engine = manager._default_engine
    manager.reflect(source)

    edge = EdgeKey.from_pair(
        engine.get_model(engine.adapter.version_key(kind="User", version="1.0.0")),
        engine.get_model(engine.adapter.version_key(kind="User", version="2.0.0")),
    )
    assert engine.registry.has_migration(edge)


@pytest.mark.parametrize(
    "source",
    [([SourceDescriptor("unknown", None, "test", {})], "test")],
    indirect=["source"],
)
def test_reflect_skips_unknown_strategy(
    manager: type[Manager], source: StaticSource
) -> None:
    report = manager.reflect(source)

    assert report.descriptors == 0
    assert report.skipped == ("unknown",)


@pytest.mark.parametrize("source", [([], "test")], indirect=["source"])
def test_reflect_after_instance_raises(
    manager: type[Manager],
    source: StaticSource,
) -> None:
    manager()

    with pytest.raises(GraphLockedError, match="locked"):
        manager.reflect(source)


def test_manager_is_reflectable(manager: type[Manager]) -> None:
    assert isinstance(manager, Reflectable)


def test_registration_context_requires_validation_flag() -> None:
    with pytest.raises(TypeError):
        RegistrationContext(source_id="test", logger=None, clock=None)  # ty: ignore[missing-argument, invalid-argument-type]
