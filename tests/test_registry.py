"""Tests for Registry: model and migration registration."""

import operator
from typing import cast

import pendulum
import pytest
import semver

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
    VersioningSettings,
    types,
)
from pydantic_migrator.migration.exceptions import (
    MigrationAlreadyRegisteredError,
    MigrationNotFoundError,
    ModelAlreadyRegisteredError,
)
from tests.examples.chrono import UserV20250310, UserV20251231, UserV20260228
from tests.examples.semver import (
    UserV011Dev7,
    UserV1,
    UserV2,
    UserV3,
    UserV123,
    UserV200Beta1,
)
from tests.utils import envelope_model


class TestModel:
    @pytest.mark.parametrize(
        "registry,model,lookup_key",
        [
            [
                Registry[semver.Version](name="semver_test"),
                UserV200Beta1,
                ModelQuery[semver.Version](key="User", use_latest=True),
            ],
            [
                Registry[semver.Version](name="semver_test"),
                UserV200Beta1,
                ModelQuery[semver.Version](
                    key=("User", VersionedModel.of("2.0.0-beta.1"))
                ),
            ],
            [
                Registry[semver.Version](name="semver_test"),
                UserV200Beta1,
                ModelQuery[semver.Version](key=UserV200Beta1),
            ],
            [
                Registry[pendulum.Date](name="date_test"),
                UserV20250310,
                ModelQuery[pendulum.Date](key="User", use_latest=True),
            ],
            [
                Registry[pendulum.Date](name="date_test"),
                UserV20250310,
                ModelQuery[pendulum.Date](
                    key=("User", VersionedModel.of("2025-03-10"))
                ),
            ],
            [
                Registry[pendulum.Date](name="semver_test"),
                UserV20250310,
                ModelQuery[pendulum.Date](key=UserV20250310),
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
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: type[types.VModel_co],
        lookup_key: ModelQuery[types.VersionValue],
    ) -> None:
        version = envelope_model(versioning_settings, model)
        registry.store_model(version)
        assert registry.get_model(version.version).model is model

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV3, UserV1, UserV2]],
            [Registry[pendulum.Date](), [UserV20251231, UserV20260228, UserV20250310]],
        ],
    )
    def test_versions_sorted(
        self,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel_co]],
    ) -> None:
        versions = [envelope_model(versioning_settings, cls) for cls in models]
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
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel_co]],
        latest: type[types.VModel_co],
    ) -> None:
        versions = [envelope_model(versioning_settings, cls) for cls in models]
        for version in versions:
            registry.store_model(version)

        assert registry.latest(versions[0].version[0]).model == latest

    @pytest.mark.parametrize(
        "registry, query",
        [
            (Registry[semver.Version](), ("User", "3.0.0")),
            (Registry[pendulum.Date](), ("User", "2025-03-10")),
        ],
    )
    def test_get_nonexistent_model_raises(
        self,
        registry: Registry[types.VersionValue],
        query: types.ModelVersionKey,
    ) -> None:
        with pytest.raises(ModelNotFoundError, match="not found"):
            registry.get_model(query)

    @pytest.mark.parametrize(
        "registry, registered, target",
        [
            (Registry[semver.Version](), UserV1, UserV3),
            (Registry[pendulum.Date](), UserV20250310, UserV20260228),
        ],
    )
    def test_get_nonexistent_model_by_class_raises(
        self,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        registered: type[types.VModel],
        target: type[types.VModel],
    ) -> None:
        registry.store_model(envelope_model(versioning_settings, registered))
        with pytest.raises(ModelNotFoundError):
            registry.get_model(envelope_model(versioning_settings, target).version)

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
                ("User", VersionedModel.of("0.1.1+dev.7")),
            ),
            (
                Registry[pendulum.Date](),
                UserV20260228,
                ("User", VersionedModel.of("2026-02-28")),
            ),
        ],
    )
    def test_model_contains(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        model: type[types.VModel],
        predicate: types.LookupKey,
    ) -> None:
        registry.store_model(envelope_model(migration_settings, model))
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
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        model: type[types.VModel],
        predicate: types.LookupKey,
    ) -> None:
        registry.store_model(envelope_model(migration_settings, model))
        assert predicate not in registry

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
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        model: type[types.VModel],
    ) -> None:
        registry.store_model(envelope_model(migration_settings, model))
        with pytest.raises(ModelAlreadyRegisteredError, match="already registered"):
            registry.store_model(envelope_model(migration_settings, model))

    @pytest.mark.parametrize(
        "registry, model, query, expected",
        [
            (
                Registry[semver.Version](),
                UserV1,
                ModelQuery[semver.Version](("User", VersionedModel.of("1.0.0"))),
                True,
            ),
            (
                Registry[semver.Version](),
                UserV123,
                ModelQuery[semver.Version](("User", VersionedModel.of("1.2.3"))),
                True,
            ),
            (
                Registry[pendulum.Date](),
                UserV20251231,
                ModelQuery[pendulum.Date](("User", VersionedModel.of("2025-12-31"))),
                True,
            ),
        ],
    )
    def test_store_backward_compatible_model(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        model: type[types.VModel],
        query: ModelQuery[types.VersionValue],
        expected: bool,
    ) -> None:
        version = envelope_model(migration_settings, model)
        registry.store_model(version, backward_compatible=expected)

        assert registry.is_backward_compatible(version.version) is expected

    @pytest.mark.parametrize(
        "registry, model",
        [
            (Registry[semver.Version](), UserV1),
            (Registry[pendulum.Date](), UserV20251231),
        ],
    )
    def test_remove_model(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        model: type[types.VModel],
    ) -> None:
        version = envelope_model(migration_settings, model)
        registry.store_model(version)
        assert version.version in registry
        registry.remove_model(version.version)
        assert version.version not in registry

    def test_remove_nonexistent_raises(
        self, migration_settings: MigrationSettings
    ) -> None:
        registry = Registry[semver.Version]()
        with pytest.raises(RegistryError, match="is not registered"):
            registry.remove_model(envelope_model(migration_settings, UserV1).version)

    @pytest.mark.parametrize(
        "registry, models",
        [
            (Registry[semver.Version](), [UserV1, UserV2]),
            (Registry[pendulum.Date](), [UserV20250310, UserV20251231]),
        ],
    )
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

        registry.store_migration((versions[0], versions[1]), _noop)

        with pytest.raises(RegistryError, match="referenced by migrations"):
            registry.remove_model(versions[0].version)

    def test_registry_model_cleanup(
        self, migration_settings: MigrationSettings
    ) -> None:
        version = envelope_model(migration_settings, UserV1)
        registry = Registry[semver.Version]()
        registry.store_model(version)
        registry.clear_models()
        assert version.version not in registry


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
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(versioning_settings, model) for model in models]
        for v in versions:
            registry.store_model(v)

        def _migrate(data: dict) -> dict:
            return data

        registry.store_migration((versions[0], versions[1]), _migrate)
        assert registry.get_migration((versions[0], versions[1])) is _migrate

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
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ):
        versions = [envelope_model(versioning_settings, m) for m in models]
        registry.store_model(versions[0])
        with pytest.raises(MigrationNotFoundError):
            migration_key = (versions[0], versions[1])
            registry.store_migration(migration_key, print)

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
            [Registry[pendulum.Date](), [UserV20250310, UserV20251231]],
        ],
    )
    def test_register_migration_dups(
        self,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ):
        versions = [envelope_model(versioning_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        def _migrate(data: dict) -> dict:
            return data

        registry.store_migration((versions[0], versions[1]), _migrate)
        with pytest.raises(MigrationAlreadyRegisteredError):
            registry.store_migration((versions[0], versions[1]), _migrate)

    def test_get_nonexistent_raises(
        self, versioning_settings: VersioningSettings
    ) -> None:
        registry = Registry[semver.Version]()
        versions = [
            envelope_model(versioning_settings, m) for m in [UserV1, UserV2, UserV3]
        ]
        for v in versions:
            registry.store_model(v)

        with pytest.raises(MigrationNotFoundError):
            migration_key = (versions[0], versions[1])
            registry.get_migration(migration_key)

    @pytest.mark.parametrize(
        "registry, models, lookup_key",
        [
            [
                Registry[semver.Version](),
                [UserV1, UserV2],
                (UserV1, UserV2),
            ],
            [
                Registry[pendulum.Date](),
                [UserV20250310, UserV20251231],
                (UserV20250310, UserV20251231),
            ],
            [
                Registry[semver.Version](),
                [UserV1, UserV3],
                (
                    ("User", VersionedModel.of("1.0.0")),
                    ("User", VersionedModel.of("3.0.0")),
                ),
            ],
        ],
    )
    def test_remove_migration(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
        lookup_key: types.MigrationKey,
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        def _migrate(data: dict) -> dict:
            return data

        migration_key = (versions[0], versions[1])
        registry.store_migration(migration_key, _migrate)
        registry.remove_migration(lookup_key)

        with pytest.raises(MigrationNotFoundError):
            registry.get_migration(migration_key)


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
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        hook = MigrationHook()
        registry.store_migration((versions[0], versions[1]), print)
        registry.add_hook((versions[0], versions[1]), hook)
        assert registry.get_hooks((versions[0], versions[1])) == [hook]

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
        ],
    )
    def test_raise_getting_no_registered_hooks(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        with pytest.raises(RegistryError):
            registry.get_hooks((versions[0], versions[1]))

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
        ],
    )
    def test_remove_single_hook(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        hook1 = MigrationHook()
        hook2 = MigrationHook()
        registry.store_migration((versions[0], versions[1]), print)
        registry.add_hook((versions[0], versions[1]), hook1)
        registry.add_hook((versions[0], versions[1]), hook2)
        registry.remove_hook((versions[0], versions[1]), hook1)

        assert registry.get_hooks((versions[0], versions[1])) == [hook2]

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
        ],
    )
    def test_remove_all_hooks_for_key(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        registry.store_migration((versions[0], versions[1]), print)
        registry.add_hook((versions[0], versions[1]), MigrationHook())
        registry.add_hook((versions[0], versions[1]), MigrationHook())
        registry.remove_hook((versions[0], versions[1]))  # hook is None → remove all
        with pytest.raises(RegistryError):
            registry.get_hooks((versions[0], versions[1]))

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
        ],
    )
    def test_remove_nonexistent_hook_raises(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        registry.store_migration((versions[0], versions[1]), print)
        with pytest.raises(RegistryError):
            registry.remove_hook((versions[0], versions[1]), MigrationHook())

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
        ],
    )
    def test_clear_all_hooks(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        registry.store_migration((versions[0], versions[1]), print)
        registry.add_hook((versions[0], versions[1]), MigrationHook())
        registry.add_hook((versions[0], versions[1]), MigrationHook())
        assert len(registry.get_hooks((versions[0], versions[1]))) == 2
        registry.clear_hooks((versions[0], versions[1]))
        with pytest.raises(RegistryError):
            registry.get_hooks((versions[0], versions[1]))

    @pytest.mark.parametrize(
        "registry, models",
        [
            [Registry[semver.Version](), [UserV1, UserV2]],
            [Registry[pendulum.Date](), [UserV20250310, UserV20260228]],
        ],
    )
    def test_clear_hooks_for_key(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue],
        models: list[type[types.VModel]],
    ) -> None:
        versions = [envelope_model(migration_settings, m) for m in models]
        for v in versions:
            registry.store_model(v)

        registry.store_migration((versions[0], versions[1]), print)
        registry.add_hook((versions[0], versions[1]), MigrationHook())
        registry.clear_hooks((versions[0], versions[1]))
        with pytest.raises(RegistryError):
            registry.get_hooks((versions[0], versions[1]))
