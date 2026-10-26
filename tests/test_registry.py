"""Tests for Registry: model and migration registration.

Most behaviors are exercised for both the semver (pydantic) and chrono/JSON
(``JsonSchemaModelAdapter`` + ``pendulum.Date``) strategies.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pendulum
import pytest
import semver
from pydantic import BaseModel

from pyverge import types
from pyverge.core import (
    MaxDepthExceededError,
    MigrationContext,
    PayloadValidationError,
)
from pyverge.engine import Engine
from pyverge.execution import MigrationHook
from pyverge.execution.extractors import (
    CompositeExtractor,
    ContainerExtractor,
    SchemaFieldsExtractor,
)
from pyverge.export import ManifestDiff
from pyverge.jgf import JgfExporter, JgfImporter
from pyverge.providers import JsonSchemaModelAdapter, PydanticModelAdapter
from pyverge.providers.types import (
    ModelHandle,
)
from pyverge.registry import InMemoryCatalog, Registry
from pyverge.registry.errors import (
    CatalogError,
    GraphLockedError,
    MigrationConflictError,
    MigrationNotFoundError,
    MigrationPathError,
    ModelAlreadyRegisteredError,
    ModelConflictError,
    ModelNotFoundError,
)
from pyverge.registry.types import PathCatalog
from pyverge.settings import VersioningSettings
from pyverge.versioning import (
    EdgeKey,
    FieldDescriptor,
    JgfNode,
    TypeRef,
    VersionKey,
    VersionNode,
    default_content_hasher,
)
from pyverge.versioning.errors import BackwardCompatibilityError
from tests.examples.json import (
    ADDRESS_V1_0_0,
    ADDRESS_V2_0_0,
    ADDRESS_V3_0_0,
    PERSON_V1_0_0,
    USER_V0_1_1_DEV_7,
    USER_V1_0_0,
    USER_V1_2_3,
    USER_V2_0_0,
    USER_V2025_01_01,
    USER_V2025_03_10,
    USER_V2025_12_31,
)
from tests.examples.pydantic.semver import (
    UserV011Dev7,
    UserV1,
    UserV2,
    UserV3,
    UserV200Beta1,
    migrate_v1_to_v2,
)
from tests.examples.pydantic.semver_nested import (
    AddressV1,
    AddressV2,
    AddressV3,
    PersonV1,
    PersonV2,
)
from tests.utils import edge_from_models, envelope_model, meta_versionable


class TestModel:
    @pytest.mark.parametrize(
        "model_adapter, registry, model",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV200Beta1], []],
                UserV200Beta1,
                id="semver_user_latest",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "date_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [],
                ],
                USER_V2025_01_01,
                id="json_schema_unsorted_models",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_get_model(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        version = envelope_model(model_adapter, versioning_settings, model)
        assert registry.get_model(version).model is version.model

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV3, UserV1, UserV2], []],
                [UserV3, UserV1, UserV2],
                id="semver_unsorted_models",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [USER_V1_0_0, USER_V0_1_1_DEV_7, USER_V1_2_3],
                    [],
                ],
                [USER_V1_0_0, USER_V0_1_1_DEV_7, USER_V1_2_3],
                id="json_schema_unsorted_models",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_versions_sorted(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, cls) for cls in models
        ]
        assert registry.versions == sorted(versions)

    @pytest.mark.parametrize(
        "model_adapter, registry, expected",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [], []],
                [],
                id="empty",
            ),
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV2, AddressV1, UserV1],
                    [((UserV1, UserV2), migrate_v1_to_v2)],
                ],
                ["Address", "User"],
                id="with_and_without_migrations",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_entities(
        self,
        registry: Registry[types.VersionValue],
        expected: list[str],
    ) -> None:
        assert registry.entities == expected

    @pytest.mark.parametrize(
        "model_adapter, registry",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV1, AddressV1], []],
                id="semver",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_entities_drop_a_removed_kind(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
    ) -> None:
        registry.remove_model(
            envelope_model(model_adapter, versioning_settings, AddressV1)
        )
        assert registry.entities == ["User"]

    @pytest.mark.parametrize(
        "model_adapter, registry, latest",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV3, UserV1, UserV200Beta1], []],
                UserV3,
                id="semver_latest_v3",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [USER_V1_2_3, USER_V0_1_1_DEV_7, USER_V1_0_0],
                    [],
                ],
                USER_V1_2_3,
                id="semver_latest_v1",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_latest(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        latest: ModelHandle,
    ) -> None:
        version = envelope_model(model_adapter, versioning_settings, latest)
        assert registry.latest(version.version[0]).model == version.model

    @pytest.mark.parametrize(
        "model_adapter, registry, key",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [], []],
                ("User", "3.0.0"),
                id="semver_user_3_0_0",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [pendulum.Date, "json_chrono_test", [], []],
                ("User", "2025-03-10"),
                id="json_chrono_get_nonexistent_model",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_get_nonexistent_model_raises(
        self,
        registry: Registry[types.VersionValue],
        key: types.ModelVersionKey,
    ) -> None:
        with pytest.raises(ModelNotFoundError, match="not found"):
            registry.get_model(VersionKey(_value=key[1], _kind=key[0]))

    @pytest.mark.parametrize(
        "model_adapter, registry, target",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV1], []],
                UserV3,
                id="semver_registered_v1_target_v3",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [pendulum.Date, "json_chrono_test", [USER_V2025_03_10], []],
                USER_V2025_12_31,
                id="json_chrono_registered_2025_03_10_target_2025_12_31",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_get_nonexistent_model_by_class_raises(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        target: ModelHandle,
    ) -> None:
        with pytest.raises(ModelNotFoundError):
            registry.get_model(
                envelope_model(model_adapter, versioning_settings, target)
            )

    @pytest.mark.parametrize(
        "model_adapter, registry, predicate",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV1], []],
                VersionKey(
                    _value=semver.Version.parse("1.0.0"),
                    _kind="User",
                ),
                id="semver_version_node_v1",
            ),
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV011Dev7], []],
                VersionKey(
                    _value=semver.Version.parse("0.1.1+dev.7"),
                    _kind="User",
                ),
                id="semver_version_node_dev",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [pendulum.Date, "json_chrono_test", [USER_V2025_03_10], []],
                VersionKey(
                    _value=pendulum.Date(2025, 3, 10),
                    _kind="User",
                ),
                id="json_chrono_version_node",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_model_contains(
        self,
        registry: Registry[types.VersionValue],
        predicate: types.LookupKey,
    ) -> None:
        assert predicate in registry

    @pytest.mark.parametrize(
        "model_adapter, registry, model",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV1], []],
                UserV3,
                id="semver_model_v1_predicate_v3",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_model_class_not_in_registry(
        self,
        registry: Registry[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        with pytest.raises(ModelNotFoundError):
            registry.get_model_by_handle(model)

    @pytest.mark.parametrize(
        "model_adapter, registry",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [], []],
                id="semver_empty_registry",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [pendulum.Date, "json_chrono_test", [], []],
                id="json_chrono_empty_registry",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_latest_model_empty_raises(
        self,
        registry: Registry[types.VersionValue],
    ) -> None:
        with pytest.raises(CatalogError):
            registry.latest("User")

    @pytest.mark.parametrize(
        "model_adapter, registry, model",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV200Beta1], []],
                UserV200Beta1,
                id="semver_user_v200beta1",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [pendulum.Date, "json_chrono_test", [USER_V2025_03_10], []],
                USER_V2025_03_10,
                id="json_chrono_store_duplicate",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_store_duplicate_raises(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        """The registry is a store: a duplicate registration raises.

        Reconciliation (identical-surface no-op) is the engine's concern.
        The fixture already registered *model*.
        """
        with pytest.raises(ModelAlreadyRegisteredError, match="already registered"):
            registry.store_model(
                envelope_model(model_adapter, versioning_settings, model)
            )

    @pytest.mark.parametrize(
        "model_adapter, registry, model",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV1], []],
                UserV1,
                id="semver_user_v1",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [pendulum.Date, "json_chrono_test", [USER_V2025_03_10], []],
                USER_V2025_03_10,
                id="json_chrono_remove_model",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_remove_model(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        version = envelope_model(model_adapter, versioning_settings, model)
        assert version in registry
        registry.remove_model(version)
        with pytest.raises(ModelNotFoundError):
            registry.get_model(version)

    @pytest.mark.parametrize(
        "model_adapter, registry, model",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [], []],
                UserV1,
                id="semver_user_v1_missing",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [pendulum.Date, "json_chrono_test", [], []],
                USER_V2025_03_10,
                id="json_chrono_user_2025_03_10_missing",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_remove_nonexistent_raises(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        with pytest.raises(CatalogError, match="is not registered"):
            registry.remove_model(
                envelope_model(model_adapter, versioning_settings, model)
            )

    @pytest.mark.parametrize(
        "model_adapter, registry, model",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV1], []],
                UserV1,
                id="semver_user_v1",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [pendulum.Date, "json_chrono_test", [USER_V2025_03_10], []],
                USER_V2025_03_10,
                id="json_chrono_model_cleanup",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_registry_model_cleanup(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        version = envelope_model(model_adapter, versioning_settings, model)
        registry.clear_models()
        with pytest.raises(ModelNotFoundError):
            registry.get_model(version)

    @pytest.mark.parametrize(
        "model_adapter, registry, version",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [], []],
                "0.1.0",
                id="semver_meta_0_1_0",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [pendulum.Date, "json_chrono_test", [], []],
                "2025-03-10",
                id="json_chrono_meta_2025_03_10",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_meta_key_is_lookup_only(
        self,
        model_adapter: types.ModelAdapter,
        registry: Registry[types.VersionValue],
        version: str,
    ) -> None:
        """A meta key is a search value; it is never stored as a node."""
        key = meta_versionable(model_adapter, "User", version)

        assert registry.find_model(key) is None
        assert key not in registry
        assert registry.models("User") == frozenset()

    @pytest.mark.parametrize(
        "model_adapter, registry, meta_versions, expected",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV1], []],
                ["0.1.0", "0.2.0"],
                ["0.1.0", "0.2.0", "1.0.0"],
                id="semver_meta_and_real",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [pendulum.Date, "json_chrono_test", [USER_V2025_03_10], []],
                ["2025-01-01", "2025-12-31"],
                ["2025-01-01", "2025-03-10", "2025-12-31"],
                id="json_chrono_meta_and_real",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_meta_and_real_versions_order_together(
        self,
        model_adapter: types.ModelAdapter,
        registry: Registry[types.VersionValue],
        meta_versions: list[str],
        expected: list[str],
    ) -> None:
        """Keys and real nodes order together by version value within a kind."""
        keys = [meta_versionable(model_adapter, "User", v) for v in meta_versions]
        versions = [
            str(v.version[1]) for v in sorted([*registry.kind_versions("User"), *keys])
        ]
        assert versions == expected

    @pytest.mark.parametrize(
        "model_adapter, registry, model",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV1], []],
                UserV1,
                id="semver_user_v1",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_copy_preserves_model_class_lookup(
        self,
        registry: Registry[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        """A copied registry keeps class-based lookups."""
        clone = registry.copy()
        assert clone.get_model_by_handle(model).model is model


class TestMigration:
    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV1, UserV2], []],
                [UserV1, UserV2],
                id="semver_user_v1_v2",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_user_2025_01_01_2025_03_10",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_store_and_get(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        def _migrate(data: dict, context: MigrationContext | None = None) -> dict:
            return data

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=_migrate
        )
        registry.store_migration(edge)
        assert registry.get_migration(EdgeKey.from_version_edge(edge)).func is edge.func

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV1], []],
                [UserV1, UserV2],
                id="semver_user_v1_v2_missing_version",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [pendulum.Date, "json_chrono_test", [USER_V2025_01_01], []],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_user_2025_01_01_2025_03_10_missing_version",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_register_migration_with_missing_version(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        with pytest.raises(MigrationNotFoundError):
            edge = edge_from_models(
                model_adapter,
                versioning_settings,
                models[0],
                models[1],
                func=lambda d, _: d,
            )
            registry.store_migration(edge)

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                id="semver_user_v1_v2_duplicate",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_user_2025_01_01_2025_03_10_duplicate",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_register_migration_dups(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        def _migrate(data: dict, context: MigrationContext | None = None) -> dict:
            return data

        edge = edge_from_models(
            model_adapter, versioning_settings, models[0], models[1], func=_migrate
        )
        with pytest.raises(MigrationConflictError):
            registry.store_migration(edge)

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV1, UserV2], []],
                [UserV1, UserV2],
                id="semver_user_v1_v2_nonexistent",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_user_2025_01_01_2025_03_10_nonexistent",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_get_nonexistent_raises(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        with pytest.raises(MigrationNotFoundError):
            fake_key = edge_from_models(
                model_adapter,
                versioning_settings,
                models[0],
                models[1],
                func=lambda data, _: data,
            )
            registry.get_migration(EdgeKey.from_version_edge(fake_key))

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                id="semver_user_v1_v2",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_user_2025_01_01_2025_03_10",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_remove_migration(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        key = edge_from_models(
            model_adapter,
            versioning_settings,
            models[0],
            models[1],
            func=lambda data, _: data,
        )
        registry.remove_migration(EdgeKey.from_version_edge(key))

        with pytest.raises(MigrationNotFoundError):
            registry.get_migration(EdgeKey.from_version_edge(key))


class TestHooks:
    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                id="semver_user_v1_v2",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_user_2025_01_01_2025_03_10",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_add_and_get_hook(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        edge = edge_from_models(
            model_adapter,
            versioning_settings,
            models[0],
            models[1],
            func=lambda d, _: d,
        )
        key = EdgeKey.from_version_edge(edge)
        hook = MagicMock(spec=MigrationHook)
        registry.add_hook(key, hook)
        assert registry.get_hooks(key) == [hook]

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                id="semver_no_hooks",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_no_hooks",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_get_hooks_returns_empty_when_none_registered(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        edge = edge_from_models(
            model_adapter,
            versioning_settings,
            models[0],
            models[1],
            func=lambda d, _: d,
        )
        assert registry.get_hooks(edge) == []

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                id="semver_remove_one_hook",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_remove_one_hook",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_remove_single_hook(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        hook1 = MagicMock(spec=MigrationHook)
        hook2 = MagicMock(spec=MigrationHook)
        edge = edge_from_models(
            model_adapter,
            versioning_settings,
            models[0],
            models[1],
            func=lambda d, _: d,
        )
        key = EdgeKey.from_version_edge(edge)
        for h in [hook1, hook2]:
            registry.add_hook(edge, h)
        registry.remove_hook(key, hook1)

        assert registry.get_hooks(key) == [hook2]

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                id="semver_remove_all_hooks",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_remove_all_hooks",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_remove_all_hooks_for_key(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        edge = edge_from_models(
            model_adapter,
            versioning_settings,
            models[0],
            models[1],
            func=lambda d, _: d,
        )
        registry.add_hook(edge, MagicMock(spec=MigrationHook))
        registry.add_hook(edge, MagicMock(spec=MigrationHook))
        registry.remove_hook(edge)  # hook is None → remove all
        assert registry.get_hooks(edge) == []

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                id="semver_missing_hook",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_missing_hook",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_remove_nonexistent_hook_raises(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        edge = edge_from_models(
            model_adapter,
            versioning_settings,
            models[0],
            models[1],
            func=lambda d, _: d,
        )
        key = EdgeKey.from_version_edge(edge)
        with pytest.raises(CatalogError):
            registry.remove_hook(key, MagicMock(spec=MigrationHook))

    @pytest.mark.parametrize(
        "model_adapter, registry, models, expected_amount",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                2,
                id="semver_two_hooks",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                2,
                id="json_chrono_two_hooks",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_clear_all_hooks(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
        expected_amount: int,
    ) -> None:
        edge = edge_from_models(
            model_adapter,
            versioning_settings,
            models[0],
            models[1],
            func=lambda d, _: d,
        )
        key = EdgeKey.from_version_edge(edge)
        registry.add_hook(edge, MagicMock(spec=MigrationHook))
        registry.add_hook(edge, MagicMock(spec=MigrationHook))
        assert len(registry.get_hooks(key)) == expected_amount
        registry.clear_hooks(key)
        assert registry.get_hooks(key) == []

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                id="semver_clear_key_hooks",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_clear_key_hooks",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_clear_hooks_for_key(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        edge = edge_from_models(
            model_adapter,
            versioning_settings,
            models[0],
            models[1],
            func=lambda d, _: d,
        )
        key = EdgeKey.from_version_edge(edge)
        registry.add_hook(key, MagicMock(spec=MigrationHook))
        registry.clear_hooks(key)
        assert registry.get_hooks(key) == []


class TestVersionEdgeIndex:
    """Inverted index: version -> set of migration edges touching it."""

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV1, UserV2], []],
                [UserV1, UserV2],
                id="semver_empty_index",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_empty_index",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_migrations_of_empty(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        assert registry.migrations_of(versions[0]) == frozenset()

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2, UserV3],
                    [
                        ((UserV1, UserV2), lambda d, _: d),
                        ((UserV2, UserV3), lambda d, _: d),
                    ],
                ],
                [UserV1, UserV2, UserV3],
                id="semver_chain_v1_v2_v3",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10, USER_V2025_12_31],
                    [
                        ((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d),
                        ((USER_V2025_03_10, USER_V2025_12_31), lambda d, _: d),
                    ],
                ],
                [USER_V2025_01_01, USER_V2025_03_10, USER_V2025_12_31],
                id="json_chrono_chain",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_migrations_of_source_and_target(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        e1 = edge_from_models(
            model_adapter,
            versioning_settings,
            models[0],
            models[1],
            func=lambda d, _: d,
        )
        e2 = edge_from_models(
            model_adapter,
            versioning_settings,
            models[1],
            models[2],
            func=lambda d, _: d,
        )

        assert registry.migrations_of(versions[0]) == {e1}
        assert registry.migrations_of(versions[1]) == {e1, e2}
        assert registry.migrations_of(versions[2]) == {e2}

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                id="semver_node_key",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_node_key",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_migrations_of_accepts_node_key(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        """VersionNode keys hit the same bucket."""
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]

        assert registry.migrations_of(versions[0]) == registry.migrations_of(
            versions[0]
        )

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2, UserV3],
                    [
                        ((UserV1, UserV2), lambda d, _: d),
                        ((UserV2, UserV3), lambda d, _: d),
                    ],
                ],
                [UserV1, UserV2, UserV3],
                id="semver_remove_updates_index",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10, USER_V2025_12_31],
                    [
                        ((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d),
                        ((USER_V2025_03_10, USER_V2025_12_31), lambda d, _: d),
                    ],
                ],
                [USER_V2025_01_01, USER_V2025_03_10, USER_V2025_12_31],
                id="json_chrono_remove_updates_index",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_index_updated_on_remove_migration(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        e1 = edge_from_models(
            model_adapter,
            versioning_settings,
            models[0],
            models[1],
            func=lambda d, _: d,
        )
        e2 = edge_from_models(
            model_adapter,
            versioning_settings,
            models[1],
            models[2],
            func=lambda d, _: d,
        )

        registry.remove_migration(EdgeKey.from_version_edge(e1))

        assert registry.migrations_of(versions[0]) == (frozenset())
        assert registry.migrations_of(versions[1]) == {e2}

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                id="semver_clear_index",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_clear_index",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_index_cleared_on_clear_migrations(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]

        registry.clear_migrations()

        assert registry.migrations_of(versions[0]) == (frozenset())

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                id="semver_copy_index",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_copy_index",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_copy_preserves_index_independently(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        edge = edge_from_models(
            model_adapter,
            versioning_settings,
            models[0],
            models[1],
            func=lambda d, _: d,
        )

        clone = registry.copy()
        key = versions[0]
        assert clone.migrations_of(key) == registry.migrations_of(key)

        clone.remove_migration(EdgeKey.from_version_edge(edge))
        assert clone.migrations_of(key) == frozenset()
        assert registry.migrations_of(key) == {edge}

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                id="semver_referenced_model",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_referenced_model",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_remove_model_raises_when_referenced(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]

        with pytest.raises(CatalogError, match="referenced by migrations") as exc:
            registry.remove_model(versions[0])
        assert "→" in str(exc.value)

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                id="semver_remove_after_migration",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_remove_after_migration",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_remove_model_allowed_after_migration_removed(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        edge = edge_from_models(
            model_adapter,
            versioning_settings,
            models[0],
            models[1],
            func=lambda d, _: d,
        )
        registry.remove_migration(EdgeKey.from_version_edge(edge))

        registry.remove_model(versions[0])
        with pytest.raises(ModelNotFoundError):
            registry.get_model(versions[0])


class TestEdgePairLookup:
    """Direct (from, to) pair index for point lookups on edges."""

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV3, UserV1, UserV2], []],
                [UserV3, UserV1, UserV2],
                id="semver_kind_versions",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_12_31, USER_V2025_01_01, USER_V2025_03_10],
                    [],
                ],
                [USER_V2025_12_31, USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_kind_versions",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_kind_versions_sorted(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        assert registry.kind_versions(versions[0].kind) == sorted(versions)

    @pytest.mark.parametrize(
        "model_adapter, registry",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [], []],
                id="semver_unknown_kind",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [pendulum.Date, "json_chrono_test", [], []],
                id="json_chrono_unknown_kind",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_kind_versions_unknown_returns_empty(
        self,
        registry: Registry[types.VersionValue],
    ) -> None:
        assert registry.kind_versions("Nope") == []

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2, UserV3],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2, UserV3],
                id="semver_pair_lookup",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10, USER_V2025_12_31],
                    [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
                ],
                [USER_V2025_01_01, USER_V2025_03_10, USER_V2025_12_31],
                id="json_chrono_pair_lookup",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_has_migration(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]

        key12 = EdgeKey.from_pair(versions[0], versions[1])
        key13 = EdgeKey.from_pair(versions[0], versions[2])
        assert registry.has_migration(key12) is True
        assert registry.has_migration(key13) is False
        # VersionNode endpoints hit the same index entry
        assert (
            registry.has_migration(
                EdgeKey.from_pair(
                    versions[0],
                    versions[1],
                )
            )
            is True
        )

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV1, UserV2], []],
                [UserV1, UserV2],
                id="semver_get_by_pair",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_get_by_pair",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_get_migration_by_pair(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        edge = edge_from_models(
            model_adapter,
            versioning_settings,
            models[0],
            models[1],
            func=lambda d, _: d,
        )
        registry.store_migration(edge)

        key = EdgeKey.from_pair(versions[0], versions[1])
        found = registry.get_migration_by_edge(key)
        assert found.func is edge.func

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV1, UserV2], []],
                [UserV1, UserV2],
                id="semver_pair_missing",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_pair_missing",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_get_migration_by_pair_missing_raises(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]

        key = EdgeKey.from_pair(versions[0], versions[1])
        with pytest.raises(MigrationNotFoundError):
            registry.get_migration_by_edge(key)

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "validation_semver", [UserV1, UserV2], []],
                [UserV1, UserV2],
                id="semver_backward_validation",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    semver.Version,
                    "validation_json_semver",
                    [USER_V1_0_0, USER_V2_0_0],
                    [],
                ],
                [USER_V1_0_0, USER_V2_0_0],
                id="json_semver_backward_validation",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_backward_compatible_declaration_is_validated(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]

        engine.store_migration(
            (versions[0], versions[1]),
            lambda d, _: d,
            backward_compatible=True,
        )

        with pytest.raises(BackwardCompatibilityError):
            engine.store_migration(
                (versions[1], versions[0]),
                lambda d, _: d,
                backward_compatible=True,
            )

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [], []],
                [UserV1, UserV2],
                id="pydantic_edge_missing",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [pendulum.Date, "date_test", [], []],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_schema_edge_missing",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_get_migration_by_edge_missing_raises(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        models: list[ModelHandle],
        registry: Registry[types.VersionValue],
    ) -> None:
        pair = [
            envelope_model(model_adapter, versioning_settings, model)
            for model in models
        ]
        with pytest.raises(MigrationNotFoundError):
            registry.get_migration_by_edge(EdgeKey.from_pair(*pair))

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                id="semver_pair_remove",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_pair_remove",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_pair_index_updated_on_remove(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        edge = edge_from_models(
            model_adapter,
            versioning_settings,
            models[0],
            models[1],
            func=lambda d, _: d,
        )
        registry.remove_migration(EdgeKey.from_version_edge(edge))

        key = EdgeKey.from_pair(versions[0], versions[1])
        assert registry.has_migration(key) is False

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                id="semver_pair_clear",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_pair_clear",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_pair_index_cleared_on_clear_migrations(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]

        registry.clear_migrations()

        key = EdgeKey.from_pair(versions[0], versions[1])
        assert registry.has_migration(key) is False

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                id="semver_pair_copy",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_pair_copy",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_pair_index_copy_independent(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        edge = edge_from_models(
            model_adapter,
            versioning_settings,
            models[0],
            models[1],
            func=lambda d, _: d,
        )

        clone = registry.copy()
        key = EdgeKey.from_pair(versions[0], versions[1])
        assert clone.has_migration(key) is True

        clone.remove_migration(EdgeKey.from_version_edge(edge))
        assert clone.has_migration(key) is False
        assert registry.has_migration(key) is True


class TestMigrationHookGuard:
    """A migration with registered hooks cannot be removed directly."""

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV1, UserV2], []],
                [UserV1, UserV2],
                id="semver_hooks_present",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_hooks_present",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_remove_migration_with_hooks_raises(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        edge = edge_from_models(
            model_adapter,
            versioning_settings,
            models[0],
            models[1],
            func=lambda d, _: d,
        )
        registry.store_migration(edge)
        registry.add_hook(edge, MagicMock(spec=MigrationHook))

        key = EdgeKey.from_version_edge(edge)
        with pytest.raises(CatalogError, match="hooks"):
            registry.remove_migration(key)

        # Migration untouched
        assert registry.get_migration(key).func is edge.func

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                id="semver_hooks_cleared",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "json_chrono_test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
                ],
                [USER_V2025_01_01, USER_V2025_03_10],
                id="json_chrono_hooks_cleared",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_remove_migration_allowed_after_hooks_cleared(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        edge = edge_from_models(
            model_adapter,
            versioning_settings,
            models[0],
            models[1],
            func=lambda d, _: d,
        )
        key = EdgeKey.from_version_edge(edge)
        registry.add_hook(key, MagicMock(spec=MigrationHook))
        registry.clear_hooks(key)

        registry.remove_migration(key)
        with pytest.raises(MigrationNotFoundError):
            registry.get_migration(EdgeKey.from_version_edge(edge))


class TestReferences:
    """A registered model's declared references to other versioned kinds.

    References are read from the model's *declared* field types — every union
    member, transitively — when the model is stored, and cached on the
    ``VersionNode``. Querying them needs no adapter, and a discriminated union
    contributes **all** its members (unlike ``field_model``, which collapses a
    union to its first member).

    The FastMCP adapter uses this to fail fast when a payload could carry a
    versioned child the graph cannot converge: the walker silently skips
    unregistered kinds, so a declared-but-unregistered reference is a latent
    runtime bug the graph can catch up front.

    Both model providers are exercised. Pydantic declares a discriminated union
    (``AddressV1 | AddressV2 | AddressV3``); JSON declares the same via ``oneOf``
    over ``$ref`` definitions. Both must surface all three versions.
    """

    #: The three Address versions a Person references, parsed.
    ADDRESS_VERSIONS = frozenset(
        {
            ("Address", semver.Version(1, 0, 0)),
            ("Address", semver.Version(2, 0, 0)),
            ("Address", semver.Version(3, 0, 0)),
        }
    )

    @pytest.mark.parametrize(
        "model_adapter, registry, model, expected",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "nested_test", [PersonV1], []],
                PersonV1,
                ADDRESS_VERSIONS,
                id="pydantic_union_contributes_all_members",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "nested_test", [PERSON_V1_0_0], []],
                PERSON_V1_0_0,
                ADDRESS_VERSIONS,
                id="json_one_of_contributes_all_members",
            ),
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "nested_test", [PersonV2], []],
                PersonV2,
                ADDRESS_VERSIONS
                | {
                    ("Contact", semver.Version(1, 0, 0)),
                    ("Contact", semver.Version(2, 0, 0)),
                },
                id="pydantic_list_of_union",
            ),
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "nested_test", [AddressV1], []],
                AddressV1,
                frozenset(),
                id="pydantic_leaf_references_nothing",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "nested_test", [ADDRESS_V1_0_0], []],
                ADDRESS_V1_0_0,
                frozenset(),
                id="json_leaf_references_nothing",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_node_references_lists_declared_versions(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: ModelHandle,
        expected: frozenset[types.ModelVersionKey],
    ) -> None:
        node = envelope_model(model_adapter, versioning_settings, model)
        assert node.references == expected

    @pytest.mark.parametrize(
        "model_adapter, registry, model",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "nested_test", [PersonV1], []],
                PersonV1,
                id="pydantic",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "nested_test", [PERSON_V1_0_0], []],
                PERSON_V1_0_0,
                id="json",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_references_are_transitive(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        """Every declared union member is reached, not just the first."""
        node = envelope_model(model_adapter, versioning_settings, model)
        assert {kind for kind, _ in node.references} == {"Address"}
        assert len(node.references) == 3  # noqa: PLR2004

    @pytest.mark.parametrize(
        "model_adapter, registry, model",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "nested_test", [PersonV1], []],
                PersonV1,
                id="pydantic",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "nested_test", [PERSON_V1_0_0], []],
                PERSON_V1_0_0,
                id="json",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_references_survive_copy(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        node = envelope_model(model_adapter, versioning_settings, model)
        copied = registry.copy(name="copy")
        assert copied.get_model(node).references == node.references

    # -- missing_references: the convenience the consumer actually wants -----

    @pytest.mark.parametrize(
        "model_adapter, registry, model, children",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "nested_test", [PersonV1], []],
                PersonV1,
                (AddressV1, AddressV2, AddressV3),
                id="pydantic",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "nested_test", [PERSON_V1_0_0], []],
                PERSON_V1_0_0,
                (ADDRESS_V1_0_0, ADDRESS_V2_0_0, ADDRESS_V3_0_0),
                id="json",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_missing_references_empty_when_children_registered(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: ModelHandle,
        children: tuple,
    ) -> None:
        node = envelope_model(model_adapter, versioning_settings, model)
        for child in children:
            registry.store_model(model_adapter.versionable(child))
        assert registry.missing_references(node) == frozenset()

    @pytest.mark.parametrize(
        "model_adapter, registry, model",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "nested_test", [PersonV1], []],
                PersonV1,
                id="pydantic",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "nested_test", [PERSON_V1_0_0], []],
                PERSON_V1_0_0,
                id="json",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_missing_references_reports_all_when_child_absent(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        node = envelope_model(model_adapter, versioning_settings, model)
        assert registry.missing_references(node) == self.ADDRESS_VERSIONS

    @pytest.mark.parametrize(
        "model_adapter, registry, model, one_child",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "nested_test", [PersonV1], []],
                PersonV1,
                AddressV1,
                id="pydantic",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "nested_test", [PERSON_V1_0_0], []],
                PERSON_V1_0_0,
                ADDRESS_V1_0_0,
                id="json",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_missing_references_reports_only_absent_versions(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: ModelHandle,
        one_child: object,
    ) -> None:
        """Registering one ``Address`` version leaves the other two missing."""
        node = envelope_model(model_adapter, versioning_settings, model)
        registry.store_model(model_adapter.versionable(one_child))  # ty: ignore[invalid-argument-type]
        assert registry.missing_references(node) == frozenset(
            {
                ("Address", semver.Version(2, 0, 0)),
                ("Address", semver.Version(3, 0, 0)),
            }
        )

    def test_missing_references_unknown_node_raises(
        self,
        model_adapter: types.ModelAdapter,
        registry: Registry[types.VersionValue],
    ) -> None:
        unregistered = meta_versionable(model_adapter, "User", "9.9.9")
        with pytest.raises(ModelNotFoundError):
            registry.missing_references(unregistered)


class TestNeutralGraphOps:
    """Registry owns low-level graph traversal and reconciliation."""

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2, UserV3],
                    [
                        ((UserV1, UserV2), lambda d, _: d),
                        ((UserV2, UserV3), lambda d, _: d),
                    ],
                ],
                [UserV1, UserV2, UserV3],
                id="pydantic_semver",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_migration_path_forward_and_backward(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        forward = registry.migration_path(versions[0], versions[2])
        assert forward == [(versions[0], versions[1]), (versions[1], versions[2])]
        assert registry.migration_path(versions[0], versions[0]) == []
        with pytest.raises(MigrationPathError):
            registry.migration_path(versions[2], versions[0])

    def test_migration_path_unregistered_raises(
        self,
        model_adapter: types.ModelAdapter,
        registry: Registry[types.VersionValue],
    ) -> None:
        missing = meta_versionable(model_adapter, "User", "9.9.9")
        other = meta_versionable(model_adapter, "User", "9.9.8")
        with pytest.raises(MigrationPathError):
            registry.migration_path(missing, other)

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "semver_test",
                    [UserV1, UserV2, UserV3],
                    [
                        ((UserV1, UserV2), lambda d, _: d),
                        ((UserV2, UserV3), lambda d, _: d),
                    ],
                ],
                [UserV1, UserV2, UserV3],
                id="pydantic_semver",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_remove_migration_range_refuses_critical_edge(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [
            envelope_model(model_adapter, versioning_settings, m) for m in models
        ]
        with pytest.raises(CatalogError):
            registry.remove_migration_range(versions[0], versions[2])

    @pytest.mark.parametrize(
        "model_adapter, registry, model",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV1], []],
                UserV1,
                id="pydantic_semver",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_reconcile_identical_is_noop(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        again = registry.reconcile_model(
            envelope_model(model_adapter, versioning_settings, model)
        )
        assert registry.get_model(again) is again

    @pytest.mark.parametrize(
        "model_adapter, registry, model",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV1], []],
                UserV1,
                id="pydantic_semver",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_reconcile_conflicting_surface_raises(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        registered = envelope_model(model_adapter, versioning_settings, model)
        incoming = registered.with_fields(
            FieldDescriptor(name="extra", type_ref=TypeRef.any())
        )
        with pytest.raises(ModelConflictError):
            registry.reconcile_model(incoming)

    @pytest.mark.parametrize(
        "model_adapter, registry, model",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "semver_test", [UserV1], []],
                UserV1,
                id="pydantic_semver",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_handle_lookup_and_removal(
        self,
        registry: Registry[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        assert registry.get_model_by_handle(model).model is model
        registry.remove_model_by_handle(model)
        with pytest.raises(ModelNotFoundError):
            registry.get_model_by_handle(model)


@pytest.mark.parametrize(
    "model_adapter, registry, models",
    [
        pytest.param(
            PydanticModelAdapter,
            [semver.Version, "idempotent_semver", [UserV1, UserV2], []],
            [UserV1, UserV2],
            id="semver_user_v1_v2_idempotent",
        ),
        pytest.param(
            JsonSchemaModelAdapter,
            [
                pendulum.Date,
                "idempotent_json_chrono",
                [USER_V2025_01_01, USER_V2025_03_10],
                [],
            ],
            [USER_V2025_01_01, USER_V2025_03_10],
            id="json_chrono_user_2025_01_01_2025_03_10_idempotent",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_register_migration_identical_content_is_idempotent(
    model_adapter: types.ModelAdapter,
    versioning_settings: VersioningSettings,
    registry: Registry[types.VersionValue],
    models: list[ModelHandle],
) -> None:
    def migrate(data: dict, context: MigrationContext | None = None) -> dict:
        return data

    edge = edge_from_models(
        model_adapter,
        versioning_settings,
        models[0],
        models[1],
        func=migrate,
    )

    assert registry.store_migration(edge) is migrate
    assert registry.store_migration(edge) is migrate


@pytest.mark.parametrize(
    "model_adapter, registry, models",
    [
        pytest.param(
            PydanticModelAdapter,
            [
                semver.Version,
                "catalog_semver",
                [UserV1, UserV2],
                [((UserV1, UserV2), lambda d, _: d)],
            ],
            [UserV1, UserV2],
            id="semver_catalog",
        ),
        pytest.param(
            JsonSchemaModelAdapter,
            [
                pendulum.Date,
                "catalog_json_chrono",
                [USER_V2025_01_01, USER_V2025_03_10],
                [((USER_V2025_01_01, USER_V2025_03_10), lambda d, _: d)],
            ],
            [USER_V2025_01_01, USER_V2025_03_10],
            id="json_chrono_catalog",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_catalog_exports_jgf_and_imports_nodes(
    model_adapter: types.ModelAdapter,
    registry: Registry[types.VersionValue],
    models: list[ModelHandle],
) -> None:
    exporter = JgfExporter(default_content_hasher())
    document = exporter.export_graph(registry).to_dict()

    assert set(document["graph"]["nodes"]) == {
        node.jgf_id for node in registry.versions
    }
    assert len(document["graph"]["edges"]) == sum(
        len(registry.migrations(kind)) for kind in registry.kinds
    )
    assert exporter.content_hash(registry) == exporter.content_hash(registry)
    assert not ManifestDiff.compare(document, document).changed

    nodes_by_id = {
        model_adapter.versionable(model).jgf_id: model_adapter.versionable(model)
        for model in models
    }

    class _Resolver:
        def resolve(self, node: JgfNode) -> types.VersionNode:
            return nodes_by_id[node.id]

    imported = InMemoryCatalog(name="imported", hasher=default_content_hasher())
    node_document = {"graph": dict(document["graph"])}
    node_document["graph"].pop("edges")
    imported_graph = JgfImporter(_Resolver()).import_graph(
        node_document,
        models=imported,
    )

    assert {node.id for node in imported_graph.nodes} == set(nodes_by_id)
    assert {node.jgf_id for node in imported.versions} == set(nodes_by_id)


@pytest.mark.parametrize(
    "model_adapter, registry, models",
    [
        pytest.param(
            PydanticModelAdapter,
            [semver.Version, "locked_semver", [UserV1, UserV2], []],
            [UserV1, UserV2],
            id="semver_locked",
        ),
        pytest.param(
            JsonSchemaModelAdapter,
            [
                pendulum.Date,
                "locked_json_chrono",
                [USER_V2025_01_01, USER_V2025_03_10],
                [],
            ],
            [USER_V2025_01_01, USER_V2025_03_10],
            id="json_chrono_locked",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
def test_catalog_lock_freezes_writes(
    model_adapter: types.ModelAdapter,
    registry: Registry[types.VersionValue],
    models: list[ModelHandle],
) -> None:
    snapshot = registry.lock()

    exporter = JgfExporter(default_content_hasher())
    assert (
        exporter.export_graph(snapshot).to_dict()
        == exporter.export_graph(registry).to_dict()
    )
    with pytest.raises(GraphLockedError):
        registry.store_model(model_adapter.versionable(models[0]))
    with pytest.raises(GraphLockedError):
        snapshot.store_model(model_adapter.versionable(models[0]))


@pytest.mark.parametrize(
    "model_adapter, models",
    [
        pytest.param(
            PydanticModelAdapter,
            [UserV1, UserV2],
            id="semver_index",
        ),
        pytest.param(
            JsonSchemaModelAdapter,
            [USER_V2025_01_01, USER_V2025_03_10],
            id="json_chrono_index",
        ),
    ],
    indirect=["model_adapter"],
)
def test_content_hash_index_tracks_registration(
    model_adapter: types.ModelAdapter,
    versioning_settings: VersioningSettings,
    models: list[ModelHandle],
) -> None:
    catalog = InMemoryCatalog(
        name="indexed",
        hasher=default_content_hasher(),
        index_content_hashes=True,
    )
    nodes = [model_adapter.versionable(model) for model in models]
    for node in nodes:
        catalog.store_model(node)

    edge = edge_from_models(
        model_adapter,
        versioning_settings,
        models[0],
        models[1],
        func=_noop_migration,
    )
    catalog.store_migration(edge)

    key = EdgeKey.from_version_edge(edge)
    assert (
        catalog.find_edge_by_content_hash(edge.content_hash(default_content_hasher()))
        == key
    )

    catalog.remove_migration(key)
    assert (
        catalog.find_edge_by_content_hash(edge.content_hash(default_content_hasher()))
        is None
    )


@pytest.mark.parametrize(
    "model_adapter, models",
    [
        pytest.param(PydanticModelAdapter, [UserV1, UserV2], id="semver_remote"),
        pytest.param(
            JsonSchemaModelAdapter,
            [USER_V2025_01_01, USER_V2025_03_10],
            id="json_chrono_remote",
        ),
    ],
    indirect=["model_adapter"],
)
def test_remote_path_catalog_is_substitutable(
    model_adapter: types.ModelAdapter,
    models: list[ModelHandle],
) -> None:
    source, target = (model_adapter.versionable(model) for model in models)

    class _RemotePathCatalog:
        """A remote adapter that answers path queries without graph download."""

        def migration_path(
            self,
            from_version: types.Versionable,
            to_version: types.Versionable,
        ) -> list[tuple[VersionNode, VersionNode]]:
            if from_version == source and to_version == target:
                return [(source, target)]
            return []

    def resolve_path(
        catalog: PathCatalog,
        from_version: types.Versionable,
        to_version: types.Versionable,
    ) -> list[tuple[VersionNode, VersionNode]]:
        return catalog.migration_path(from_version, to_version)

    assert resolve_path(_RemotePathCatalog(), source, target) == [(source, target)]


def _noop_migration(data: dict, context: Any = None) -> dict:
    return data


class Leaf(BaseModel):
    kind: str = "Leaf"
    version: str = "1.0.0"
    name: str = ""


class Envelope(BaseModel):
    item: Leaf


EXPECTED_ENTRIES = 3


class ListEnvelope(BaseModel):
    items: list[Leaf]


def _extractor() -> tuple[
    Registry[semver.Version], PydanticModelAdapter, CompositeExtractor[semver.Version]
]:
    adapter = PydanticModelAdapter()
    registry = Registry[semver.Version](hasher=default_content_hasher())
    registry.store_model(adapter.versionable(Leaf))
    return registry, adapter, CompositeExtractor(registry, adapter=adapter)


def test_containerless_list_and_depth() -> None:
    _, _, extractor = _extractor()
    payload = {
        "items": [
            {"kind": "Leaf", "version": "1.0.0", "name": "a"},
            {
                "kind": "Leaf",
                "version": "1.0.0",
                "name": "outer",
                "child": {"kind": "Leaf", "version": "1.0.0", "name": "inner"},
            },
        ]
    }
    entries = list(extractor.extract(payload))
    assert len(entries) == EXPECTED_ENTRIES
    with pytest.raises(MaxDepthExceededError):
        list(extractor.extract(payload, max_depth=0))


def test_guided_container_and_list() -> None:
    _, _, extractor = _extractor()
    envelope = Envelope(item={"kind": "Leaf", "version": "1.0.0", "name": "a"})
    entries = list(extractor.extract(envelope.model_dump(), container=Envelope))
    assert len(entries) == 1
    list_envelope = ListEnvelope(items=[{"kind": "Leaf", "version": "1.0.0"}])
    entries = list(
        extractor.extract(list_envelope.model_dump(), container=ListEnvelope)
    )
    assert len(entries) == 1


def test_guided_depth_and_validation_errors() -> None:
    _, _, extractor = _extractor()
    envelope = Envelope(item={"kind": "Leaf", "version": "1.0.0"})
    with pytest.raises(MaxDepthExceededError):
        list(extractor.extract(envelope.model_dump(), container=Envelope, max_depth=0))
    with pytest.raises(PayloadValidationError, match="container validation"):
        list(extractor.extract({"item": "bad"}, container=Envelope))
    with pytest.raises(PayloadValidationError, match="not a recognized"):
        list(extractor.extract({}, container=dict))


def test_specialized_extractor_modes() -> None:
    registry, adapter, _ = _extractor()
    schema = SchemaFieldsExtractor(registry, adapter=adapter)
    assert list(schema.extract({})) == []

    container = ContainerExtractor(registry, adapter=adapter)
    with pytest.raises(PayloadValidationError, match="container validation"):
        list(container.extract({"item": "bad"}, container=Envelope))

    permissive = ContainerExtractor(
        registry,
        adapter=adapter,
        validation_mode="none",
    )
    payload = {"item": {"kind": "Leaf", "version": "1.0.0"}}
    assert len(list(permissive.extract(payload, container=Envelope))) == 1


def test_public_registry_error_paths(
    model_adapter: types.ModelAdapter,
    versioning_settings: VersioningSettings,
    registry: Registry[types.VersionValue],
) -> None:
    with pytest.raises(CatalogError, match="No versions registered"):
        _ = registry.latest_version
    with pytest.raises(CatalogError, match="No versions registered"):
        registry.earliest("Missing")
    with pytest.raises(CatalogError, match="Unsupported index type"):
        _ = registry[{}]

    def _migrate(data: dict, context: MigrationContext | None = None) -> dict:
        return data

    source = envelope_model(model_adapter, versioning_settings, UserV1)
    target = envelope_model(model_adapter, versioning_settings, UserV2)
    registry.store_model(source)
    registry.store_model(target)
    registry.store_migration(
        edge_from_models(
            model_adapter,
            versioning_settings,
            UserV1,
            UserV2,
            func=_migrate,
        )
    )
    snapshot = registry.snapshot()
    assert snapshot.versions == registry.versions

    with pytest.raises(CatalogError, match="Clear migrations first"):
        registry.clear_models()


def test_backward_compatibility_error_reports_modified_and_required(
    model_adapter: types.ModelAdapter,
    versioning_settings: VersioningSettings,
) -> None:
    error = BackwardCompatibilityError(
        "test",
        (
            envelope_model(model_adapter, versioning_settings, UserV1),
            envelope_model(model_adapter, versioning_settings, UserV2),
        ),
        removed=(),
        modified=("age",),
        required_additions=("status",),
    )
    message = str(error)
    assert "modified=['age']" in message
    assert "required_additions=['status']" in message
