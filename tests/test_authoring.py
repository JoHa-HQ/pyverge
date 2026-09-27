"""Tests for reconstruction authoring.

``MigrationSettings.on_missing`` is one authoritative enum — the two
reconstruction strategies are inherently exclusive:
- ``"reconstruct_model"`` — rebuild a missing endpoint model from the anchor
  and the migration diffs,
- ``"reconstruct_migration"`` — propose a version-edge migration from two
  schemas (``Engine.propose_migration``); model reconstruction is disabled.
"""

from __future__ import annotations

import pytest
import semver
from pydantic import ValidationError

from pyverge import Manager
from pyverge.core import (
    MigrationSettings,
    ModelNotFoundError,
    VersioningSettings,
    VersionNode,
)
from pyverge.migration import (
    JsonPatchMigration,
    PydanticModelAdapter,
)
from tests.examples.pydantic.semver import UserV1, UserV2
from tests.utils import envelope_model, meta_versionable


def _engine(
    settings: MigrationSettings,
    adapter: PydanticModelAdapter,
):
    UserManager = Manager[semver.Version].configure(settings, adapter)
    return UserManager()


class TestOnMissingSingleEnum:
    def test_default_is_raise(self) -> None:
        assert MigrationSettings().on_missing == "raise"

    def test_accepts_reconstruct_model(self) -> None:
        settings = MigrationSettings(on_missing="reconstruct_model")
        assert settings.on_missing == "reconstruct_model"

    def test_accepts_reconstruct_migration(self) -> None:
        settings = MigrationSettings(on_missing="reconstruct_migration")
        assert settings.on_missing == "reconstruct_migration"

    def test_rejects_unknown_value(self) -> None:
        with pytest.raises(ValidationError):
            MigrationSettings(on_missing="both")  # ty: ignore[invalid-argument-type]


class TestReconstructModel:
    def test_reconstructs_missing_model_on_store_migration(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        manager = _engine(
            MigrationSettings(on_missing="reconstruct_model"),
            model_adapter,
        )
        real = envelope_model(model_adapter, versioning_settings, UserV2)
        manager.engine.store_model(real)
        meta = meta_versionable(model_adapter, "User", "1.0.0")

        manager.engine.store_migration(
            (meta, real),
            JsonPatchMigration(
                {
                    "from": "1.0.0",
                    "to": "2.0.0",
                    "ops": [{"op": "add", "path": "/age", "value": None}],
                }
            ).patch,
        )
        reconstructed = manager.engine.get_model(meta)
        assert reconstructed.model is not None
        assert "age" not in reconstructed.model.model_fields


class TestProposeMigration:
    @pytest.fixture
    def engine(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ):
        manager = _engine(
            MigrationSettings(on_missing="reconstruct_migration"),
            model_adapter,
        )
        eng = manager.engine
        anchor = envelope_model(model_adapter, versioning_settings, UserV1)
        target = envelope_model(model_adapter, versioning_settings, UserV2)
        eng.store_model(anchor)
        eng.store_model(target)
        return eng, anchor, target

    def test_proposes_migration_from_schema_diff(self, engine) -> None:
        eng, anchor, target = engine
        migration = eng.propose_migration(anchor, target)
        assert isinstance(migration, JsonPatchMigration)
        assert migration.spec["from"] == "1.0.0"
        assert migration.spec["to"] == "2.0.0"
        assert migration.spec["ops"]
        assert {"op": "add", "path": "/age", "value": None} in migration.spec["ops"]

    def test_proposal_does_not_auto_register(self, engine) -> None:
        eng, anchor, target = engine
        eng.propose_migration(anchor, target)
        # Nothing was auto-registered with the registry.
        assert eng.registry.migrations_of(anchor.kind) == frozenset()

    def test_proposal_rejects_missing_model(self, engine) -> None:
        eng, anchor, _target = engine
        virtual = VersionNode(
            _model=None,
            _value=anchor.version[1],
            _kind=anchor.kind,
        )
        with pytest.raises(ModelNotFoundError):
            eng.propose_migration(anchor, virtual)
