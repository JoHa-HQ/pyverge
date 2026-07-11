"""Tests for Registry: model and migration registration."""

from typing import cast

import pytest
from pendulum import Date
from semver import Version

from pydantic_migrator.migration import (
    MigrationError,
    MigrationHook,
    MigrationQuery,
    MigrationSettings,
    ModelNotFoundError,
    ModelQuery,
    Registry,
    RegistryError,
    VersionedModel,
    types,
)
from pydantic_migrator.migration.exceptions import ModelAlreadyRegisteredError
from tests.examples.chronnological import UserV20250310, UserV20251231, UserV20260228
from tests.examples.semver import UserV1, UserV2, UserV3, UserV123, UserV200Beta1
from tests.utils import envelope_model


class TestModel:
    def test_store_and_get(self, migration_settings: MigrationSettings) -> None:
        registry = Registry[Version](name="test_store_and_get")
        version = cast(
            VersionedModel[Version, UserV1],
            envelope_model(migration_settings, UserV1)
        )
        registry.store_model(version)
        query = ModelQuery[Version](version_value=cast(Version, version.version))
        assert registry.get_model(query).model is UserV1

    @pytest.mark.parametrize(
        "models",
        [[UserV3, UserV1, UserV2], [UserV20251231, UserV20260228, UserV20250310]],
    )
    def test_versions_sorted(
        self, migration_settings: MigrationSettings, models: list[type[types.VModel_co]]
    ) -> None:
        registry = Registry()

        for cls in models:
            version = envelope_model(migration_settings, cls)
            registry.store_model(version)

        assert registry.versions == sorted(
            [envelope_model(migration_settings, cls) for cls in models]
        )

    @pytest.mark.parametrize(
        "registry, models, latest",
        [
            (Registry[Version](), [UserV3, UserV1, UserV200Beta1], UserV3),
            (Registry[Date](), [UserV20251231, UserV20260228, UserV20250310], UserV20260228),
        ],
    )
    def test_latest(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel_co]],
        latest: type[types.VModel_co],
    ) -> None:

        for cls in models:
            version = cast(VersionedModel[types.VersionValue, types.VModel_co], envelope_model(migration_settings, cls))
            registry.store_model(version)

        assert registry.latest.model == latest

    @pytest.mark.parametrize(
        "registry, query_factory, model",
        [
            (Registry[Version](), ModelQuery[Version], UserV3),
            (Registry[Date](), ModelQuery[Date], UserV20250310),
        ],
    )
    def test_get_nonexistent_model_raises(
        self,
        migration_settings: MigrationSettings,
        query_factory: type[ModelQuery[types.VersionValue]],
        registry: Registry[types.VersionValue],
        model: type[types.VModel_co]
    ) -> None:
        version = cast(
            VersionedModel[types.VersionValue, types.VModel_co],
            envelope_model(migration_settings, model),
        )

        with pytest.raises(ModelNotFoundError, match="not found"):
            registry.get_model(
                query_factory(version_value=version.version)
            )

    @pytest.mark.parametrize(
        "registry, query_factory, model",
        [
            (Registry[Version](), ModelQuery[Version], UserV123),
            (Registry[Date](), ModelQuery[Date], UserV20250310),
        ],
    )
    def test_get_model_by_class(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        query_factory: type[ModelQuery[types.VersionValue]],
        model: type[types.VModel],
    ) -> None:
        version = envelope_model(migration_settings, model)
        registry.store_model(version)
        query = query_factory(model_cls=model)
        assert registry.get_model(query).model is model

    @pytest.mark.parametrize(
        "registry, registered, queried",
        [
            (Registry[Version](), UserV1, UserV3),
            (Registry[Date](), UserV20250310, UserV20260228),
        ],
    )
    def test_get_nonexistent_model_by_class_raises(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        registered: type[types.VModel],
        queried: type[types.VModel],
    ) -> None:
        registry.store_model(envelope_model(migration_settings, registered))
        with pytest.raises(ModelNotFoundError):
            registry.get_model(ModelQuery[types.VersionValue](model_cls=queried))

    @pytest.mark.parametrize(
        "registry, model",
        [
            (Registry[Version](), UserV1),
            (Registry[Date](), UserV20251231),
        ],
    )
    def test_model_class_in_registry(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        model: type[types.VModel],
    ) -> None:
        registry.store_model(envelope_model(migration_settings, model))
        assert model in registry

    @pytest.mark.parametrize(
        "registry, registered, queried",
        [
            (Registry[Version](), UserV1, UserV3),
            (Registry[Date](), UserV20250310, UserV20260228),
        ],
    )
    def test_model_class_not_in_registry(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        registered: type[types.VModel],
        queried: type[types.VModel],
    ) -> None:
        registry.store_model(envelope_model(migration_settings, registered))
        assert queried not in registry

    def test_latest_model_empty_raises(self) -> None:
        registry = Registry[Date]()
        with pytest.raises(RegistryError):
            _ = registry.latest

    @pytest.mark.parametrize("registry, model", [
        (Registry[Version](), UserV200Beta1),
        (Registry[Date](), UserV20250310),
    ])
    def test_store_duplicate_raises(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        model: type[types.VModel],
    ) -> None:
        registry.store_model(envelope_model(migration_settings, model))
        with pytest.raises(ModelAlreadyRegisteredError, match="already registered"):
            registry.store_model(envelope_model(migration_settings, model))

    @pytest.mark.parametrize("registry, model, expected", [
        (Registry[Version](), UserV1, False),
        (Registry[Version](), UserV123, True),
        (Registry[Date](), UserV20251231, True),
    ])
    def test_store_backward_compatible_model(self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        model: type[types.VModel],
        expected: bool,
    ) -> None:
        version = cast(
            VersionedModel[types.VersionValue, types.VModel],
            envelope_model(migration_settings, model)
        )
        registry.store_model(
            version, backward_compatible=expected
        )

        assert registry.is_backward_compatible(
            ModelQuery[Version](
                version_value=cast(Version, version.version)
            )
        ) is expected


    @pytest.mark.parametrize(
        "registry, model",
        [
            (Registry[Version](), UserV1),
            (Registry[Date](), UserV20251231),
        ],
    )
    def test_remove_model(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        model: type[types.VModel],
    ) -> None:
        version = cast(VersionedModel[types.VersionValue, types.VModel], envelope_model(
            migration_settings, model
        ))
        registry.store_model(version)
        assert version.version in registry
        registry.remove_model(version)
        assert version.version not in registry

    def test_remove_nonexistent_raises(self, migration_settings: MigrationSettings) -> None:
        registry = Registry[Version]()
        with pytest.raises(RegistryError, match="is not registered"):
            registry.remove_model(envelope_model(migration_settings, UserV1))

    @pytest.mark.parametrize("registry, models", [
        (Registry[Version](), [UserV1, UserV2]),
        (Registry[Version](), [UserV20250310, UserV20251231]),
    ])
    def test_remove_cleans_migrations(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, model) for model in models]
        for v in versions:
            registry.store_model(v)

        def _noop(data: dict) -> dict:
            return data

        registry.store_migration(
            versions[0], versions[1], _noop
        )

        with pytest.raises(RegistryError, match="referenced by migrations"):
            registry.remove_model(versions[0])


    def test_remove_cleans_backward_compatible(
        self,
        migration_settings: MigrationSettings
    ) -> None:
        registry = Registry[Version]()
        assert registry.is_backward_compatible(
            ModelQuery[Version](
                version_value=envelope_model(migration_settings, UserV1).version
            )
        ) is False


class TestMigration:

    @pytest.mark.parametrize("registry, models", [
        [Registry[Version](), [UserV1, UserV2]],
        [Registry[Date](), [UserV20250310, UserV20251231]],
    ])
    def test_register_migration_with_missing_version(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]]
    ):
        versions = [envelope_model(migration_settings, m) for m in models]
        registry.store_model(versions[0])
        with pytest.raises(RegistryError):
            registry.store_migration(*versions, lambda dict: print(hello))

    @pytest.mark.parametrize("registry, models", [
        [Registry[Version](), [UserV1, UserV2]],
        [Registry[Date](), [UserV20250310, UserV20251231]],
    ])
    def test_store_and_get(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [
            cast(
                VersionedModel[Version, types.VModel],
                envelope_model(migration_settings, model)
            ) for model in models
        ]
        for v in versions:
            registry.store_model(v)

        def _migrate(data: dict) -> dict:
            return data

        query = MigrationQuery[Version](version_range=tuple(v.version for v in versions[:2]))
        registry.store_migration(versions[0], versions[1], _migrate)
        assert registry.get_migration(query) is _migrate


    @pytest.mark.parametrize("registry, models", [
        [Registry[Version](), [UserV1, UserV2]],
        [Registry[Date](), [UserV20250310, UserV20251231]],
    ])
    def test_register_migration_dups(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ):
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        def _migrate(data: dict) -> dict:
            return data

        registry.store_migration(*versions, _migrate)
        with pytest.raises(RegistryError, match="is already registered"):
            registry.store_migration(*versions, _migrate)


    def test_get_nonexistent_raises(self, migration_settings: MigrationSettings) -> None:
        registry = Registry[Version]()
        versioned = [envelope_model(migration_settings, m) for m in [UserV1, UserV2, UserV3]]
        for v in versioned:
            registry.store_model(v)

        with pytest.raises(MigrationError):
            query = MigrationQuery[Version](
                version_range=(versioned[0].version, versioned[2].version)
            )
            registry.get_migration(query)

    @pytest.mark.parametrize("registry, models", [
        [Registry[Version](), [UserV1, UserV2, UserV3]],
        [Registry[Date](), [UserV20250310, UserV20251231, UserV20260228]],
    ])
    def test_multi_range_query(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        def _migrate(data: dict) -> dict:
            return data

        registry.store_migration(versions[0], versions[1], _migrate)
        registry.store_migration(versions[1], versions[2], _migrate)

        query = MigrationQuery[types.VersionValue](
            version_range=tuple(v.version for v in versions)
        )
        result = registry.get_migration(query)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] is _migrate
        assert result[1] is _migrate

    @pytest.mark.parametrize("registry, models", [
        [Registry[Version](), [UserV1, UserV2]],
        [Registry[Date](), [UserV20250310, UserV20251231]],
    ])
    def test_use_latest(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        def _migrate(data: dict) -> dict:
            return data

        registry.store_migration(versions[0], versions[1], _migrate)

        query = MigrationQuery[types.VersionValue](
            version_range=(versions[0].version,),
            use_latest=True,
        )
        assert registry.get_migration(query) is _migrate

    @pytest.mark.parametrize("registry, models", [
        [Registry[Version](), [UserV1, UserV2]],
    ])
    def test_model_based_query(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        def _migrate(data: dict) -> dict:
            return data

        registry.store_migration(versions[0], versions[1], _migrate)

        query = MigrationQuery[types.VersionValue](
            model_range=tuple(m for m in models),
        )
        assert registry.get_migration(query) is _migrate

    @pytest.mark.parametrize("registry, models", [
        [Registry[Version](), [UserV1, UserV123, UserV2]],
    ])
    def test_non_adjacent_with_backward_compat(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        registry.store_model(versions[0])
        registry.store_model(versions[1], backward_compatible=True)
        registry.store_model(versions[2])

        def _migrate(data: dict) -> dict:
            return data

        registry.store_migration(versions[0], versions[2], _migrate)
        query = MigrationQuery[types.VersionValue](
            version_range=(versions[0].version, versions[2].version)
        )
        assert registry.get_migration(query) is _migrate

    @pytest.mark.parametrize("registry, models", [
        [
            Registry[Version](),
            [
                UserV1,
                UserV123,
                UserV2
            ]
        ],
    ])
    def test_non_adjacent_without_backward_compat(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        registry.store_model(versions[0])
        registry.store_model(versions[1])  # not backward_compatible
        registry.store_model(versions[2])

        def _migrate(data: dict) -> dict:
            return data

        with pytest.raises(RegistryError):
            registry.store_migration(versions[0], versions[2], _migrate)

    @pytest.mark.parametrize("registry, models", [
        [Registry[Version](), [UserV1, UserV2]],
        [Registry[Date](), [UserV20250310, UserV20251231]],
    ])
    def test_remove_migration(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        def _migrate(data: dict) -> dict:
            return data

        registry.store_migration(versions[0], versions[1], _migrate)
        registry.remove_migration(versions[0], versions[1])

        query = MigrationQuery[types.VersionValue](
            version_range=(versions[0].version, versions[1].version)
        )
        with pytest.raises(MigrationError):
            registry.get_migration(query)


class TestHooks:
    @pytest.mark.parametrize("registry, models", [
        [Registry[Version](), [UserV1, UserV2]],
        [Registry[Date](), [UserV20250310, UserV20251231]],
    ])
    def test_add_and_get_hook(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        hook = MigrationHook()
        registry.add_hook(hook, versions[0], versions[1])
        assert registry.get_hook(versions[0], versions[1]) == [hook]

    @pytest.mark.parametrize("registry, models", [
        [Registry[Version](), [UserV1, UserV2]],
    ])
    def test_get_hook_empty(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        assert registry.get_hook(versions[0], versions[1]) == []

    @pytest.mark.parametrize("registry, models", [
        [Registry[Version](), [UserV1, UserV2]],
    ])
    def test_remove_single_hook(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        hook = MigrationHook()
        registry.add_hook(hook, versions[0], versions[1])
        registry.remove_hook(versions[0], versions[1], hook)
        assert registry.get_hook(versions[0], versions[1]) == []

    @pytest.mark.parametrize("registry, models", [
        [Registry[Version](), [UserV1, UserV2]],
    ])
    def test_remove_all_hooks_for_key(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        registry.add_hook(MigrationHook(), versions[0], versions[1])
        registry.add_hook(MigrationHook(), versions[0], versions[1])
        registry.remove_hook(versions[0], versions[1])  # hook is None → remove all
        assert registry.get_hook(versions[0], versions[1]) == []

    @pytest.mark.parametrize("registry, models", [
        [Registry[Version](), [UserV1, UserV2]],
    ])
    def test_remove_nonexistent_hook_raises(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        with pytest.raises(ValueError, match="is not registered"):
            registry.remove_hook(versions[0], versions[1], MigrationHook())

    @pytest.mark.parametrize("registry, models", [
        [Registry[Version](), [UserV1, UserV2]],
    ])
    def test_clear_all_hooks(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        registry.add_hook(MigrationHook(), versions[0], versions[1])
        registry.add_hook(MigrationHook(), versions[0], versions[1])
        registry.clear_hooks()
        assert registry.get_hook(versions[0], versions[1]) == []

    @pytest.mark.parametrize("registry, models", [
        [Registry[Version](), [UserV1, UserV2]],
    ])
    def test_clear_hooks_for_key(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        registry.add_hook(MigrationHook(), versions[0], versions[1])
        registry.clear_hooks(versions[0], versions[1])
        assert registry.get_hook(versions[0], versions[1]) == []
