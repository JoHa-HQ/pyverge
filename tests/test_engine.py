from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pendulum
import pytest
import semver
from pydantic import BaseModel

from pyverge.migration import (
    CompoundKeyWalker,
    DiscoverySettings,
    Engine,
    EntryMigration,
    GraphBuilder,
    MigrationAlreadyRegisteredError,
    MigrationHook,
    MigrationNotFoundError,
    MigrationSettings,
    ModelAlreadyRegisteredError,
    ModelNotFoundError,
    PydanticModelAdapter,
    Registry,
    RegistryError,
    SentinelEdge,
    SentinelNode,
    SequentialExecutor,
    VersioningSettings,
    VersionNode,
    latest_target_resolver,
    types,
)
from tests.examples.pydantic.chrono import (
    UserV20250310,
    UserV20251231,
    UserV20260228,
)
from tests.examples.pydantic.semver import (
    UserV1,
    UserV2,
    UserV3,
)
from tests.examples.pydantic.semver_nested import AddressV1
from tests.utils import edge_from_models, envelope_model, make_engine

# Alias for compatibility with existing test references
ModelVersion = VersionNode
SequentialWalker = CompoundKeyWalker


class TestModelManagement:
    """Engine-level CRUD for model versions.

    Engine policy = key normalization (``(kind, value)`` tuple |
    model class | ``Versionable``) over the registry's strict
    ``SentinelNode`` API.  Structural invariants (duplicate,
    referenced-by-migration) are enforced by the registry and
    must propagate unchanged.
    """

    @pytest.mark.parametrize(
        "registry, model",
        [
            [Registry[semver.Version, BaseModel](), UserV1],
            [Registry[pendulum.Date, BaseModel](), UserV20250310],
        ],
    )
    def test_store_and_get_model_by_tuple(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        model: type[types.VModel],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        version = envelope_model(model_adapter, versioning_settings, model)
        eng.store_model(version)

        assert eng.get_model(version.version).model is model

    @pytest.mark.parametrize(
        "registry, model",
        [
            [Registry[semver.Version, BaseModel](), UserV1],
            [Registry[pendulum.Date, BaseModel](), UserV20250310],
        ],
    )
    def test_get_model_by_class(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        model: type[types.VModel],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        eng.store_model(envelope_model(model_adapter, versioning_settings, model))

        assert eng.get_model(model).model is model

    @pytest.mark.parametrize(
        "registry, model",
        [
            [Registry[semver.Version, BaseModel](), UserV1],
            [Registry[pendulum.Date, BaseModel](), UserV20250310],
        ],
    )
    def test_get_model_by_versionable(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        model: type[types.VModel],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        version = envelope_model(model_adapter, versioning_settings, model)
        eng.store_model(version)

        assert eng.get_model(version).model is model

    @pytest.mark.parametrize(
        "registry, key",
        [
            [Registry[semver.Version, BaseModel](), ("User", semver.Version(9, 9, 9))],
            [
                Registry[pendulum.Date, BaseModel](),
                ("User", pendulum.Date(2099, 1, 1)),
            ],
        ],
    )
    def test_get_missing_model_raises(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        key: types.ModelVersionKey,
    ) -> None:
        eng = make_engine(registry, migration_settings)
        with pytest.raises(ModelNotFoundError):
            eng.get_model(key)

    @pytest.mark.parametrize(
        "registry, model",
        [
            [Registry[semver.Version, BaseModel](), UserV1],
            [Registry[pendulum.Date, BaseModel](), UserV20250310],
        ],
    )
    def test_store_duplicate_raises(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        model: type[types.VModel],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        version = envelope_model(model_adapter, versioning_settings, model)
        eng.store_model(version)

        with pytest.raises(ModelAlreadyRegisteredError):
            eng.store_model(version)

    @pytest.mark.parametrize(
        "registry, models, latest",
        [
            [
                Registry[semver.Version, BaseModel](),
                [UserV3, UserV1, UserV2],
                UserV3,
            ],
            [
                Registry[pendulum.Date, BaseModel](),
                [UserV20251231, UserV20260228, UserV20250310],
                UserV20260228,
            ],
        ],
    )
    def test_model_latest(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
        latest: type[types.VModel],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)

        assert eng.model_latest(versions[0].kind).model is latest

    def test_model_latest_unknown_kind_raises(
        self, migration_settings: MigrationSettings
    ) -> None:
        eng = make_engine(Registry[semver.Version, BaseModel](), migration_settings)
        with pytest.raises(RegistryError):
            eng.model_latest("User")

    @pytest.mark.parametrize(
        "registry, model",
        [
            [Registry[semver.Version, BaseModel](), UserV1],
            [Registry[pendulum.Date, BaseModel](), UserV20250310],
        ],
    )
    def test_find_model_hit(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        model: type[types.VModel],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        version = envelope_model(model_adapter, versioning_settings, model)
        eng.store_model(version)

        found = eng.find_model(version.version)
        assert found is not None
        assert found.model is model

    @pytest.mark.parametrize(
        "registry, key",
        [
            [Registry[semver.Version, BaseModel](), ("User", semver.Version(9, 9, 9))],
        ],
    )
    def test_find_model_miss_returns_none(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        key: types.ModelVersionKey,
    ) -> None:
        eng = make_engine(registry, migration_settings)
        assert eng.find_model(key) is None

    @pytest.mark.parametrize(
        "registry, model",
        [
            [Registry[semver.Version, BaseModel](), UserV1],
            [Registry[pendulum.Date, BaseModel](), UserV20250310],
        ],
    )
    def test_contains_version_tuple(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        model: type[types.VModel],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        version = envelope_model(model_adapter, versioning_settings, model)
        eng.store_model(version)

        assert version.version in eng
        assert (version.kind, "0.0.0-not-registered") not in eng

    @pytest.mark.parametrize(
        "registry, model",
        [
            [Registry[semver.Version, BaseModel](), UserV1],
            [Registry[pendulum.Date, BaseModel](), UserV20250310],
        ],
    )
    def test_remove_model_by_versionable(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        model: type[types.VModel],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        version = envelope_model(model_adapter, versioning_settings, model)
        eng.store_model(version)

        eng.remove_model(version)
        assert SentinelNode.from_version(version) not in registry

    @pytest.mark.parametrize(
        "registry, model",
        [
            [Registry[semver.Version, BaseModel](), UserV1],
            [Registry[pendulum.Date, BaseModel](), UserV20250310],
        ],
    )
    def test_remove_model_by_tuple(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        model: type[types.VModel],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        version = envelope_model(model_adapter, versioning_settings, model)
        eng.store_model(version)

        eng.remove_model(version.version)
        assert SentinelNode.from_version(version) not in registry

    @pytest.mark.parametrize(
        "registry, model",
        [
            [Registry[semver.Version, BaseModel](), UserV1],
            [Registry[pendulum.Date, BaseModel](), UserV20250310],
        ],
    )
    def test_remove_model_by_class(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        model: type[types.VModel],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        version = envelope_model(model_adapter, versioning_settings, model)
        eng.store_model(version)

        eng.remove_model(model)
        assert SentinelNode.from_version(version) not in registry

    def test_remove_missing_model_raises(
        self, migration_settings: MigrationSettings
    ) -> None:
        eng = make_engine(Registry[semver.Version, BaseModel](), migration_settings)
        with pytest.raises(RegistryError, match="not registered"):
            eng.remove_model(("User", semver.Version(9, 9, 9)))

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2]],
            [Registry[pendulum.Date, BaseModel](), [UserV20250310, UserV20251231]],
        ],
    )
    def test_remove_model_referenced_by_migration_raises(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)
        registry.store_migration(
            edge_from_models(
                model_adapter,
                versioning_settings,
                models[0],
                models[1],
                func=lambda d: d,
            )
        )

        with pytest.raises(RegistryError, match="referenced by migrations"):
            eng.remove_model(versions[0])


class TestMigrationManagement:
    """Engine-level CRUD for migration edges.

    Engine policy: key normalization (Versionable | class | tuple
    pairs), same-kind enforcement, and the adjacency rule —
    non-adjacent edges are accepted only when every consecutive
    edge inside the gap is registered and backward-compatible.
    Registry enforces structural invariants; both must propagate.
    """

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2]],
            [Registry[pendulum.Date, BaseModel](), [UserV20250310, UserV20251231]],
        ],
    )
    def test_store_and_get_by_versionable_pair(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)

        def _migrate(data: dict) -> dict:
            return data

        eng.store_migration((versions[0], versions[1]), _migrate)
        assert eng.get_migration((versions[0], versions[1])) is _migrate

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2]],
        ],
    )
    def test_store_and_get_by_class_pair(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        for m in models:
            eng.store_model(envelope_model(model_adapter, versioning_settings, m))

        def _migrate(data: dict) -> dict:
            return data

        eng.store_migration((models[0], models[1]), _migrate)
        assert eng.get_migration((models[0], models[1])) is _migrate

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2]],
        ],
    )
    def test_store_and_get_by_tuple_pair(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)

        def _migrate(data: dict) -> dict:
            return data

        key = (versions[0].version, versions[1].version)
        eng.store_migration(key, _migrate)
        assert eng.get_migration(key) is _migrate

    def test_store_across_kinds_raises(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
    ) -> None:
        eng = make_engine(Registry[semver.Version, BaseModel](), migration_settings)
        v_user = envelope_model(model_adapter, versioning_settings, UserV1)
        v_addr = envelope_model(model_adapter, versioning_settings, AddressV1)
        eng.store_model(v_user)
        eng.store_model(v_addr)

        with pytest.raises(RegistryError, match="across kinds"):
            eng.store_migration((v_user, v_addr), lambda d: d)

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2]],
        ],
    )
    def test_store_duplicate_raises(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)

        eng.store_migration((versions[0], versions[1]), lambda d: d)
        with pytest.raises(MigrationAlreadyRegisteredError):
            eng.store_migration((versions[0], versions[1]), lambda d: d)

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2]],
        ],
    )
    def test_get_missing_raises(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)

        with pytest.raises(MigrationNotFoundError):
            eng.get_migration((versions[0], versions[1]))

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2, UserV3]],
        ],
    )
    def test_store_non_adjacent_without_bc_raises(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)

        with pytest.raises(RegistryError, match="not adjacent"):
            eng.store_migration((versions[0], versions[2]), lambda d: d)

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2, UserV3]],
        ],
    )
    def test_store_non_adjacent_with_bc_gap_ok(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)

        eng.store_migration(
            (versions[0], versions[1]), lambda d: d, backward_compatible=True
        )
        eng.store_migration(
            (versions[1], versions[2]), lambda d: d, backward_compatible=True
        )

        def _skip(data: dict) -> dict:
            return data

        eng.store_migration((versions[0], versions[2]), _skip)
        assert eng.get_migration((versions[0], versions[2])) is _skip

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2, UserV3]],
        ],
    )
    def test_store_non_adjacent_partial_bc_gap_raises(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        """Gap with one non-bc consecutive edge rejects the skip edge."""
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)

        eng.store_migration(
            (versions[0], versions[1]), lambda d: d, backward_compatible=True
        )
        eng.store_migration((versions[1], versions[2]), lambda d: d)

        with pytest.raises(RegistryError, match="not adjacent"):
            eng.store_migration((versions[0], versions[2]), lambda d: d)

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2]],
        ],
    )
    def test_store_backward_adjacent_ok(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)

        def _down(data: dict) -> dict:
            return data

        eng.store_migration((versions[1], versions[0]), _down)
        assert eng.get_migration((versions[1], versions[0])) is _down

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2, UserV3]],
        ],
    )
    def test_remove_non_critical_ok(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)

        eng.store_migration(
            (versions[0], versions[1]), lambda d: d, backward_compatible=True
        )
        eng.store_migration(
            (versions[1], versions[2]), lambda d: d, backward_compatible=True
        )
        eng.store_migration((versions[0], versions[2]), lambda d: d)

        eng.remove_migration((versions[0], versions[2]))
        with pytest.raises(MigrationNotFoundError):
            eng.get_migration((versions[0], versions[2]))

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2]],
        ],
    )
    def test_remove_critical_raises(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)
        eng.store_migration((versions[0], versions[1]), lambda d: d)

        with pytest.raises(RegistryError, match="critical"):
            eng.remove_migration((versions[0], versions[1]))

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2]],
        ],
    )
    def test_remove_critical_with_force(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)
        eng.store_migration((versions[0], versions[1]), lambda d: d)

        eng.remove_migration((versions[0], versions[1]), force=True)
        with pytest.raises(MigrationNotFoundError):
            eng.get_migration((versions[0], versions[1]))

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2]],
        ],
    )
    def test_remove_missing_raises(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)

        with pytest.raises(MigrationNotFoundError):
            eng.remove_migration((versions[0], versions[1]))

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2, UserV3]],
        ],
    )
    def test_remove_range_critical_raises(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)
        eng.store_migration((versions[0], versions[1]), lambda d: d)
        eng.store_migration((versions[1], versions[2]), lambda d: d)

        with pytest.raises(RegistryError, match="critical"):
            eng.remove_migration_range(versions[0], versions[2])

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2, UserV3]],
        ],
    )
    def test_remove_range_skips_gaps(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        """Range over consecutive pairs with no edges is a no-op."""
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)

        eng.remove_migration_range(versions[0], versions[2])
        assert registry.kind_versions(versions[0].kind) == sorted(versions)

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2]],
        ],
    )
    def test_delete_kind_removes_all(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)
        eng.store_migration((versions[0], versions[1]), lambda d: d)

        eng.delete_kind(versions[0].kind)

        for v in versions:
            assert SentinelNode.from_version(v) not in registry
        assert (
            registry.has_migration(SentinelEdge.from_pair(versions[0], versions[1]))
            is False
        )

    def test_delete_unknown_kind_noop(
        self, migration_settings: MigrationSettings
    ) -> None:
        eng = make_engine(Registry[semver.Version, BaseModel](), migration_settings)
        eng.delete_kind("Nope")

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2]],
        ],
    )
    def test_add_and_remove_hook(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)
        eng.store_migration((versions[0], versions[1]), lambda d: d)

        key = SentinelEdge.from_pair(versions[0], versions[1])
        hook = MigrationHook()
        eng.add_hook((versions[0].version, versions[1].version), hook)
        assert registry.has_hooks(registry.get_migration_by_edge(key))

        eng.remove_hook((versions[0], versions[1]), hook)
        assert not registry.has_hooks(registry.get_migration_by_edge(key))

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2]],
        ],
    )
    def test_clear_hooks(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)
        eng.store_migration((versions[0], versions[1]), lambda d: d)

        eng.add_hook((versions[0], versions[1]), MigrationHook())
        eng.clear_hooks()
        assert not registry._hooks


class TestLookupConvenience:
    """Engine operator overloads for model / edge / path lookup."""

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2, UserV3]],
            [
                Registry[pendulum.Date, BaseModel](),
                [UserV20250310, UserV20251231, UserV20260228],
            ],
        ],
    )
    def test_contains_model_key(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)

        assert versions[0].version in eng
        assert models[0] in eng
        assert ("unknown", 0) not in eng

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2]],
            [Registry[pendulum.Date, BaseModel](), [UserV20250310, UserV20251231]],
        ],
    )
    def test_contains_migration_edge(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)
        eng.store_migration((versions[0], versions[1]), lambda d: d)

        assert (versions[0].version, versions[1].version) in eng
        assert (versions[1].version, versions[0].version) not in eng

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2, UserV3]],
        ],
    )
    def test_contains_migration_path_slice(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)
        eng.store_migration((versions[0], versions[1]), lambda d: d)
        eng.store_migration((versions[1], versions[2]), lambda d: d)

        assert slice(versions[0].version, versions[2].version) in eng
        assert slice(versions[0].version, versions[1].version) in eng
        assert slice(versions[2].version, versions[0].version) not in eng

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2]],
            [Registry[pendulum.Date, BaseModel](), [UserV20250310, UserV20251231]],
        ],
    )
    def test_getitem_migration_edge(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)

        def _migrate(d: dict) -> dict:
            return {"migrated": True}

        eng.store_migration((versions[0], versions[1]), _migrate)
        assert eng[(versions[0].version, versions[1].version)] is _migrate

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version, BaseModel](), [UserV1, UserV2, UserV3]],
        ],
    )
    def test_getitem_migration_path_slice(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        models: list[type[types.VModel]],
    ) -> None:
        eng = make_engine(registry, migration_settings)
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            eng.store_model(v)

        def _migrate_12(d: dict) -> dict:
            return d

        def _migrate_23(d: dict) -> dict:
            return d

        eng.store_migration((versions[0], versions[1]), _migrate_12)
        eng.store_migration((versions[1], versions[2]), _migrate_23)

        path = eng[slice(versions[0].version, versions[2].version)]
        assert path == [_migrate_12, _migrate_23]


class TestEntryMigrationIntegration:
    """Engine delegates per-entry migration to an injected EntryMigration strategy."""

    def test_engine_uses_custom_entry_migration(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        migration_settings: MigrationSettings,
    ) -> None:
        registry = Registry[semver.Version, BaseModel]()
        versions = [
            envelope_model(model_adapter, versioning_settings, UserV1),
            envelope_model(model_adapter, versioning_settings, UserV2),
        ]

        class _CustomTask:
            def run(self) -> dict[str, Any]:
                return {"custom": True}

        custom_strategy = MagicMock(spec=EntryMigration)
        custom_strategy.migrate.return_value = _CustomTask()

        engine = Engine(
            registry,
            migration_settings,
            SequentialExecutor(),
            GraphBuilder(
                registry,
                DiscoverySettings(),
                CompoundKeyWalker(
                    registry, settings=DiscoverySettings(), adapter=model_adapter
                ),
            ),
            model_adapter,
            entry_migration=custom_strategy,
        )
        for v in versions:
            engine.store_model(v)
        engine.store_migration((versions[0], versions[1]), lambda d: d)

        result = engine.migrate(
            {"kind": "User", "version": "1.0.0", "name": "Alice"},
            target=latest_target_resolver(engine.registry),
        )

        assert result == {"custom": True}
        assert custom_strategy.migrate.call_count == 1
