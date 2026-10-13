"""Tests for reconstruction strategies and the reflection orchestrator.

The strategy owns the artifact a diff materializes — a rebuilt model or a
proposed migration spec — and the engine dispatches to it by settings (explicit)
or the diff's origin (fallback).
"""

from __future__ import annotations

import pytest
import semver

from pyverge import types
from pyverge.core import MigrationSettings
from pyverge.migration import JsonPatchMigration, PydanticModelAdapter
from pyverge.reflection import (
    CompositeDiffDiscovery,
    MigrationReflection,
    ModelReflection,
    ReconstructionStrategy,
    Reflection,
    strategy_for,
)
from tests.examples.pydantic.semver import UserV1, UserV2
from tests.utils import envelope_model


def _adapter() -> PydanticModelAdapter:
    return PydanticModelAdapter()


def _add_age():
    """A JSON Patch migration that writes ``age`` into the payload."""
    return JsonPatchMigration(
        {
            "from": "1.0.0",
            "to": "2.0.0",
            "ops": [{"op": "add", "path": "/age", "value": None}],
        }
    ).patch


@pytest.fixture
def versions():
    adapter = _adapter()
    v1 = envelope_model(adapter, MigrationSettings(), UserV1)
    v2 = envelope_model(adapter, MigrationSettings(), UserV2)
    return adapter, v1, v2


class TestStrategySelection:
    def test_reconstruct_model_setting(self) -> None:
        assert isinstance(
            strategy_for("reconstruct_model", adapter=_adapter()), ModelReflection
        )

    def test_reconstruct_migration_setting(self) -> None:
        assert isinstance(
            strategy_for("reconstruct_migration", adapter=_adapter()),
            MigrationReflection,
        )

    @pytest.mark.parametrize("on_missing", ["raise", "skip"])
    def test_no_strategy_for_raise_or_skip(self, on_missing: str) -> None:
        assert strategy_for(on_missing, adapter=_adapter()) is None

    def test_strategies_satisfy_protocol(self) -> None:
        assert isinstance(ModelReflection(_adapter()), ReconstructionStrategy)
        assert isinstance(MigrationReflection(_adapter()), ReconstructionStrategy)


class TestReflectionDiffStep:
    def test_migration_origin(self, versions) -> None:
        adapter, v1, v2 = versions
        reflection = Reflection(adapter, CompositeDiffDiscovery())
        diff = reflection.diff(v2, v1, migration=_add_age())
        assert diff.origin == "migration"

    def test_schema_origin(self, versions) -> None:
        adapter, v1, v2 = versions
        reflection = Reflection(adapter, CompositeDiffDiscovery())
        assert reflection.diff(v1, v2).origin == "schema"

    def test_explicit_setting_wins_over_origin(self, versions) -> None:
        adapter, v1, v2 = versions
        reflection = Reflection(
            adapter, CompositeDiffDiscovery(), on_missing="reconstruct_migration"
        )
        schema_diff = reflection.diff(v1, v2)
        assert isinstance(reflection.strategy(schema_diff), MigrationReflection)

    def test_origin_breaks_tie_when_setting_is_raise(self, versions) -> None:
        adapter, v1, v2 = versions
        reflection = Reflection(adapter, CompositeDiffDiscovery(), on_missing="raise")
        migration_diff = reflection.diff(v2, v1, migration=_add_age())
        assert isinstance(reflection.strategy(migration_diff), ModelReflection)
        schema_diff = reflection.diff(v1, v2)
        assert isinstance(reflection.strategy(schema_diff), MigrationReflection)


class TestModelReflection:
    def test_reconstructs_model_from_diff(self, versions) -> None:
        adapter, v1, v2 = versions
        reflection = Reflection(adapter, CompositeDiffDiscovery())
        outcome = reflection.reflect(
            v2, v1, migration=_add_age(), strategy=ModelReflection(adapter)
        )
        assert outcome.model is not None
        assert outcome.model.model is not None
        assert "age" not in outcome.model.model.model_fields

    def test_outcome_carries_only_model(self, versions) -> None:
        adapter, v1, v2 = versions
        reflection = Reflection(adapter, CompositeDiffDiscovery())
        outcome = reflection.reflect(
            v2, v1, migration=_add_age(), strategy=ModelReflection(adapter)
        )
        assert outcome.migration is None


class TestMigrationReflection:
    def test_proposes_spec_from_diff(self, versions) -> None:
        adapter, v1, v2 = versions
        reflection = Reflection(adapter, CompositeDiffDiscovery())
        outcome = reflection.reflect(v1, v2, strategy=MigrationReflection(adapter))
        assert isinstance(outcome.migration, JsonPatchMigration)
        assert outcome.migration.spec["from"] == "1.0.0"
        assert outcome.migration.spec["to"] == "2.0.0"
        assert outcome.model is None


_ = (types, semver.Version)
