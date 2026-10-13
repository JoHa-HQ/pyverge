from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from itertools import pairwise
from typing import Any
from unittest.mock import MagicMock

import pendulum
import pytest
import semver

from pyverge import types
from pyverge.core import (
    MigrationAlreadyRegisteredError,
    MigrationHook,
    MigrationNotFoundError,
    MigrationSettings,
    MissingReferenceError,
    ModelConflictError,
    ModelNotFoundError,
    RegistryError,
    SentinelEdge,
    VersionNode,
)
from pyverge.migration import (
    Engine,
    JsonPatchMigration,
    JsonSchemaModelAdapter,
    MigrationEntry,
    PydanticModelAdapter,
    earliest_target_resolver,
    fixed_target_resolver,
    latest_target_resolver,
)
from pyverge.providers.types import (
    ModelHandle,
)
from tests.examples.json import (
    ADDRESS_V1_0_0,
    ADDRESS_V2_0_0,
    ADDRESS_V3_0_0,
    PERSON_V1_0_0,
    USER_V0_1_1_DEV_7,
    USER_V1_0_0,
    USER_V1_2_3,
)
from tests.examples.pydantic.chrono import (
    UserV20250310,
    UserV20251231,
    UserV20260228,
)
from tests.examples.pydantic.chrono_nested import AddressV20240101
from tests.examples.pydantic.semver import (
    UserV011Dev7,
    UserV1,
    UserV2,
    UserV3,
)
from tests.examples.pydantic.semver_nested import (
    AddressV1,
    AddressV2,
    AddressV3,
    PersonV1,
)
from tests.utils import envelope_model, meta_versionable


class TestModelManagement:
    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            [PydanticModelAdapter, [semver.Version, "test", [UserV1], []], [UserV1]],
            [
                PydanticModelAdapter,
                [pendulum.Date, "test", [UserV20250310], []],
                [UserV20250310],
            ],
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_get_model_by_versionable(
        self,
        subtests: pytest.Subtests,
        migration_settings: MigrationSettings,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        for model in models:
            with subtests.test(f"model={model.__name__}"):
                version = envelope_model(engine.adapter, migration_settings, model)
                assert engine.get_model(version).model is model

    @pytest.mark.parametrize(
        "model_adapter, registry, operation, expected",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [], []],
                lambda engine: engine.get_model(
                    VersionNode(
                        _model=None, _value=semver.Version(9, 9, 9), _kind="User"
                    )
                ),
                ModelNotFoundError,
                id="get_missing_pydantic_semver",
            ),
            pytest.param(
                PydanticModelAdapter,
                [pendulum.Date, "test", [], []],
                lambda engine: engine.get_model(
                    VersionNode(
                        _model=None, _value=pendulum.Date(2099, 1, 1), _kind="User"
                    )
                ),
                ModelNotFoundError,
                id="get_missing_pydantic_pendulum",
            ),
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1], []],
                lambda engine: engine.reconcile_model(
                    replace(
                        envelope_model(engine.adapter, engine.settings, UserV1),
                        fields=frozenset({"conflict"}),
                    )
                ),
                ModelConflictError,
                id="store_conflict_pydantic_semver",
            ),
            pytest.param(
                PydanticModelAdapter,
                [pendulum.Date, "test", [UserV20250310], []],
                lambda engine: engine.reconcile_model(
                    replace(
                        envelope_model(engine.adapter, engine.settings, UserV20250310),
                        fields=frozenset({"conflict"}),
                    )
                ),
                ModelConflictError,
                id="store_conflict_pydantic_pendulum",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "test", [USER_V0_1_1_DEV_7], []],
                lambda engine: engine.reconcile_model(
                    replace(
                        envelope_model(
                            engine.adapter, engine.settings, USER_V0_1_1_DEV_7
                        ),
                        fields=frozenset({"conflict"}),
                    )
                ),
                ModelConflictError,
                id="store_conflict_json_semver",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_get_and_store_raises(
        self,
        engine: Engine[types.VersionValue],
        operation: Callable[[Engine[types.VersionValue]], Any],
        expected: type[Exception],
    ) -> None:
        with pytest.raises(expected):
            operation(engine)

    @pytest.mark.parametrize(
        "model_adapter, registry, model",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1], []],
                UserV1,
                id="pydantic_semver",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "test", [USER_V1_0_0], []],
                USER_V1_0_0,
                id="json_semver",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_conflict_reports_structured_surface(
        self,
        model_adapter: types.ModelAdapter,
        migration_settings: MigrationSettings,
        engine: Engine[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        """A conflict exposes the diff and a resolution hint."""
        registered = envelope_model(model_adapter, migration_settings, model)
        incoming = replace(registered, fields=registered.fields | {"extra_field"})
        with pytest.raises(ModelConflictError) as raised:
            engine.reconcile_model(incoming)
        error = raised.value
        assert error.extra == {"extra_field"}
        assert error.missing == frozenset()
        assert error.registered == registered.fields
        assert "Resolve by aligning" in str(error)

    @pytest.mark.parametrize(
        "model_adapter, registry, model",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1], []],
                UserV1,
                id="pydantic_semver",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "test", [USER_V1_0_0], []],
                USER_V1_0_0,
                id="json_semver",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_store_identical_duplicate_is_noop(
        self,
        model_adapter: types.ModelAdapter,
        migration_settings: MigrationSettings,
        engine: Engine[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        """The engine reconciles: an identical re-registration is a no-op."""
        again = engine.reconcile_model(
            envelope_model(model_adapter, migration_settings, model)
        )
        assert engine.get_model(again) is again

    @pytest.mark.parametrize(
        "model_adapter, registry, children",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "nested_test", [PersonV1], []],
                (AddressV1,),
                id="pydantic_partial",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "nested_test", [PERSON_V1_0_0], []],
                (ADDRESS_V1_0_0,),
                id="json_partial",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_validate_reports_missing_references(
        self,
        model_adapter: types.ModelAdapter,
        engine: Engine[types.VersionValue],
        children: tuple,
    ) -> None:
        """One child registered, the rest absent: validate names the gaps."""
        for child in children:
            engine.store_model(model_adapter.versionable(child))
        with pytest.raises(MissingReferenceError) as raised:
            engine.validate()
        assert raised.value.absent
        assert all(kind == "Address" for kind, _ in raised.value.absent)

    @pytest.mark.parametrize(
        "model_adapter, registry, children",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "nested_test", [PersonV1], []],
                (AddressV1, AddressV2, AddressV3),
                id="pydantic",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "nested_test", [PERSON_V1_0_0], []],
                (ADDRESS_V1_0_0, ADDRESS_V2_0_0, ADDRESS_V3_0_0),
                id="json",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_validate_passes_when_references_registered(
        self,
        model_adapter: types.ModelAdapter,
        engine: Engine[types.VersionValue],
        children: tuple,
    ) -> None:
        """A complete graph validates cleanly."""
        for child in children:
            engine.store_model(model_adapter.versionable(child))
        engine.validate()

    @pytest.mark.parametrize(
        "model_adapter, registry, model, expected_error",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [UserV3, UserV1, UserV2], []],
                UserV3,
                None,
                id="latest_pydantic_semver",
            ),
            pytest.param(
                PydanticModelAdapter,
                [
                    pendulum.Date,
                    "test",
                    [UserV20251231, UserV20260228, UserV20250310],
                    [],
                ],
                UserV20260228,
                None,
                id="latest_pydantic_pendulum",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    semver.Version,
                    "test",
                    [USER_V1_2_3, USER_V0_1_1_DEV_7, USER_V1_0_0],
                    [],
                ],
                USER_V1_2_3,
                None,
                id="latest_json_semver",
            ),
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [], []],
                UserV1,
                RegistryError,
                id="unknown_kind_pydantic_semver",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [pendulum.Date, "test", [], []],
                USER_V0_1_1_DEV_7,
                RegistryError,
                id="unknown_kind_json_pendulum",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_model_latest(
        self,
        engine: Engine[types.VersionValue],
        model: ModelHandle,
        expected_error: type[Exception] | None,
    ) -> None:
        version = envelope_model(engine.adapter, engine.settings, model)
        if expected_error is None:
            assert engine.get_latest_model(version.kind).model is version.model
            return
        with pytest.raises(expected_error):
            engine.get_latest_model(version.kind)

    @pytest.mark.parametrize(
        "model_adapter, registry, model",
        [
            [PydanticModelAdapter, [semver.Version, "test", [UserV1], []], UserV1],
            [
                JsonSchemaModelAdapter,
                [pendulum.Date, "test", [USER_V0_1_1_DEV_7], []],
                USER_V0_1_1_DEV_7,
            ],
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_contains_version_tuple(
        self,
        engine: Engine[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        version = envelope_model(engine.adapter, engine.settings, model)
        assert version in engine
        # Typed-only: a raw (kind, version) tuple is manager sugar, not engine.
        assert (version.kind, version.version[1]) not in engine

    @pytest.mark.parametrize(
        "model_adapter, registry, model",
        [
            [PydanticModelAdapter, [semver.Version, "test", [UserV1], []], UserV1],
            [
                JsonSchemaModelAdapter,
                [pendulum.Date, "test", [USER_V0_1_1_DEV_7], []],
                USER_V0_1_1_DEV_7,
            ],
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_remove_model_by_versionable(
        self,
        engine: Engine[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        version = envelope_model(engine.adapter, engine.settings, model)
        engine.remove_model(version)
        assert version not in engine

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            [PydanticModelAdapter, [semver.Version, "test", [], []], UserV1],
            [
                JsonSchemaModelAdapter,
                [pendulum.Date, "test", [], []],
                USER_V0_1_1_DEV_7,
            ],
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_remove_model_referenced_by_migration_raises(
        self,
        engine: Engine[semver.Version],
        models: ModelHandle,
    ) -> None:
        version = envelope_model(engine.adapter, engine.settings, models)
        with pytest.raises(RegistryError):
            engine.remove_model(version)


class TestMigrationManagement:
    """Engine-level CRUD for migration edges.

    Engine policy: key normalization (Versionable | class | tuple
    pairs), same-kind enforcement, and the adjacency rule —
    non-adjacent edges are accepted only when every consecutive
    edge inside the gap is registered and backward-compatible.
    Registry enforces structural invariants; both must propagate.
    """

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            [
                PydanticModelAdapter,
                [semver.Version, "test", [], []],
                [UserV1, UserV2],
            ],
            [
                JsonSchemaModelAdapter,
                [pendulum.Date, "test", [], []],
                [USER_V0_1_1_DEV_7, USER_V1_0_0],
            ],
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_store_and_get_by_versionable_pair(
        self,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [envelope_model(engine.adapter, engine.settings, m) for m in models]
        for v in versions:
            engine.store_model(v)

        def _migrate(data: dict) -> dict:
            return data

        engine.store_migration((versions[0], versions[1]), _migrate)
        edge = SentinelEdge.from_pair(versions[0], versions[1])
        assert engine.get_migration(edge).func is _migrate

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [], []],
                [UserV1, AddressV1],
                id="pydantic_semver_user_v1_address_v1_empty",
            ),
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2], []],
                [UserV1, AddressV1],
                id="pydantic_semver_user_v1_address_v1",
            ),
            pytest.param(
                PydanticModelAdapter,
                [pendulum.Date, "test", [UserV20250310, UserV20251231], []],
                [UserV20250310, AddressV20240101],
                id="pydantic_semver_user_v20250310_address_v20240101",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "test", [USER_V1_0_0, USER_V1_2_3], []],
                [USER_V1_0_0, ADDRESS_V1_0_0],
                id="json_user_v1_address_v1",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_store_across_kinds_raises(
        self,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [
            envelope_model(engine.adapter, engine.settings, model) for model in models
        ]
        with pytest.raises(RegistryError, match="across kinds"):
            engine.store_migration(versions, lambda d: d)  # ty: ignore[invalid-argument-type]

    @pytest.mark.parametrize(
        "model_adapter, registry, meta_models, "
        "expected_version, func_factory, migration_direction",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [UserV011Dev7], []],
                [("User", "0.2.1"), ("User", "1.0.0")],
                "1.0.0",
                lambda from_v, to_v: lambda d, to=to_v: {**d, "version": to},
                "forward",
                id="pydantic_semver_user_v1_meta_010_020_forward",
            ),
            pytest.param(
                PydanticModelAdapter,
                [pendulum.Date, "test", [UserV20250310], []],
                [("User", "2025-03-11"), ("User", "2025-04-01")],
                "2025-04-01",
                lambda from_v, to_v: lambda d, to=to_v: {**d, "version": to},
                "forward",
                id="pydantic_pendulum_user_v20250310_meta_20250311_20250401_forward",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "test", [USER_V1_0_0], []],
                [("User", "1.1.0"), ("User", "2.0.0")],
                "2.0.0",
                lambda from_v, to_v: (
                    JsonPatchMigration(
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
                    ).patch
                ),
                "forward",
                id="pydantic_semver_user_v1_meta_010_020_jsonpatch_forward",
            ),
            pytest.param(
                PydanticModelAdapter,
                [pendulum.Date, "test", [UserV20251231], []],
                [("User", "2025-04-11"), ("User", "2025-03-01")],
                "2025-03-01",
                lambda from_v, to_v: lambda d, to=to_v: {**d, "version": to},
                "backward",
                id="pydantic_pendulum_user_v20250310_meta_20250411_20250301_backward",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_meta_chain_forward_migrates_to_latest(
        self,
        engine: Engine[types.VersionValue],
        meta_models: list[types.ModelVersionKey],
        expected_version: str,
        func_factory: Callable,
        migration_direction: types.MigrationDirectionStrategy,
    ) -> None:
        """A meta chain hooks stored (kind, version) pairs and converges forward.

        The migration func is built either as a Python callable or as a
        declarative :class:`JsonPatchMigration` spec.
        """
        if migration_direction == "forward":
            real = engine.get_latest_model(kind=meta_models[0][0])
            target = latest_target_resolver(engine.registry)
        else:
            real = engine.get_earliest_model(kind=meta_models[0][0])
            target = earliest_target_resolver(engine.registry)
        versionables = [
            engine.store_model(
                engine.adapter.versionable(None, kind=m[0], version=m[1])
            )
            for m in meta_models
        ]
        for src, dst in pairwise([real, *versionables]):
            func = func_factory(str(src), str(dst))
            engine.store_migration((src, dst), func)

        result = engine.migrate(
            {
                "kind": "User",
                "version": str(real.version[1]),
                "name": "Alice",
                "email": "a@b.c",
                "role": "user",
            },
            target=target,
            direction=migration_direction,
        )
        assert result["version"] == expected_version

    @pytest.mark.parametrize(
        "model_adapter, registry, meta_versions, direction",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [UserV011Dev7], []],
                [("User", "0.2.0"), ("User", "0.3.0")],
                "forward",
                id="pydantic_semver_user_v1_meta_010_020_forward",
            ),
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1], []],
                [("User", "0.2.0"), ("User", "0.1.0")],
                "backward",
                id="pydantic_semver_user_v1_meta_020_010_backward",
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.VersionInfo, "test", [USER_V1_0_0], []],
                [("User", "0.2.0"), ("User", "0.1.0")],
                "backward",
                id="json_schema_semver_user_v1_0_0_020_backward",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_meta_chain_missing_edge_raises(
        self,
        engine: Engine[types.VersionValue],
        meta_versions: list[tuple[str, str]],
        direction: types.MigrationDirectionStrategy,
    ) -> None:
        """Backward migration raises when a reverse edge is missing."""
        versionables = [
            engine.store_model(
                engine.adapter.versionable(None, kind=v[0], version=v[1])
            )
            for v in meta_versions
        ]
        if direction == "backward":
            real = engine.get_latest_model(versionables[0].kind)
        else:
            real = engine.get_earliest_model(versionables[0].kind)
        for src, dst in pairwise([real, versionables[0]]):
            engine.store_migration(
                (src, dst), lambda d: {**d, "version": str(dst.version[1])}
            )

        with pytest.raises(MigrationNotFoundError):
            engine.migrate(
                {
                    "kind": "User",
                    "version": str(real.version[1]),
                    "name": "Alice",
                    "email": "a@b.c",
                    "role": "user",
                },
                target=fixed_target_resolver(engine.registry, versionables[1]),
                direction=direction,
            )

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d: d)],
                ],
                [UserV1, UserV2],
                id="pydantic_semver_user_v1_v2",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_store_duplicate_raises(
        self,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [envelope_model(engine.adapter, engine.settings, m) for m in models]
        with pytest.raises(MigrationAlreadyRegisteredError):
            engine.store_migration((versions[0], versions[1]), lambda d: d)

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2], []],
                [UserV1, UserV2],
                id="pydantic_semver_user_v1_v2",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_get_missing_raises(
        self,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [envelope_model(engine.adapter, engine.settings, m) for m in models]
        with pytest.raises(MigrationNotFoundError):
            engine.get_migration(SentinelEdge.from_pair(versions[0], versions[1]))

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2, UserV3], []],
                [UserV1, UserV2, UserV3],
                id="pydantic_semver_user_v1_v2_v3",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_remove_non_critical_ok(
        self,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [envelope_model(engine.adapter, engine.settings, m) for m in models]

        for pair in pairwise(versions):
            engine.store_migration(pair, lambda d: d, backward_compatible=True)

        engine.remove_migration(SentinelEdge.from_pair(versions[0], versions[1]))

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [UserV011Dev7, UserV1, UserV2, UserV3],
                    [
                        ((UserV011Dev7, UserV1), lambda d: d),
                        ((UserV1, UserV2), lambda d: d),
                        ((UserV2, UserV3), lambda d: d),
                    ],
                ],
                [UserV011Dev7, UserV1, UserV2, UserV3],
                id="pydantic_semver_user_v011_v1_v2_v3",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_remove_critical_raises(
        self,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [envelope_model(engine.adapter, engine.settings, m) for m in models]
        with pytest.raises(RegistryError, match="critical"):
            engine.remove_migration(SentinelEdge.from_pair(versions[1], versions[2]))

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [], []],
                [UserV1, UserV2],
                id="pydantic_semver_user_v1_v2",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_remove_critical_with_force(
        self,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [envelope_model(engine.adapter, engine.settings, m) for m in models]
        for v in versions:
            engine.store_model(v)
        engine.store_migration((versions[0], versions[1]), lambda d: d)

        edge = SentinelEdge.from_pair(versions[0], versions[1])
        engine.remove_migration(edge, force=True)
        with pytest.raises(MigrationNotFoundError):
            engine.get_migration(edge)

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [], []],
                [UserV1, UserV2],
                id="pydantic_semver_user_v1_v2",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_remove_missing_raises(
        self,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [envelope_model(engine.adapter, engine.settings, m) for m in models]
        for v in versions:
            engine.store_model(v)

        with pytest.raises(MigrationNotFoundError):
            engine.remove_migration(SentinelEdge.from_pair(versions[0], versions[1]))

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [], []],
                [UserV1, UserV2, UserV3],
                id="pydantic_semver_user_v1_v2_v3",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_remove_range_critical_raises(
        self,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [envelope_model(engine.adapter, engine.settings, m) for m in models]
        for v in versions:
            engine.store_model(v)
        engine.store_migration((versions[0], versions[1]), lambda d: d)
        engine.store_migration((versions[1], versions[2]), lambda d: d)

        with pytest.raises(RegistryError, match="critical"):
            engine.remove_migration_range(versions[0], versions[2])

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [], []],
                [UserV1, UserV2, UserV3],
                id="pydantic_semver_user_v1_v2_v3",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_remove_range_skips_gaps(
        self,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        """Range over consecutive pairs with no edges is a no-op."""
        versions = [envelope_model(engine.adapter, engine.settings, m) for m in models]
        for v in versions:
            engine.store_model(v)

        engine.remove_migration_range(versions[0], versions[2])
        assert engine.registry.kind_versions(versions[0].kind) == sorted(versions)

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [], []],
                [UserV1, UserV2],
                id="pydantic_semver_user_v1_v2",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_delete_kind_removes_all(
        self,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [envelope_model(engine.adapter, engine.settings, m) for m in models]
        for v in versions:
            engine.store_model(v)
        engine.store_migration((versions[0], versions[1]), lambda d: d)

        engine.delete_kind(versions[0].kind)

        for v in versions:
            assert v not in engine.registry
        assert (
            engine.registry.has_migration(
                SentinelEdge.from_pair(versions[0], versions[1])
            )
            is False
        )

    @pytest.mark.parametrize(
        "model_adapter, registry",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [], []],
                id="pydantic_semver_empty",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_delete_unknown_kind_noop(self, engine: Engine[types.VersionValue]) -> None:
        engine.delete_kind("Nope")

    @pytest.mark.parametrize(
        "model_adapter, registry, models, scenario",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [], []],
                [UserV1, UserV2],
                "add_remove",
                id="add_remove",
            ),
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [], []],
                [UserV1, UserV2],
                "clear",
                id="clear",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_add_and_remove_hook(
        self,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
        scenario: str,
    ) -> None:
        versions = [envelope_model(engine.adapter, engine.settings, m) for m in models]
        for v in versions:
            engine.store_model(v)
        engine.store_migration((versions[0], versions[1]), lambda d: d)

        key = SentinelEdge.from_pair(versions[0], versions[1])
        if scenario == "add_remove":
            hook = MigrationHook()
            engine.add_hook(SentinelEdge.from_pair(versions[0], versions[1]), hook)
            assert engine.registry.has_hooks(engine.registry.get_migration_by_edge(key))

            engine.remove_hook(SentinelEdge.from_pair(versions[0], versions[1]), hook)
            assert not engine.registry.has_hooks(
                engine.registry.get_migration_by_edge(key)
            )
            return

        engine.add_hook(
            SentinelEdge.from_pair(versions[0], versions[1]), MigrationHook()
        )
        engine.clear_hooks()
        assert not engine.registry._hooks


class TestReflection:
    """Engine reconstructs missing models implicitly on migration registration."""

    @pytest.mark.parametrize(
        "model_adapter, registry, migration_settings, models",
        [
            pytest.param(
                JsonSchemaModelAdapter,
                [semver.Version, "test", [USER_V1_0_0], []],
                {"on_missing": "reconstruct_model"},
                [USER_V1_0_0],
                id="json_semver_reconstruct_user_v1_0_0",
            ),
        ],
        indirect=["model_adapter", "registry", "migration_settings"],
    )
    def test_reconstructs_missing_model_on_store_migration(
        self,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        real, meta = (
            envelope_model(engine.adapter, engine.settings, models[0]),
            meta_versionable(engine.adapter, "User", "2.0.0"),
        )

        engine.store_migration(
            (meta, real),
            JsonPatchMigration(
                {
                    "from": "1.0.0",
                    "to": "2.0.0",
                    "ops": [{"op": "add", "path": "/age", "value": None}],
                }
            ).patch,
        )

        reconstructed = engine.get_model(
            VersionNode(_model=None, _value=semver.Version(2, 0, 0), _kind="User")
        )
        assert reconstructed.model is not None
        assert all(
            field in reconstructed.model.model_fields
            for field in ["name", "age", "version"]
        )
        assert reconstructed.model.model_fields["version"].default == "2.0.0"

    @pytest.mark.parametrize(
        "model_adapter, registry, migration_settings, models",
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [UserV2], []],
                {"on_missing": "skip"},
                [UserV2],
                id="pydantic_skip_user_v2",
            ),
        ],
        indirect=["model_adapter", "registry", "migration_settings"],
    )
    def test_skips_reconstruction_when_disabled(
        self,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        real = envelope_model(engine.adapter, engine.settings, models[0])
        meta = engine.adapter.versionable(None, kind="User", version="1.0.0")
        engine.store_model(meta)

        engine.store_migration((meta, real), lambda d: {**d, "age": None})

        stored = engine.get_model(
            VersionNode(_model=None, _value=semver.Version(1, 0, 0), _kind="User")
        )
        assert stored.model is None


class TestLookupTyped:
    """Engine operator overloads operate on typed keys only."""

    @pytest.mark.parametrize(
        "model_adapter, registry, model",
        [
            [PydanticModelAdapter, [semver.Version, "test", [UserV1], []], UserV1],
            [
                JsonSchemaModelAdapter,
                [pendulum.Date, "test", [USER_V0_1_1_DEV_7], []],
                USER_V0_1_1_DEV_7,
            ],
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_contains_typed_node(
        self,
        engine: Engine[types.VersionValue],
        model: ModelHandle,
    ) -> None:
        version = envelope_model(engine.adapter, engine.settings, model)
        assert version in engine
        assert engine[version].model is version.model

    @pytest.mark.parametrize(
        "model_adapter, registry, models",
        [
            [
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d: d)],
                ],
                [UserV1, UserV2],
            ],
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_getitem_typed_sentinel_edge(
        self,
        engine: Engine[types.VersionValue],
        models: list[ModelHandle],
    ) -> None:
        versions = [envelope_model(engine.adapter, engine.settings, m) for m in models]
        key = SentinelEdge.from_pair(versions[0], versions[1])
        assert engine[key].func is not None


class TestMigrationEntryIntegration:
    """Engine delegates per-entry migration to an injected MigrationEntry strategy."""

    @pytest.mark.parametrize(
        "model_adapter, registry",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [UserV1, UserV2],
                    [
                        ((UserV1, UserV2), lambda d: d),
                    ],
                ],
                id="pydantic",
            )
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_engine_uses_custom_entry_migration(
        self,
        engine: Engine[types.VersionValue],
    ) -> None:

        class _CustomTask:
            def run(self) -> dict[str, Any]:
                return {"custom": True}

        custom_strategy = MagicMock(spec=MigrationEntry)
        custom_strategy.migrate.return_value = _CustomTask()
        result = engine.migrate(
            {"kind": "User", "version": "1.0.0", "name": "Alice"},
            target=latest_target_resolver(engine.registry),
            entry_migration=custom_strategy,
        )

        assert result == {"custom": True}
        assert custom_strategy.migrate.call_count == 1
