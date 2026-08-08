"""Tests for Registry: model and migration registration."""

import pendulum
import pytest
import semver

from pyverge.migration import (
    MigrationAlreadyRegisteredError,
    MigrationHook,
    MigrationNotFoundError,
    ModelAlreadyRegisteredError,
    ModelNotFoundError,
    PydanticModelAdapter,
    Registry,
    RegistryError,
    SentinelEdge,
    SentinelNode,
    VersioningSettings,
    VersionNode,
    types,
)
from tests.examples.pydantic.chrono import (
    UserV20250310,
    UserV20251231,
    UserV20260228,
)
from tests.examples.pydantic.semver import (
    UserV011Dev7,
    UserV1,
    UserV2,
    UserV3,
    UserV200Beta1,
)
from tests.utils import edge_from_models, envelope_model


class TestModel:
    @pytest.mark.parametrize(
        "registry,model",
        [
            [
                Registry[semver.Version](name="semver_test"),
                UserV200Beta1,
            ],
            [
                Registry[semver.Version](name="semver_test"),
                UserV200Beta1,
            ],
            [
                Registry[semver.Version](name="semver_test"),
                UserV200Beta1,
            ],
            [
                Registry[pendulum.Date](name="date_test"),
                UserV20250310,
            ],
            [
                Registry[pendulum.Date](name="date_test"),
                UserV20250310,
            ],
            [
                Registry[pendulum.Date](name="semver_test"),
                UserV20250310,
            ],
        ],
        ids=[
            "semver_user_latest",
            "semver_user_version",
            "semver_user_model",
            "date_user_latest",
            "date_user_version",
            "date_user_model",
        ],
    )
    def test_get_model(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: type[types.VModel_co],
    ) -> None:
        version = envelope_model(model_adapter, versioning_settings, model)
        registry.store_model(version)
        assert registry.get_model(SentinelNode.from_version(version)).model is model

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV3, UserV1, UserV2]],
            [Registry[pendulum.Date](), [UserV20251231, UserV20260228, UserV20250310]],
        ],
    )
    def test_versions_sorted(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel_co]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, cls) for cls in models
        ]
        for version in versions:
            registry.store_model(version)

        assert registry.versions == sorted(versions)

    @pytest.mark.parametrize(
        "registry, models, latest",
        [
            (
                Registry[semver.Version](),
                [UserV3, UserV1, UserV200Beta1],
                UserV3,
            ),
            (
                Registry[pendulum.Date](),
                [UserV20251231, UserV20260228, UserV20250310],
                UserV20260228,
            ),
        ],
    )
    def test_latest(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel_co]],
        latest: type[types.VModel_co],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, cls) for cls in models
        ]
        for version in versions:
            registry.store_model(version)

        assert registry.latest(versions[0].version[0]).model == latest

    @pytest.mark.parametrize(
        "registry, key",
        [
            (Registry[semver.Version](), ("User", "3.0.0")),
            (Registry[pendulum.Date](), ("User", "2025-03-10")),
        ],
    )
    def test_get_nonexistent_model_raises(
        self,
        registry: Registry[types.VersionValue],
        key: types.ModelVersionKey,
    ) -> None:
        with pytest.raises(ModelNotFoundError, match="not found"):
            registry.get_model(SentinelNode(*key))

    @pytest.mark.parametrize(
        "registry, registered, target",
        [
            (Registry[semver.Version](), UserV1, UserV3),
            (Registry[pendulum.Date](), UserV20250310, UserV20260228),
        ],
    )
    def test_get_nonexistent_model_by_class_raises(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        registered: type[types.VModel],
        target: type[types.VModel],
    ) -> None:
        registry.store_model(
            envelope_model(model_adapter, versioning_settings, registered)
        )
        with pytest.raises(ModelNotFoundError):
            registry.get_model(
                SentinelNode.from_version(
                    envelope_model(model_adapter, versioning_settings, target)
                )
            )

    @pytest.mark.parametrize(
        "registry, model, predicate",
        [
            (
                Registry[semver.Version](),
                UserV1,
                UserV1,
            ),
            (
                Registry[pendulum.Date](),
                UserV20251231,
                UserV20251231,
            ),
            (
                Registry[semver.Version](),
                UserV011Dev7,
                SentinelNode("User", semver.Version.parse("0.1.1+dev.7")),
            ),
            (
                Registry[pendulum.Date](),
                UserV20260228,
                SentinelNode("User", pendulum.parse("2026-02-28").date()),
            ),
        ],
    )
    def test_model_contains(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: type[types.VModel],
        predicate: types.LookupKey,
    ) -> None:
        registry.store_model(envelope_model(model_adapter, versioning_settings, model))
        assert predicate in registry

    @pytest.mark.parametrize(
        "registry, model, predicate",
        [
            (Registry[semver.Version](), UserV1, UserV3),
            (Registry[pendulum.Date](), UserV20250310, UserV20260228),
        ],
    )
    def test_model_class_not_in_registry(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: type[types.VModel],
        predicate: type[types.VModel],
    ) -> None:
        registry.store_model(envelope_model(model_adapter, versioning_settings, model))
        with pytest.raises(ModelNotFoundError):
            registry.get_model_by_class(predicate)

    def test_latest_model_empty_raises(self) -> None:
        registry = Registry[pendulum.Date]()
        with pytest.raises(RegistryError):
            registry.latest("User")

    @pytest.mark.parametrize(
        "registry, model",
        [
            (Registry[semver.Version](), UserV200Beta1),
            (Registry[pendulum.Date](), UserV20250310),
        ],
    )
    def test_store_duplicate_raises(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: type[types.VModel],
    ) -> None:
        registry.store_model(envelope_model(model_adapter, versioning_settings, model))
        with pytest.raises(ModelAlreadyRegisteredError, match="already registered"):
            registry.store_model(
                envelope_model(model_adapter, versioning_settings, model)
            )

    @pytest.mark.parametrize(
        "registry, model",
        [
            (Registry[semver.Version](), UserV1),
            (Registry[pendulum.Date](), UserV20251231),
        ],
    )
    def test_remove_model(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: type[types.VModel],
    ) -> None:
        version = envelope_model(model_adapter, versioning_settings, model)
        registry.store_model(version)
        assert SentinelNode.from_version(version) in registry
        registry.remove_model(version)
        with pytest.raises(ModelNotFoundError):
            registry.get_model(version)

    def test_remove_nonexistent_raises(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        registry = Registry[semver.Version]()
        with pytest.raises(RegistryError, match="is not registered"):
            registry.remove_model(
                SentinelNode.from_version(
                    envelope_model(model_adapter, versioning_settings, UserV1)
                )
            )

    def test_registry_model_cleanup(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        version = envelope_model(model_adapter, versioning_settings, UserV1)
        registry = Registry[semver.Version]()
        registry.store_model(version)
        registry.clear_models()
        with pytest.raises(ModelNotFoundError):
            registry.get_model(SentinelNode.from_version(version))

    @pytest.mark.parametrize(
        "registry, model",
        [
            [Registry[semver.Version](), UserV1],
            [Registry[pendulum.Date](), UserV20251231],
        ],
    )
    def test_copy_preserves_model_class_lookup(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: type[types.VModel],
    ) -> None:
        """A copied registry keeps class-based lookups."""
        registry.store_model(envelope_model(model_adapter, versioning_settings, model))
        clone = registry.copy()
        assert clone.get_model_by_class(model).model is model


class TestMigration:
    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
            [Registry[pendulum.Date](), [UserV20250310, UserV20251231]],
        ],
    )
    def test_store_and_get(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, model)
            for model in models
        ]
        for v in versions:
            registry.store_model(v)

        def _migrate(data: dict) -> dict:
            return data

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=_migrate
        )
        registry.store_migration(edge)
        assert (
            registry.get_migration(SentinelEdge.from_version_edge(edge)).func
            is edge.func
        )

    @pytest.mark.parametrize(
        "registry, models",
        [
            [
                Registry[semver.Version](),
                [UserV1, UserV2],
            ],
            [
                Registry[pendulum.Date](),
                [UserV20250310, UserV20251231],
            ],
        ],
    )
    def test_register_migration_with_missing_version(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ):
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        registry.store_model(versions[0])
        with pytest.raises(MigrationNotFoundError):
            edge = edge_from_models(
                model_adapter, versioning_settings, models[0], models[1], func=print
            )
            registry.store_migration(edge)

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
            [Registry[pendulum.Date](), [UserV20250310, UserV20251231]],
        ],
    )
    def test_register_migration_dups(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ):
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        def _migrate(data: dict) -> dict:
            return data

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=_migrate
        )
        registry.store_migration(edge)
        with pytest.raises(MigrationAlreadyRegisteredError):
            registry.store_migration(edge)

    def test_get_nonexistent_raises(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        registry = Registry[semver.Version]()
        versions = [
            envelope_model(model_adapter, versioning_settings, m)
            for m in [UserV1, UserV2, UserV3]
        ]
        for v in versions:
            registry.store_model(v)

        with pytest.raises(MigrationNotFoundError):
            fake_key = edge_from_models(
                model_adapter,
                versioning_settings,
                versions[0]._model,
                versions[1]._model,
                func=lambda data: data,
            )
            registry.get_migration(SentinelEdge.from_version_edge(fake_key))

    @pytest.mark.parametrize(
        "registry, models",
        [
            [
                Registry[semver.Version](),
                [UserV1, UserV2],
            ],
            [
                Registry[pendulum.Date](),
                [UserV20250310, UserV20251231],
            ],
            [
                Registry[semver.Version](),
                [UserV1, UserV3],
            ],
        ],
    )
    def test_remove_migration(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        key = edge_from_models(
            model_adapter,
            versioning_settings,
            models[0],
            models[1],
            func=lambda data: data,
        )
        registry.store_migration(key)
        registry.remove_migration(SentinelEdge.from_version_edge(key))

        with pytest.raises(MigrationNotFoundError):
            registry.get_migration(SentinelEdge.from_version_edge(key))


class TestHooks:
    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
            [Registry[pendulum.Date](), [UserV20250310, UserV20251231]],
        ],
    )
    def test_add_and_get_hook(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=print
        )
        key = SentinelEdge.from_version_edge(edge)
        hook = MigrationHook()
        registry.store_migration(edge)
        registry.add_hook(key, hook)
        assert registry.get_hooks(key) == [hook]

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
        ],
    )
    def test_get_hooks_returns_empty_when_none_registered(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=print
        )
        assert registry.get_hooks(edge) == []

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
        ],
    )
    def test_remove_single_hook(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        hook1 = MigrationHook()
        hook2 = MigrationHook()
        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=print
        )
        key = SentinelEdge.from_version_edge(edge)
        registry.store_migration(edge)
        for h in [hook1, hook2]:
            registry.add_hook(edge, h)
        registry.remove_hook(key, hook1)

        assert registry.get_hooks(key) == [hook2]

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
        ],
    )
    def test_remove_all_hooks_for_key(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=print
        )
        registry.store_migration(edge)
        registry.add_hook(edge, MigrationHook())
        registry.add_hook(edge, MigrationHook())
        registry.remove_hook(edge)  # hook is None → remove all
        assert registry.get_hooks(edge) == []

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
        ],
    )
    def test_remove_nonexistent_hook_raises(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=print
        )
        key = SentinelEdge.from_version_edge(edge)
        registry.store_migration(edge)
        with pytest.raises(RegistryError):
            registry.remove_hook(key, MigrationHook())

    @pytest.mark.parametrize(
        "registry, models, expected_amount",
        [
            [Registry[semver.Version](), [UserV1, UserV2], 2],
        ],
    )
    def test_clear_all_hooks(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
        expected_amount: int,
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=print
        )
        key = SentinelEdge.from_version_edge(edge)
        registry.store_migration(edge)
        registry.add_hook(edge, MigrationHook())
        registry.add_hook(edge, MigrationHook())
        assert len(registry.get_hooks(key)) == expected_amount
        registry.clear_hooks(key)
        assert registry.get_hooks(key) == []

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
            [Registry[pendulum.Date](), [UserV20250310, UserV20260228]],
        ],
    )
    def test_clear_hooks_for_key(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=print
        )
        key = SentinelEdge.from_version_edge(edge)
        registry.store_migration(edge)
        registry.add_hook(key, MigrationHook())
        registry.clear_hooks(key)
        assert registry.get_hooks(key) == []


class TestVersionEdgeIndex:
    """Inverted index: version -> set of migration edges touching it."""

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
            [Registry[pendulum.Date](), [UserV20250310, UserV20251231]],
        ],
    )
    def test_migrations_of_empty(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        assert (
            registry.migrations_of(SentinelNode.from_version(versions[0]))
            == frozenset()
        )

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2, UserV3]],
            [
                Registry[pendulum.Date](),
                [UserV20250310, UserV20251231, UserV20260228],
            ],
        ],
    )
    def test_migrations_of_source_and_target(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        e1 = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=lambda d: d
        )
        e2 = edge_from_models(
            model_adapter, versioning_settings, models[1], models[2], func=lambda d: d
        )
        registry.store_migration(e1)
        registry.store_migration(e2)

        assert registry.migrations_of(SentinelNode.from_version(versions[0])) == {e1}
        assert registry.migrations_of(SentinelNode.from_version(versions[1])) == {
            e1,
            e2,
        }
        assert registry.migrations_of(SentinelNode.from_version(versions[2])) == {e2}

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
            [Registry[pendulum.Date](), [UserV20250310, UserV20251231]],
        ],
    )
    def test_migrations_of_accepts_node_key(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        """VersionNode and SentinelNode keys hit the same bucket."""
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=lambda d: d
        )
        registry.store_migration(edge)

        assert registry.migrations_of(versions[0]) == registry.migrations_of(
            SentinelNode.from_version(versions[0])
        )

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2, UserV3]],
        ],
    )
    def test_index_updated_on_remove_migration(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        e1 = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=lambda d: d
        )
        e2 = edge_from_models(
            model_adapter, versioning_settings, models[1], models[2], func=lambda d: d
        )
        registry.store_migration(e1)
        registry.store_migration(e2)

        registry.remove_migration(SentinelEdge.from_version_edge(e1))

        assert registry.migrations_of(SentinelNode.from_version(versions[0])) == (
            frozenset()
        )
        assert registry.migrations_of(SentinelNode.from_version(versions[1])) == {e2}

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
        ],
    )
    def test_index_cleared_on_clear_migrations(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=lambda d: d
        )
        registry.store_migration(edge)
        registry.clear_migrations()

        assert registry.migrations_of(SentinelNode.from_version(versions[0])) == (
            frozenset()
        )

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
        ],
    )
    def test_copy_preserves_index_independently(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=lambda d: d
        )
        registry.store_migration(edge)

        clone = registry.copy()
        key = SentinelNode.from_version(versions[0])
        assert clone.migrations_of(key) == registry.migrations_of(key)

        clone.remove_migration(SentinelEdge.from_version_edge(edge))
        assert clone.migrations_of(key) == frozenset()
        assert registry.migrations_of(key) == {edge}

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
            [Registry[pendulum.Date](), [UserV20250310, UserV20251231]],
        ],
    )
    def test_remove_model_raises_when_referenced(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=lambda d: d
        )
        registry.store_migration(edge)

        with pytest.raises(RegistryError, match="referenced by migrations") as exc:
            registry.remove_model(SentinelNode.from_version(versions[0]))
        assert "→" in str(exc.value)

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
        ],
    )
    def test_remove_model_allowed_after_migration_removed(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=lambda d: d
        )
        registry.store_migration(edge)
        registry.remove_migration(SentinelEdge.from_version_edge(edge))

        registry.remove_model(SentinelNode.from_version(versions[0]))
        with pytest.raises(ModelNotFoundError):
            registry.get_model(SentinelNode.from_version(versions[0]))


class TestEdgePairLookup:
    """Direct (from, to) pair index for point lookups on edges."""

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV3, UserV1, UserV2]],
            [
                Registry[pendulum.Date](),
                [UserV20251231, UserV20260228, UserV20250310],
            ],
        ],
    )
    def test_kind_versions_sorted(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        assert registry.kind_versions(versions[0].kind) == sorted(versions)

    def test_kind_versions_unknown_returns_empty(self) -> None:
        registry = Registry[semver.Version]()
        assert registry.kind_versions("Nope") == []

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2, UserV3]],
        ],
    )
    def test_has_migration(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=lambda d: d
        )
        registry.store_migration(edge)

        key12 = SentinelEdge.from_pair(versions[0], versions[1])
        key13 = SentinelEdge.from_pair(versions[0], versions[2])
        assert registry.has_migration(key12) is True
        assert registry.has_migration(key13) is False
        # SentinelNode endpoints hit the same index entry
        assert (
            registry.has_migration(
                SentinelEdge.from_pair(
                    SentinelNode.from_version(versions[0]),
                    SentinelNode.from_version(versions[1]),
                )
            )
            is True
        )

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
            [Registry[pendulum.Date](), [UserV20250310, UserV20251231]],
        ],
    )
    def test_get_migration_by_pair(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=lambda d: d
        )
        registry.store_migration(edge)

        key = SentinelEdge.from_pair(versions[0], versions[1])
        found = registry.get_migration_by_edge(key)
        assert found.func is edge.func

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
        ],
    )
    def test_get_migration_by_pair_missing_raises(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        key = SentinelEdge.from_pair(versions[0], versions[1])
        with pytest.raises(MigrationNotFoundError):
            registry.get_migration_by_edge(key)

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
        ],
    )
    def test_is_backward_compatible_edge_default_false(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=lambda d: d
        )
        registry.store_migration(edge)

        key = SentinelEdge.from_pair(versions[0], versions[1])
        assert registry.get_migration_by_edge(key).diff.is_backward_compatible is False

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
        ],
    )
    def test_is_backward_compatible_edge_true(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter,
            versioning_settings,
            models[0],
            models[1],
            func=lambda d: d,
            backward_compatible=True,
        )
        registry.store_migration(edge)

        key = SentinelEdge.from_pair(versions[0], versions[1])
        assert registry.get_migration_by_edge(key).diff.is_backward_compatible is True

    def test_get_migration_by_edge_missing_raises(self) -> None:
        registry = Registry[semver.Version]()
        v1 = VersionNode[semver.Version, object](
            _model=UserV1, _value=semver.Version(1, 0, 0), _kind="User"
        )
        v2 = VersionNode[semver.Version, object](
            _model=UserV2, _value=semver.Version(2, 0, 0), _kind="User"
        )
        with pytest.raises(MigrationNotFoundError):
            registry.get_migration_by_edge(SentinelEdge.from_pair(v1, v2))

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
        ],
    )
    def test_pair_index_updated_on_remove(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=lambda d: d
        )
        registry.store_migration(edge)
        registry.remove_migration(SentinelEdge.from_version_edge(edge))

        key = SentinelEdge.from_pair(versions[0], versions[1])
        assert registry.has_migration(key) is False

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
        ],
    )
    def test_pair_index_cleared_on_clear_migrations(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=lambda d: d
        )
        registry.store_migration(edge)
        registry.clear_migrations()

        key = SentinelEdge.from_pair(versions[0], versions[1])
        assert registry.has_migration(key) is False

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
        ],
    )
    def test_pair_index_copy_independent(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=lambda d: d
        )
        registry.store_migration(edge)

        clone = registry.copy()
        key = SentinelEdge.from_pair(versions[0], versions[1])
        assert clone.has_migration(key) is True

        clone.remove_migration(SentinelEdge.from_version_edge(edge))
        assert clone.has_migration(key) is False
        assert registry.has_migration(key) is True


class TestMigrationHookGuard:
    """A migration with registered hooks cannot be removed directly."""

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
            [Registry[pendulum.Date](), [UserV20250310, UserV20251231]],
        ],
    )
    def test_remove_migration_with_hooks_raises(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=lambda d: d
        )
        registry.store_migration(edge)
        registry.add_hook(edge, MigrationHook())

        key = SentinelEdge.from_version_edge(edge)
        with pytest.raises(RegistryError, match="hooks"):
            registry.remove_migration(key)

        # Migration untouched
        assert registry.get_migration(key).func is edge.func

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
        ],
    )
    def test_remove_migration_allowed_after_hooks_cleared(
        self,
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        for v in versions:
            registry.store_model(v)

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=lambda d: d
        )
        key = SentinelEdge.from_version_edge(edge)
        registry.store_migration(edge)
        registry.add_hook(key, MigrationHook())
        registry.clear_hooks(key)

        registry.remove_migration(key)
        with pytest.raises(MigrationNotFoundError):
            registry.get_migration(SentinelEdge.from_version_edge(edge))
