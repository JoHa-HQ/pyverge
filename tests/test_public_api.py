"""Top-level public API exports."""

from __future__ import annotations

from pyverge import Engine, Manager
from pyverge.discovery import (
    MigrationSpec,
    ModelRegistrationMode,
    RegisterMigration,
    RegisterModel,
    RegistrationCollector,
)
from pyverge.engine import Engine as EngineFromModule


def test_top_level_engine_export() -> None:
    assert Engine is EngineFromModule
    assert Manager.__name__ == "Manager"


def test_discovery_command_exports() -> None:
    assert ModelRegistrationMode.STRICT.value == "strict"
    assert ModelRegistrationMode.RECONCILE.value == "reconcile"
    assert RegisterModel.__name__ == "RegisterModel"
    assert RegisterMigration.__name__ == "RegisterMigration"
    assert MigrationSpec.__name__ == "MigrationSpec"
    assert RegistrationCollector.__name__ == "RegistrationCollector"
