from __future__ import annotations

from collections.abc import Callable
from itertools import pairwise
from typing import Any
from unittest.mock import MagicMock

import pendulum
import pytest
import semver
from pydantic import BaseModel

from pyverge.core import (
    DiscoverySettings,
    MigrationAlreadyRegisteredError,
    MigrationHook,
    MigrationNotFoundError,
    MigrationSettings,
    ModelAlreadyRegisteredError,
    ModelNotFoundError,
    RegistryError,
    SentinelEdge,
    SentinelNode,
    VersioningSettings,
    VersionNode,
    types,
)
from pyverge.migration import (
    CompoundKeyWalker,
    Engine,
    EntryMigration,
    GraphBuilder,
    JsonPatchMigration,
    PydanticModelAdapter,
    Registry,
    SequentialExecutor,
    fixed_target_resolver,
    latest_target_resolver,
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
)
from tests.examples.pydantic.semver_nested import AddressV1
from tests.utils import edge_from_models, envelope_model, make_engine, meta_versionable

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
            [
                Registry[semver.Version, BaseModel](),
                SentinelNode("User", semver.Version(9, 9, 9)),
            ],
            [
                Registry[pendulum.Date, BaseModel](),
                SentinelNode("User", pendulum.Date(2099, 1, 1)),
            ],
        ],
    )
    def test_get_missing_model_raises(
        self,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        key: SentinelNode,
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

        found = eng.find_model(version)
        assert found.model is model

    def test_find_model_miss_raises(
        self,
        migration_settings: MigrationSettings,
    ) -> None:
        eng = make_engine(Registry[semver.Version, BaseModel](), migration_settings)
        with pytest.raises(ModelNotFoundError):
            eng.find_model(SentinelNode("User", semver.Version(9, 9, 9)))

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

    def test_remove_missing_model_raises(
        self, migration_settings: MigrationSettings
    ) -> None:
        eng = make_engine(Registry[semver.Version, BaseModel](), migration_settings)
        with pytest.raises(RegistryError):
            eng.remove_model(SentinelNode("User", semver.Version(9, 9, 9)))

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
        edge = SentinelEdge.from_pair(versions[0], versions[1])
        assert eng.get_migration(edge).func is _migrate

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
        "registry, meta_versions, real_model, expected_version, func_factory",
        [
            [
                Registry[semver.Version, BaseModel](),
                ["0.1.0", "0.2.0"],
                UserV1,
                "1.0.0",
                lambda from_v, to_v: lambda d, to=to_v: {**d, "version": to},
            ],
            [
                Registry[pendulum.Date, BaseModel](),
                ["2024-01-01", "2024-02-01"],
                UserV20250310,
                "2025-03-10",
                lambda from_v, to_v: lambda d, to=to_v: {**d, "version": to},
            ],
            [
                Registry[semver.Version, BaseModel](),
                ["0.1.0", "0.2.0"],
                UserV1,
                "1.0.0",
                lambda from_v, to_v: JsonPatchMigration(
                    {
                        "from": from_v,
                        "to": to_v,
                        "ops": [
                            {
                                "op": "replace",
                                "path": "/version",
                                "value": to_v,
                            }
                        ],
                    }
                ).patch,
            ],
        ],
        ids=["semver-callable", "date-callable", "semver-jsonpatch"],
    )
    def test_meta_chain_forward_migrates_to_latest(
        self,
        model_adapter: PydanticModelAdapter,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        meta_versions: list[str],
        real_model: type[types.VModel],
        expected_version: str,
        func_factory: Callable,
    ) -> None:
        """A meta chain hooks stored (kind, version) pairs and converges forward.

        The migration func is built either as a Python callable or as a
        declarative :class:`JsonPatchMigration` spec.
        """
        eng = make_engine(registry, migration_settings)
        metas = [meta_versionable(model_adapter, "User", v) for v in meta_versions]
        real = eng.adapter.versionable(real_model)
        for v in metas:
            eng.store_model(v)
        eng.store_model(real)
        for src, dst in zip(metas, [*metas[1:], real]):
            func = func_factory(str(src.version[1]), str(dst.version[1]))
            eng.store_migration((src, dst), func)

        result = eng.migrate(
            {
                "kind": "User",
                "version": meta_versions[0],
                "name": "Alice",
                "email": "a@b.c",
                "role": "user",
            },
            target=latest_target_resolver(registry),
        )
        assert result["version"] == expected_version

    @pytest.mark.parametrize(
        "registry, meta_versions, real_model",
        [
            [Registry[semver.Version, BaseModel](), ["0.1.0", "0.2.0"], UserV1],
            [
                Registry[pendulum.Date, BaseModel](),
                ["2024-01-01", "2024-02-01"],
                UserV20250310,
            ],
        ],
    )
    def test_meta_chain_backward_via_swapped_spec(
        self,
        model_adapter: PydanticModelAdapter,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        meta_versions: list[str],
        real_model: type[types.VModel],
    ) -> None:
        """Backward migration across a meta chain uses swapped-spec reverse edges."""
        eng = make_engine(registry, migration_settings)
        metas = [meta_versionable(model_adapter, "User", v) for v in meta_versions]
        real = eng.adapter.versionable(real_model)
        for v in metas:
            eng.store_model(v)
        eng.store_model(real)
        for src, dst in zip(metas, [*metas[1:], real]):
            eng.store_migration(
                (src, dst), lambda d: {**d, "version": str(dst.version[1])}
            )
        for src, dst in zip([*metas[1:], real], metas):
            eng.store_migration(
                (src, dst), lambda d: {**d, "version": str(dst.version[1])}
            )

        result = eng.migrate(
            {
                "kind": "User",
                "version": str(real.version[1]),
                "name": "Alice",
                "email": "a@b.c",
                "role": "user",
            },
            target=fixed_target_resolver(registry, metas[0]),
            direction="backward",
        )
        assert result["version"] == meta_versions[0]

    @pytest.mark.parametrize(
        "registry, meta_versions, real_model",
        [
            [Registry[semver.Version, BaseModel](), ["0.1.0", "0.2.0"], UserV1],
        ],
    )
    def test_meta_chain_backward_missing_reverse_edge_raises(
        self,
        model_adapter: PydanticModelAdapter,
        migration_settings: MigrationSettings,
        registry: Registry[types.VersionValue, BaseModel],
        meta_versions: list[str],
        real_model: type[types.VModel],
    ) -> None:
        """Backward migration raises when a reverse edge is missing."""
        eng = make_engine(registry, migration_settings)
        metas = [meta_versionable(model_adapter, "User", v) for v in meta_versions]
        real = eng.adapter.versionable(real_model)
        for v in metas:
            eng.store_model(v)
        eng.store_model(real)
        for src, dst in zip(metas, [*metas[1:], real]):
            eng.store_migration(
                (src, dst), lambda d: {**d, "version": str(dst.version[1])}
            )

        with pytest.raises(MigrationNotFoundError):
            eng.migrate(
                {
                    "kind": "User",
                    "version": str(real.version[1]),
                    "name": "Alice",
                    "email": "a@b.c",
                    "role": "user",
                },
                target=fixed_target_resolver(registry, metas[0]),
                direction="backward",
            )

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
            eng.get_migration(SentinelEdge.from_pair(versions[0], versions[1]))

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

        for pair in pairwise(versions):
            eng.store_migration(pair, lambda d: d, backward_compatible=True)

        eng.remove_migration(SentinelEdge.from_pair(versions[0], versions[1]))

    @pytest.mark.parametrize(
        "registry, models",
        [
            [
                Registry[semver.Version, BaseModel](),
                [UserV011Dev7, UserV1, UserV2, UserV3],
            ],
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

        for pair in pairwise(versions):
            eng.store_migration(pair, lambda d: d)

        with pytest.raises(RegistryError, match="critical"):
            eng.remove_migration(SentinelEdge.from_pair(versions[1], versions[2]))

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

        edge = SentinelEdge.from_pair(versions[0], versions[1])
        eng.remove_migration(edge, force=True)
        with pytest.raises(MigrationNotFoundError):
            eng.get_migration(edge)

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
            eng.remove_migration(SentinelEdge.from_pair(versions[0], versions[1]))

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
        eng.add_hook(SentinelEdge.from_pair(versions[0], versions[1]), hook)
        assert registry.has_hooks(registry.get_migration_by_edge(key))

        eng.remove_hook(SentinelEdge.from_pair(versions[0], versions[1]), hook)
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

        eng.add_hook(SentinelEdge.from_pair(versions[0], versions[1]), MigrationHook())
        eng.clear_hooks()
        assert not registry._hooks


class TestReflection:
    """Engine reconstructs missing models implicitly on migration registration."""

    def test_reconstructs_missing_model_on_store_migration(
        self,
        model_adapter: PydanticModelAdapter,
        migration_settings: MigrationSettings,
    ) -> None:
        settings = migration_settings.model_copy(
            update={"on_missing_model": "reconstruct"}
        )
        registry = Registry[semver.Version, BaseModel]()
        eng = make_engine(registry, settings, adapter=model_adapter)
        real = eng.adapter.versionable(UserV2)
        eng.store_model(real)
        meta = meta_versionable(model_adapter, "User", "1.0.0")

        eng.store_migration(
            (meta, real),
            JsonPatchMigration(
                {
                    "from": "1.0.0",
                    "to": "2.0.0",
                    "ops": [{"op": "add", "path": "/age", "value": None}],
                }
            ).patch,
        )

        reconstructed = eng.get_model(SentinelNode("User", semver.Version(1, 0, 0)))
        assert reconstructed.model is not None
        fields = reconstructed.model.model_fields
        assert "name" in fields
        assert "age" not in fields
        assert fields["version"].default == "1.0.0"

    def test_reconstructs_with_callable_migration(
        self,
        model_adapter: PydanticModelAdapter,
        migration_settings: MigrationSettings,
    ) -> None:
        settings = migration_settings.model_copy(
            update={"on_missing_model": "reconstruct"}
        )
        registry = Registry[semver.Version, BaseModel]()
        eng = make_engine(registry, settings, adapter=model_adapter)
        real = eng.adapter.versionable(UserV2)
        eng.store_model(real)
        meta = meta_versionable(model_adapter, "User", "1.0.0")

        def add_age(data: dict) -> dict:
            return {**data, "age": None}

        eng.store_migration((meta, real), add_age)

        reconstructed = eng.get_model(SentinelNode("User", semver.Version(1, 0, 0)))
        assert reconstructed.model is not None
        assert "age" not in reconstructed.model.model_fields

    def test_skips_reconstruction_when_disabled(
        self,
        model_adapter: PydanticModelAdapter,
        migration_settings: MigrationSettings,
    ) -> None:
        settings = migration_settings.model_copy(update={"on_missing_model": "skip"})
        registry = Registry[semver.Version, BaseModel]()
        eng = make_engine(registry, settings, adapter=model_adapter)
        real = eng.adapter.versionable(UserV2)
        eng.store_model(real)
        meta = meta_versionable(model_adapter, "User", "1.0.0")
        eng.store_model(meta)

        eng.store_migration((meta, real), lambda d: {**d, "age": None})

        stored = eng.get_model(SentinelNode("User", semver.Version(1, 0, 0)))
        assert stored.model is None


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

        assert (versions[0], versions[1]) in eng
        assert (versions[1], versions[0]) not in eng

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
        assert eng[(versions[0], versions[1])].func is _migrate

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
        assert [e.func for e in path] == [_migrate_12, _migrate_23]


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
