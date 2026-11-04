# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for Registry: model and migration registration.

Most behaviors are exercised for both the semver (pydantic) and chrono/JSON
(``JsonSchemaModelAdapter`` + ``pendulum.Date``) strategies.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import pendulum
import pytest
import semver
from pydantic import BaseModel

from pyverge import types
from pyverge.cli.export import ManifestDiff
from pyverge.cli.jgf import JgfExporter, JgfImporter, JgfNode
from pyverge.core import (
    MaxDepthExceededError,
    PayloadValidationError,
)
from pyverge.core.engine import Engine
from pyverge.core.graph import GraphBuilder
from pyverge.core.registry import DEFAULT_HEALTH_LINTERS, Registry
from pyverge.core.registry.errors import (
    CatalogError,
    HealthValidationError,
    MigrationConflictError,
    MigrationNotFoundError,
    ModelConflictError,
    ModelNotFoundError,
)
from pyverge.core.versioning import (
    EdgeKey,
    FieldDescriptor,
    NodeId,
    NodeRef,
    TypeRef,
    VersionKey,
    VersionNode,
    default_content_hasher,
)
from pyverge.core.versioning.errors import BackwardCompatibilityError
from pyverge.migrations.spec import MigrationSpec
from pyverge.runtime import MigrationHook
from pyverge.runtime.context import MigrationContext
from pyverge.runtime.extractors import (
    ContainerExtractor,
    PayloadWalker,
    SchemaFieldsExtractor,
)
from pyverge.schemas import JsonSchemaModelAdapter, ModelCodec, PydanticModelAdapter
from pyverge.schemas.types import (
    ModelHandle,
)
from pyverge.settings import VersioningSettings
from tests.examples.json import (
    ADDRESS_V1_0_0,
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
    UserV1,
    UserV2,
    UserV3,
    UserV200Beta1,
    migrate_v1_to_v2,
)
from tests.examples.pydantic.semver_nested import (
    AddressV1,
    PersonV1,
)
from tests.utils import edge_from_models, envelope_model, meta_versionable


class TestModel:
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
        assert registry.latest(version.kind).descriptor == version.descriptor

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
        model_adapter: types.ModelAdapter,
        registry: Registry[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        with pytest.raises(ModelNotFoundError):
            registry.get_model_by_ref(model_adapter.ref(model))

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
            str(v.version) for v in sorted([*registry.kind_versions("User"), *keys])
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
        model_adapter: types.ModelAdapter,
        registry: Registry[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        """A copied registry keeps class-based lookups."""
        clone = registry.copy()
        ref = model_adapter.ref(model)
        assert clone.get_model_by_ref(ref).descriptor.ref == ref


class TestMigration:
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

        engine.store_migration(
            (versions[1], versions[0]),
            lambda d, _: d,
            backward_compatible=True,
        )

        breaking = [
            issue
            for issue in engine.registry.health_issues
            if issue.code == "migration.structural_breaking"
        ]
        assert breaking
        assert all(issue.severity == "warning" for issue in breaking)


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
        assert registry.get_migration(key) == edge

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


def _missing_references(
    registry: Registry[types.VersionValue],
    node: types.Comparable,
) -> frozenset[NodeId]:
    return frozenset(
        issue.details["reference"]
        for issue in registry.health(node)
        if issue.code.startswith("reference.missing.")
    )


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
            NodeId("test", "Address", semver.Version(1, 0, 0)),
            NodeId("test", "Address", semver.Version(2, 0, 0)),
            NodeId("test", "Address", semver.Version(3, 0, 0)),
        }
    )

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
        assert {reference.kind for reference in node.references} == {"Address"}
        assert len(node.references) == 3  # noqa: PLR2004

    # -- missing_references: the convenience the consumer actually wants -----

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
        assert _missing_references(registry, node) == self.ADDRESS_VERSIONS

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
        one_child: ModelHandle,
    ) -> None:
        """Registering one ``Address`` version leaves the other two missing."""
        node = envelope_model(model_adapter, versioning_settings, model)
        registry.store(model_adapter.versionable(one_child))
        assert _missing_references(registry, cast(types.Comparable, node)) == frozenset(
            {
                NodeId("test", "Address", semver.Version(2, 0, 0)),
                NodeId("test", "Address", semver.Version(3, 0, 0)),
            }
        )

    def test_health_reports_local_reference_issues(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
    ) -> None:
        node = envelope_model(model_adapter, versioning_settings, PersonV1)
        registry.store(node)

        issues = registry.health(node)

        assert {issue.code for issue in issues} == {"reference.missing.local"}
        assert all(issue.is_node for issue in issues)
        assert all(not issue.is_edge for issue in issues)
        assert _missing_references(registry, node) == self.ADDRESS_VERSIONS

    def test_health_raises_at_error_fail_level(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
    ) -> None:
        node = envelope_model(model_adapter, versioning_settings, PersonV1)
        registry.store(node)

        assert registry.health(node)

        with pytest.raises(HealthValidationError) as raised:
            registry.health(node, fail_level="error")

        assert raised.value.issues
        assert all(issue.severity == "error" for issue in raised.value.issues)

    def test_health_whole_registry_applies_fail_level(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
    ) -> None:
        node = envelope_model(model_adapter, versioning_settings, PersonV1)
        registry.store(node)

        with pytest.raises(HealthValidationError):
            registry.health(fail_level="error")

    def test_health_reports_namespaced_reference_issues(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
    ) -> None:
        registry = Registry[semver.Version](
            namespace="orders",
            hasher=default_content_hasher(),
            linters=DEFAULT_HEALTH_LINTERS,
        )
        node = envelope_model(
            model_adapter,
            versioning_settings,
            PersonV1,
        )
        registry.store(node)

        issues = registry.health(node)

        assert {issue.code for issue in issues} == {"reference.missing.namespaced"}

    def test_health_reports_missing_edge_endpoints(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
    ) -> None:
        source = envelope_model(model_adapter, versioning_settings, UserV1)
        target = envelope_model(model_adapter, versioning_settings, UserV2)
        edge = EdgeKey.from_pair(source, target)
        registry.store_migration(edge)

        issues = registry.health(edge)

        assert {issue.code for issue in issues} == {"edge.endpoint.missing"}
        assert all(issue.is_edge for issue in issues)
        assert all(not issue.is_node for issue in issues)

        registry.store(source)
        registry.store(target)
        assert registry.health(edge) == ()

    def test_health_indexes_track_referrers_and_namespaces(
        self,
        model_adapter: types.ModelAdapter,
        versioning_settings: VersioningSettings,
        registry: Registry[types.VersionValue],
    ) -> None:
        node = envelope_model(model_adapter, versioning_settings, PersonV1)
        registry.store(node)

        for reference in node.references:
            assert node in registry.references_to[reference]

        issues = registry.health(node)
        assert issues
        assert node in registry.issues_by_entity
        assert node in registry.issues_by_namespace[node.namespace]

        child = model_adapter.versionable(AddressV1)
        registry.store(child)
        assert node in registry.references_to[child]
        registry.remove_model(child)
        assert node in registry.references_to[child]
        assert any(
            issue.details["reference"] == child for issue in registry.health(node)
        )


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
        again = registry.reconcile(
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
            registry.reconcile(incoming)

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
        model_adapter: types.ModelAdapter,
        registry: Registry[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        ref = model_adapter.ref(model)
        assert registry.get_model_by_ref(ref).descriptor.ref == ref
        registry.remove_model_by_ref(ref)
        with pytest.raises(ModelNotFoundError):
            registry.get_model_by_ref(ref)


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

    first = registry.store_migration(edge)
    second = registry.store_migration(edge)
    assert first == edge
    assert second == first


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

    assert set(document["graph"]["nodes"]) == {str(node) for node in registry.versions}
    assert len(document["graph"]["edges"]) == sum(
        len(registry.migrations(kind)) for kind in registry.kinds
    )
    assert exporter.export_digest(registry) == exporter.export_digest(registry)
    assert not ManifestDiff.compare(document, document).changed

    nodes_by_id = {
        str(model_adapter.versionable(model)): model_adapter.versionable(model)
        for model in models
    }

    class _Resolver:
        def resolve(self, node: JgfNode) -> types.VersionNode:
            return nodes_by_id[node.id]

    imported = Registry(
        namespace=registry.namespace,
        hasher=default_content_hasher(),
        linters=DEFAULT_HEALTH_LINTERS,
    )
    node_document = {"graph": dict(document["graph"])}
    node_document["graph"].pop("edges")
    imported_graph = JgfImporter(_Resolver()).import_graph(
        node_document,
        models=imported,
    )

    assert {node.id for node in imported_graph.nodes} == set(nodes_by_id)
    assert {str(node) for node in imported.versions} == set(nodes_by_id)


def test_jgf_imports_key_only_edge(model_adapter, registry) -> None:
    source = model_adapter.versionable(UserV1)
    target = model_adapter.versionable(UserV2)
    registry.store(source)
    registry.store(target)
    document = JgfExporter(default_content_hasher()).export_graph(registry).to_dict()
    document["graph"]["edges"] = [
        {
            "id": f"{source}->{target}",
            "source": str(source),
            "target": str(target),
            "directed": True,
            "metadata": {},
        }
    ]
    nodes_by_id = {str(source): source, str(target): target}

    class _NodeResolver:
        def resolve(self, node: JgfNode) -> VersionNode:
            return nodes_by_id[node.id]

    class _EdgeResolver:
        def resolve(self, edge) -> EdgeKey:
            return EdgeKey.from_pair(nodes_by_id[edge.source], nodes_by_id[edge.target])

    imported = Registry(
        namespace=registry.namespace,
        hasher=default_content_hasher(),
        linters=DEFAULT_HEALTH_LINTERS,
    )
    JgfImporter(_NodeResolver()).import_graph(
        document,
        models=imported,
        migrations=imported,
        edge_resolver=_EdgeResolver(),
    )
    edge_key = EdgeKey.from_pair(source, target)

    assert imported.has_edge(edge_key)
    assert not imported.has_migration(edge_key)


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
def test_catalog_lock_returns_frozen_view(
    model_adapter: types.ModelAdapter,
    registry: Registry[types.VersionValue],
    models: list[ModelHandle],
) -> None:
    snapshot = GraphBuilder().build(registry)

    exporter = JgfExporter(default_content_hasher())
    assert (
        exporter.export_graph(snapshot).to_dict()
        == exporter.export_graph(registry).to_dict()
    )
    registry.reconcile(model_adapter.versionable(models[0]))
    assert not hasattr(snapshot, "store")


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
def test_digest_index_tracks_registration(
    model_adapter: types.ModelAdapter,
    versioning_settings: VersioningSettings,
    models: list[ModelHandle],
) -> None:
    catalog = Registry(
        namespace=getattr(model_adapter, "model_codec").namespace,
        hasher=default_content_hasher(),
        index_digests=True,
        linters=DEFAULT_HEALTH_LINTERS,
    )
    nodes = [model_adapter.versionable(model) for model in models]
    for node in nodes:
        catalog.store(node)

    edge = edge_from_models(
        model_adapter,
        versioning_settings,
        models[0],
        models[1],
        func=_noop_migration,
    )
    catalog.store_migration(edge)

    key = EdgeKey.from_version_edge(edge)
    assert catalog.find_edge_by_digest(edge.digest(default_content_hasher())) == key

    catalog.remove_migration(key)
    assert catalog.find_edge_by_digest(edge.digest(default_content_hasher())) is None


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
    Registry[semver.Version],
    PydanticModelAdapter,
    PayloadWalker[semver.Version],
]:
    adapter = PydanticModelAdapter(
        codec=ModelCodec(
            namespace="test", version_property="version", kind_property="kind"
        )
    )
    registry = Registry[semver.Version](
        namespace="test",
        hasher=default_content_hasher(),
        linters=DEFAULT_HEALTH_LINTERS,
    )
    registry.store(adapter.versionable(Leaf))
    return registry, adapter, PayloadWalker(registry, adapter=adapter)


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
    entries = list(extractor.extract(envelope.model_dump(), source_model=Envelope))
    assert len(entries) == 1
    list_envelope = ListEnvelope(items=[{"kind": "Leaf", "version": "1.0.0"}])
    entries = list(
        extractor.extract(list_envelope.model_dump(), source_model=ListEnvelope)
    )
    assert len(entries) == 1


def test_guided_depth_and_validation_errors() -> None:
    _, _, extractor = _extractor()
    envelope = Envelope(item={"kind": "Leaf", "version": "1.0.0"})
    with pytest.raises(MaxDepthExceededError):
        list(
            extractor.extract(envelope.model_dump(), source_model=Envelope, max_depth=0)
        )
    with pytest.raises(PayloadValidationError, match="source model validation"):
        list(extractor.extract({"item": "bad"}, source_model=Envelope))
    with pytest.raises(PayloadValidationError, match="not a recognized"):
        list(extractor.extract({}, source_model=dict))


def test_specialized_extractor_modes() -> None:
    registry, adapter, _ = _extractor()
    schema = SchemaFieldsExtractor(registry, adapter=adapter)
    assert list(schema.extract({})) == []

    container = ContainerExtractor(registry, adapter=adapter)
    with pytest.raises(PayloadValidationError, match="source model validation"):
        list(container.extract({"item": "bad"}, source_model=Envelope))

    permissive = ContainerExtractor(
        registry,
        adapter=adapter,
        validation_mode="none",
    )
    payload = {"item": {"kind": "Leaf", "version": "1.0.0"}}
    assert len(list(permissive.extract(payload, source_model=Envelope))) == 1


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
    registry.store(source)
    registry.store(target)
    registry.store_migration(
        edge_from_models(
            model_adapter,
            versioning_settings,
            UserV1,
            UserV2,
            func=_migrate,
        )
    )
    snapshot = GraphBuilder().build(registry)
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


def test_key_only_entry_hydrates_to_full_node(
    model_adapter: types.ModelAdapter,
    versioning_settings: VersioningSettings,
    registry: Registry[types.VersionValue],
) -> None:
    node = envelope_model(model_adapter, versioning_settings, UserV1)
    key = VersionKey(
        namespace=node.namespace,
        kind=node.kind,
        version=node.version,
        ref=NodeRef(),
    )

    assert registry.store(key) == key
    assert registry.has_entry(key)
    assert registry.find_model(key) is None
    assert registry.versions == []

    hydrated = registry.hydrate(node)

    assert hydrated == node
    assert registry.get_model(key) == node
    assert registry.versions == [node]
    assert len(registry.entries) == 1


def test_reconcile_does_not_hydrate_key_only_entry(
    model_adapter: types.ModelAdapter,
    versioning_settings: VersioningSettings,
    registry: Registry[types.VersionValue],
) -> None:
    node = envelope_model(model_adapter, versioning_settings, UserV1)
    key = VersionKey(
        namespace=node.namespace,
        kind=node.kind,
        version=node.version,
        ref=NodeRef(),
    )
    registry.store(key)

    with pytest.raises(CatalogError, match="hydrate"):
        registry.reconcile(node)

    assert registry.find_model(key) is None
    assert registry.get_entry(key) == key


def test_registry_requires_non_empty_namespace() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        Registry[semver.Version](
            namespace="",
            hasher=default_content_hasher(),
            linters=DEFAULT_HEALTH_LINTERS,
        )


def test_registry_accepts_foreign_namespace_entry(
    model_adapter: types.ModelAdapter,
    versioning_settings: VersioningSettings,
) -> None:
    registry = Registry[semver.Version](
        namespace="orders",
        hasher=default_content_hasher(),
        linters=DEFAULT_HEALTH_LINTERS,
    )
    foreign = envelope_model(
        model_adapter,
        versioning_settings,
        UserV1,
    ).with_namespace("billing")

    stored = registry.store(foreign)

    assert stored.namespace == "billing"
    assert registry.has_entry(foreign)
    assert registry.reconcile(foreign) is foreign


def test_jgf_export_prefixes_namespace() -> None:
    registry = Registry[semver.Version](
        namespace="orders",
        hasher=default_content_hasher(),
        linters=DEFAULT_HEALTH_LINTERS,
    )
    adapter = PydanticModelAdapter(
        codec=ModelCodec(
            namespace="orders", version_property="version", kind_property="kind"
        )
    )
    registry.store(adapter.versionable(UserV1))

    document = JgfExporter(default_content_hasher()).export_graph(registry).to_dict()
    assert set(document["graph"]["nodes"]) == {"orders:User@1.0.0"}


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [semver.Version, "test", [UserV1, UserV2], []],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_parallel_migrations_with_discriminators(registry) -> None:
    source, target = registry.kind_versions("User")

    canary = registry.store_migration(
        MigrationSpec(
            (source, target),
            migrate_v1_to_v2,
            discriminator="canary",
        )
    )
    stable = registry.store_migration(
        MigrationSpec(
            (source, target),
            migrate_v1_to_v2,
            discriminator="stable",
        )
    )

    assert canary.discriminator == "canary"
    assert stable.discriminator == "stable"
    assert len(registry.edges("User")) == 2  # noqa: PLR2004
    assert (
        registry.get_migration_by_edge(
            EdgeKey.from_pair(source, target, discriminator="canary")
        )
        is canary
    )
    assert (
        registry.get_migration_by_edge(
            EdgeKey.from_pair(source, target, discriminator="stable")
        )
        is stable
    )
    assert not registry.has_edge(EdgeKey.from_pair(source, target))
    assert EdgeKey.from_pair(source, target, discriminator="canary") in registry


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [semver.Version, "test", [UserV1, UserV2], []],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_parallel_migration_discriminators_keep_own_content(registry) -> None:
    source, target = registry.kind_versions("User")
    registry.store_migration(
        MigrationSpec(
            (source, target),
            migrate_v1_to_v2,
            discriminator="canary",
        )
    )

    with pytest.raises(MigrationConflictError):
        registry.store_migration(
            MigrationSpec(
                (source, target),
                lambda data, _: data,
                discriminator="canary",
            )
        )
