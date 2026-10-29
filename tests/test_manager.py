from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any, Literal, cast

import pendulum
import pytest
import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.core import (
    ManagerMigrationKey,
    MigrationContext,
    MigrationKeyInput,
    ModelPair,
    VersionValue,
)
from pyverge.engine import Engine
from pyverge.execution.backends import AsyncBackend
from pyverge.manager.types import (
    ManagerClassState,
    ManagerInstanceState,
)
from pyverge.registry.errors import (
    CatalogError,
    ModelNotFoundError,
)
from pyverge.schemas import JsonSchemaModelAdapter, PydanticModelAdapter
from pyverge.schemas.types import (
    ModelAdapter,
    ModelHandle,
)
from pyverge.settings import MigrationSettings, VersioningSettings, manager_kwargs
from pyverge.versioning import Migratable, Versionable
from tests.examples.json import (
    USER_V1_0_0,
    USER_V1_2_3,
)
from tests.examples.pydantic.base import UserBaseModel
from tests.examples.pydantic.chrono import (
    UserV20250310,
    UserV20251231,
)
from tests.examples.pydantic.semver import (
    UserV1,
    UserV2,
    UserV3,
    migrate_v1_to_v2,
)
from tests.examples.pydantic.semver_nested import (
    AddressV1,
    AddressV2,
    AddressV3,
    PersonV1,
    PersonV2,
)
from tests.utils.engine import envelope_model


def _payload(version: str) -> dict:
    return {
        "document": {
            "kind": "User",
            "version": version,
            "name": "Alice",
            "email": "alice@example.com",
            "role": "user",
        }
    }


#: Nested semver models exercised by target-spec compilation.
NESTED_MODELS = [PersonV1, PersonV2, AddressV1, AddressV2, AddressV3]


class TestScoping:
    def test_explicit_engine_used_as_is(
        self,
        engine: Engine[VersionValue],
    ) -> None:
        UserManager = Manager[semver.Version].configure(
            engine.adapter,
            engine=cast("Engine[semver.Version]", engine),
        )

        assert UserManager._default_engine is engine


class TestClassLevelRegistration:
    def test_bare_model_decorator_derives_key(
        self, manager: type[Manager[semver.Version]]
    ) -> None:
        @manager.model
        class UserV1(UserBaseModel):
            version: Literal["1.0.0"] = "1.0.0"
            name: str

        @manager.model
        class UserV2(UserBaseModel):
            version: Literal["2.0.0"] = "2.0.0"
            name: str
            age: int | None = None

        versions = [str(v) for v in manager().registry.versions]
        assert versions == ["User@1.0.0", "User@2.0.0"]

    def test_jsonata_strategy_requires_expression(
        self, manager: type[Manager[semver.Version]]
    ) -> None:
        with pytest.raises(TypeError, match="expression"):

            @manager.migration("User", "1.0.0", "2.0.0", strategy="jsonata")
            class _Migration:
                pass

    def test_unscoped_registration_raises(self) -> None:
        with pytest.raises(AttributeError):
            Manager.model(UserV1)


class TestInstanceFacade:
    @pytest.mark.parametrize(
        ("model_adapter", "registry", "key"),
        [
            (
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2], []],
                ManagerMigrationKey("User", "1.0.0", "2.0.0"),
            ),
            (
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2], []],
                ModelPair(UserV1, UserV2),
            ),
            (
                PydanticModelAdapter,
                [pendulum.Date, "test", [UserV20250310, UserV20251231], []],
                ManagerMigrationKey("User", "2025-03-10", "2025-12-31"),
            ),
            (
                PydanticModelAdapter,
                [pendulum.Date, "test", [UserV20250310, UserV20251231], []],
                ModelPair(UserV20250310, UserV20251231),
            ),
        ],
        indirect=["model_adapter", "registry"],
        ids=["semver-str", "semver-model", "date-str", "date-model"],
    )
    def test_store_and_get_accepts_all_migration_key_forms(
        self,
        manager: type[Manager[VersionValue]],
        key: MigrationKeyInput,
    ) -> None:
        instance = manager()

        def _migrate(data: dict, context: MigrationContext | None = None) -> dict:
            return data

        instance.store_migration(key, _migrate)
        assert instance.get_migration(key).func is _migrate
        instance.remove_migration(key)

    @pytest.mark.parametrize(
        ("model_adapter", "registry", "model"),
        [
            (
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2], []],
                UserV2,
            ),
            (
                PydanticModelAdapter,
                [pendulum.Date, "test", [UserV20250310], []],
                UserV20250310,
            ),
            (
                JsonSchemaModelAdapter,
                [pendulum.Date, "test", [USER_V1_0_0, USER_V1_2_3], []],
                USER_V1_2_3,
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_find_model_hit(
        self,
        manager: type[Manager[VersionValue]],
        model: ModelHandle,
    ) -> None:
        instance = manager()
        version = envelope_model(instance.engine.adapter, None, model)
        found = instance.engine.get_model(version)
        assert found.descriptor == version.descriptor


class TestLookupHelpers:
    @pytest.mark.parametrize(
        ("model_adapter", "registry", "models", "versions", "payloads"),
        [
            (
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2], []],
                [UserV1, UserV2],
                ["1.0.0", "2.0.0"],
                [
                    {"name": "Alice", "email": "alice@example.com", "role": "user"},
                    {"name": "Alice", "email": "alice@example.com", "role": "user"},
                ],
            ),
            (
                PydanticModelAdapter,
                [pendulum.Date, "test", [UserV20250310, UserV20251231], []],
                [UserV20250310, UserV20251231],
                ["2025-03-10", "2025-12-31"],
                [
                    {"name": "Alice", "email": "alice@example.com", "role": "user"},
                    {"name": "Alice", "email": "alice@example.com", "role": "user"},
                ],
            ),
        ],
        indirect=["model_adapter", "registry"],
        ids=["semver", "date"],
    )
    def test_get_returns_versionable(
        self,
        manager: type[Manager],
        models: list[type[BaseModel]],
        versions: list[str],
        payloads: list[dict],
    ) -> None:
        """``get(kind, version_string)`` resolves the registered versionable.

        Regression: the string was parsed once by ``get`` and then parsed again
        by ``adapter.versionable``, whose ``of`` accepted only strings.
        """
        for model, version, payload in zip(models, versions, payloads, strict=True):
            assert (
                manager().engine.adapter.resolve(
                    manager.get("User", version).descriptor.ref
                )
                is model
            )
            manager().validate(payload, "User", version)

    @pytest.mark.parametrize(
        ("model_adapter", "registry", "missing_version"),
        [
            (
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1], []],
                "9.0.0",
            ),
            (
                PydanticModelAdapter,
                [pendulum.Date, "test", [UserV20250310], []],
                "2099-01-01",
            ),
        ],
        indirect=["model_adapter", "registry"],
        ids=["semver", "date"],
    )
    def test_get_unknown_raises(
        self,
        manager: type[Manager],
        missing_version: str,
    ) -> None:
        with pytest.raises(ModelNotFoundError):
            manager.get("User", missing_version)

    @pytest.mark.parametrize(
        ("model_adapter", "registry", "version"),
        [
            (
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1], []],
                "1.0.0",
            ),
            (
                PydanticModelAdapter,
                [pendulum.Date, "test", [UserV20250310], []],
                "2025-03-10",
            ),
        ],
        indirect=["model_adapter", "registry"],
        ids=["semver", "date"],
    )
    def test_get_kind_is_strict(
        self,
        manager: type[Manager],
        version: str,
    ) -> None:
        with pytest.raises(ModelNotFoundError):
            manager.get("user", version)

    @pytest.mark.parametrize(
        ("model_adapter", "registry", "latest"),
        [
            (
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2, UserV3], []],
                UserV3,
            ),
            (
                PydanticModelAdapter,
                [pendulum.Date, "test", [UserV20250310, UserV20251231], []],
                UserV20251231,
            ),
        ],
        indirect=["model_adapter", "registry"],
        ids=["semver", "date"],
    )
    def test_get_latest_returns_highest(
        self,
        manager: type[Manager],
        latest: type[BaseModel],
    ) -> None:
        assert manager.get_latest_model("User").model_id.endswith(latest.__name__)

    @pytest.mark.parametrize(
        ("model_adapter", "registry"),
        [
            (PydanticModelAdapter, [semver.Version, "test", [UserV1], []]),
            (PydanticModelAdapter, [pendulum.Date, "test", [UserV20250310], []]),
        ],
        indirect=["model_adapter", "registry"],
        ids=["semver", "date"],
    )
    def test_get_latest_unknown_kind_raises(
        self,
        manager: type[Manager],
    ) -> None:
        with pytest.raises(CatalogError):
            manager.get_latest_model("Missing")

    @pytest.mark.parametrize(
        ("model_adapter", "registry", "expected"),
        [
            (
                PydanticModelAdapter,
                [semver.Version, "test", [UserV3, UserV1, UserV2], []],
                [UserV1, UserV2, UserV3],
            ),
            (
                PydanticModelAdapter,
                [pendulum.Date, "test", [UserV20251231, UserV20250310], []],
                [UserV20250310, UserV20251231],
            ),
        ],
        indirect=["model_adapter", "registry"],
        ids=["semver", "date"],
    )
    def test_list_versions_ascending(
        self,
        manager: type[Manager],
        expected: list[type[BaseModel]],
    ) -> None:
        assert [
            manager().engine.adapter.resolve(n.descriptor.ref)
            for n in manager.list_versions("User")
        ] == expected
        assert manager.list_versions("Missing") == []

    @pytest.mark.parametrize(
        ("model_adapter", "registry"),
        [
            (
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [UserV2, AddressV1, UserV1],
                    [((UserV1, UserV2), migrate_v1_to_v2)],
                ],
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_get_entities(self, manager: type[Manager]) -> None:
        assert manager.get_entities() == ["Address", "User"]


class TestFluentLookup:
    """Manager owns the fluent lookup sugar; engine/registry are typed-only."""

    @pytest.mark.parametrize(
        ("model_adapter", "registry", "models", "key_factory", "expected"),
        [
            (
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2], []],
                [UserV1, UserV2],
                lambda versions: UserV1,
                True,
            ),
            (
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2], []],
                [UserV1, UserV2],
                lambda versions: UserV3,
                False,
            ),
            (
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2], []],
                [UserV1, UserV2],
                lambda versions: (versions[0].kind, versions[0].version),
                True,
            ),
            (
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2], []],
                [UserV1, UserV2],
                lambda versions: ("User", semver.Version(9, 9, 9)),
                False,
            ),
            (
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                lambda versions: (versions[0], versions[1]),
                True,
            ),
            (
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                lambda versions: (versions[1], versions[0]),
                False,
            ),
            (
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [UserV1, UserV2, UserV3],
                    [
                        ((UserV1, UserV2), lambda d, _: d),
                        ((UserV2, UserV3), lambda d, _: d),
                    ],
                ],
                [UserV1, UserV2, UserV3],
                lambda versions: slice(versions[0], versions[2]),
                True,
            ),
            (
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [UserV1, UserV2, UserV3],
                    [
                        ((UserV1, UserV2), lambda d, _: d),
                        ((UserV2, UserV3), lambda d, _: d),
                    ],
                ],
                [UserV1, UserV2, UserV3],
                lambda versions: slice(versions[2], versions[0]),
                False,
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_contains_fluent_keys(
        self,
        manager: type[Manager],
        models: list[ModelHandle],
        key_factory: Callable[..., object],
        expected: bool,
    ) -> None:
        instance = manager()
        versions = [envelope_model(instance.engine.adapter, None, m) for m in models]
        assert (key_factory(versions) in instance) is expected

    @pytest.mark.parametrize(
        ("model_adapter", "registry", "models", "selector", "kind"),
        [
            (
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2], []],
                [UserV1, UserV2],
                lambda versions: UserV1,
                "model",
            ),
            (
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2], []],
                [UserV1, UserV2],
                lambda versions: (versions[0].kind, versions[0].version),
                "model",
            ),
            (
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), lambda d, _: d)],
                ],
                [UserV1, UserV2],
                lambda versions: (versions[0], versions[1]),
                "edge",
            ),
            (
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [UserV1, UserV2, UserV3],
                    [
                        ((UserV1, UserV2), lambda d, _: d),
                        ((UserV2, UserV3), lambda d, _: d),
                    ],
                ],
                [UserV1, UserV2, UserV3],
                lambda versions: slice(versions[0], versions[2]),
                "path",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_getitem_fluent_keys(
        self,
        manager: type[Manager],
        models: list[ModelHandle],
        selector: Callable[..., object],
        kind: str,
    ) -> None:
        instance = manager()
        versions = [envelope_model(instance.engine.adapter, None, m) for m in models]
        result = instance[selector(versions)]
        if kind == "model":
            assert instance.engine.adapter.resolve(
                cast(Versionable, result).descriptor.ref
            ) in set(models)
        elif kind == "edge":
            assert cast(Migratable, result).func is not None
        else:
            branch = cast(list[Migratable], result)
            assert len(branch) == len(models) - 1

    @pytest.mark.parametrize(
        ("model_adapter", "registry", "models"),
        [
            (
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [UserV1, UserV2, UserV3],
                    [
                        ((UserV1, UserV2), lambda d, _: d),
                        ((UserV2, UserV3), lambda d, _: d),
                    ],
                ],
                [UserV1, UserV2, UserV3],
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_migration_path_fluent(
        self,
        manager: type[Manager],
        models: list[ModelHandle],
    ) -> None:
        instance = manager()
        path = instance.migration_path(UserV1, UserV3)
        assert len(path) == 2  # noqa: PLR2004


class TestSharedEngine:
    @pytest.mark.parametrize(
        ("model_adapter", "registry", "model", "version"),
        [
            (PydanticModelAdapter, [semver.Version, "test", [], []], UserV1, "1.0.0"),
            (
                PydanticModelAdapter,
                [pendulum.Date, "test", [], []],
                UserV20250310,
                "2025-03-10",
            ),
        ],
        indirect=["model_adapter", "registry"],
        ids=["semver", "date"],
    )
    def test_instances_get_independent_engine_copies(
        self,
        manager: type[Manager],
        model: type,
        version: str,
    ) -> None:
        manager.model(model)

        a, b = manager(), manager()
        assert a.engine is not b.engine
        assert a.engine is not manager._default_engine
        assert a.registry.versions == b.registry.versions

    @pytest.mark.parametrize(
        ("model_adapter", "registry", "model", "version"),
        [
            (PydanticModelAdapter, [semver.Version, "test", [], []], UserV1, "1.0.0"),
            (
                PydanticModelAdapter,
                [pendulum.Date, "test", [], []],
                UserV20250310,
                "2025-03-10",
            ),
        ],
        indirect=["model_adapter", "registry"],
        ids=["semver", "date"],
    )
    def test_instance_writes_do_not_leak_to_class(
        self,
        manager: type[Manager],
        model: type,
        version: str,
    ) -> None:
        manager_instance = manager()
        manager_instance.store_model(model)

        expected = f"User@{version}"
        assert [str(v) for v in manager_instance.registry.versions] == [expected]
        assert manager().registry.versions == []

    @pytest.mark.parametrize(
        ("model_adapter", "registry"),
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2], []],
                id="pydantic",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_instance_store_migration_updates_instance_engine(
        self, manager: type[Manager]
    ) -> None:
        instance = manager()
        key = ManagerMigrationKey("User", "1.0.0", "2.0.0")
        instance.store_migration(key, migrate_v1_to_v2)

        payload = {
            "kind": "User",
            "version": "1.0.0",
            "name": "Alice",
            "email": "alice@example.com",
            "role": "user",
        }
        assert instance.runner().run(payload, "2.0.0")["version"] == "2.0.0"
        assert manager._default_engine.registry.migrations("User") == []

    @pytest.mark.parametrize(
        ("model_adapter", "registry"),
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2], []],
                id="pydantic",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_instance_add_hook_updates_instance_engine(
        self, manager: type[Manager]
    ) -> None:
        instance = manager()
        key = ManagerMigrationKey("User", "1.0.0", "2.0.0")
        instance.store_migration(key, migrate_v1_to_v2)
        hook = cast("Any", object())
        instance.add_hook(key, hook)

        edge = instance.registry.migrations("User")[0]
        assert instance.registry.get_hooks(edge) == [hook]
        assert manager._default_engine.registry.hooks() == []

    @pytest.mark.parametrize(
        ("model_adapter", "registry"),
        [
            pytest.param(
                PydanticModelAdapter,
                [semver.Version, "test", [], []],
                id="pydantic",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_instance_lookup_sees_instance_only_model(
        self, manager: type[Manager]
    ) -> None:
        instance = manager()
        instance.store_model(UserV1)

        assert instance.get_model(UserV1).version == "1.0.0"
        assert [str(v) for v in instance.list_versions("User")] == ["User@1.0.0"]
        assert cast("Any", instance[UserV1]).version == "1.0.0"
        assert manager._default_engine.registry.versions == []

    @pytest.mark.parametrize(
        ("model_adapter", "registry", "model", "version"),
        [
            (PydanticModelAdapter, [semver.Version, "test", [], []], UserV1, "1.0.0"),
            (
                PydanticModelAdapter,
                [pendulum.Date, "test", [], []],
                UserV20250310,
                "2025-03-10",
            ),
        ],
        indirect=["model_adapter", "registry"],
        ids=["semver", "date"],
    )
    def test_class_registration_not_visible_to_existing_instances(
        self,
        manager: type[Manager],
        model: type,
        version: str,
    ) -> None:
        manager_instance = manager()
        manager.model(model)

        assert manager_instance.registry.versions == []


@pytest.mark.parametrize(
    ("source_cls", "spec", "expected"),
    [
        pytest.param(PersonV1, "skip", None, id="skip"),
        pytest.param(
            PersonV1,
            "latest",
            ("Person", semver.VersionInfo(2, 0, 0)),
            id="latest",
        ),
        pytest.param(
            AddressV2,
            "earliest",
            ("Address", semver.VersionInfo(1, 0, 0)),
            id="earliest",
        ),
        pytest.param(PersonV1, None, None, id="none"),
        pytest.param(
            PersonV1,
            PersonV2,
            ("Person", semver.VersionInfo(2, 0, 0)),
            id="model-class",
        ),
    ],
)
class TestCompileTargetSpec:
    """Unit tests for compiling a single target spec into a resolver."""

    @pytest.mark.parametrize(
        "model_adapter, registry",
        [
            [
                PydanticModelAdapter,
                [semver.Version, "test", NESTED_MODELS, []],
            ]
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_compile_target_spec(  # noqa: PLR0913, PLR0917
        self,
        manager: type[Manager[semver.Version]],
        model_adapter: PydanticModelAdapter,
        versioning_settings: VersioningSettings,
        source_cls: type[BaseModel],
        spec: str | type[BaseModel] | None,
        expected: tuple[str, semver.VersionInfo] | None,
    ) -> None:
        source = envelope_model(model_adapter, versioning_settings, source_cls)
        resolver = manager.compile_target_spec(spec)
        target = resolver(source)

        if expected is None:
            assert target is None
        else:
            assert target is not None
            assert (target.kind, target.version) == expected


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [semver.Version, "test", NESTED_MODELS, []],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_versionable_target_used_as_is(
    manager: type[Manager[semver.Version]],
    model_adapter: PydanticModelAdapter,
    versioning_settings: VersioningSettings,
) -> None:
    source = envelope_model(model_adapter, versioning_settings, PersonV1)
    target_node = envelope_model(model_adapter, versioning_settings, PersonV2)
    resolver = manager.compile_target_spec(target_node)
    assert resolver(source) == target_node


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [semver.Version, "test", NESTED_MODELS, []],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_unsupported_spec_raises(
    manager: type[Manager[semver.Version]],
) -> None:
    with pytest.raises(CatalogError):
        manager.compile_target_spec("unknown")


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [semver.Version, "test", NESTED_MODELS, []],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_model_class_wrong_kind_raises(
    manager: type[Manager[semver.Version]],
    model_adapter: PydanticModelAdapter,
    versioning_settings: VersioningSettings,
) -> None:
    source = envelope_model(model_adapter, versioning_settings, AddressV1)
    resolver = manager.compile_target_spec(PersonV2)
    with pytest.raises(CatalogError):
        resolver(source)


def test_unregistered_model_class_raises(
    manager: type[Manager[semver.Version]],
) -> None:
    with pytest.raises(CatalogError):
        manager.compile_target_spec(PersonV2)


# Structural conformance of the composed Manager with its state contracts: the
# class-level defaults established by ``configure`` and the instance-level
# bindings resolved at construction.


def test_configured_manager_satisfies_class_state_contract(
    migration_settings: MigrationSettings,
    model_adapter: ModelAdapter,
) -> None:
    manager_cls = Manager[semver.Version]
    configured: type[ManagerClassState[semver.Version]] = manager_cls.configure(
        model_adapter, **manager_kwargs(migration_settings)
    )
    assert configured._default_adapter is model_adapter
    assert configured._default_engine is not None
    assert configured._strategy is semver.Version
    assert callable(configured.configure)


def test_instantiated_manager_satisfies_instance_state_contract(
    migration_settings: MigrationSettings,
    model_adapter: ModelAdapter,
) -> None:
    configured = Manager[semver.Version].configure(
        model_adapter, **manager_kwargs(migration_settings)
    )
    instance: ManagerInstanceState[semver.Version] = configured()

    assert instance.engine is not configured._default_engine
    assert instance.registry is not configured._default_engine.registry
    assert instance.adapter is model_adapter


class TestMigrationContext:
    def test_create_is_a_view_over_source_mapping(self) -> None:
        source = {"tenant": "tenant_99"}
        context = MigrationContext.create(source)

        source["tenant"] = "tenant_100"

        assert context["tenant"] == "tenant_100"

    def test_create_is_idempotent(self) -> None:
        context = MigrationContext.create({"tenant": "tenant_99"})
        copy = MigrationContext.create(context)

        assert copy["tenant"] == context["tenant"]

    def test_create_empty(self) -> None:
        assert MigrationContext.create(None) == MigrationContext.empty()

    def test_rejects_mutation(self) -> None:
        context = MigrationContext.create({"tenant": "tenant_99"})

        with pytest.raises(TypeError):
            context["tenant"] = "tenant_100"


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [UserV1, UserV2],
                [((UserV1, UserV2), migrate_v1_to_v2)],
            ],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_engine_explore_build_mode(manager: type[Manager]) -> None:
    engine = manager._default_engine
    explorer = engine.explore()
    source = engine.get_model(engine.adapter.version_key(kind="User", version="1.0.0"))
    target = engine.get_model(engine.adapter.version_key(kind="User", version="2.0.0"))

    assert explorer.versions("User") == engine.registry.kind_versions("User")
    assert explorer.path(source, target) == [(source, target)]


@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [UserV1, UserV2],
                [((UserV1, UserV2), migrate_v1_to_v2)],
            ],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_manager_runner_sync_and_async_handles(
    manager: type[Manager],
) -> None:
    instance = manager()
    sync_result = instance.runner().run(
        _payload("1.0.0"),
        "latest",
        container=None,
        max_depth=-1,
        context=None,
    )
    assert sync_result["document"]["version"] == "2.0.0"

    pending = instance.runner(
        runtime=AsyncBackend(
            backend="asyncio",
            backend_options={},
            max_workers=0,
        )
    ).run(
        _payload("1.0.0"),
        "latest",
        container=None,
        max_depth=-1,
        context=None,
    )
    assert inspect.isawaitable(pending)
    async_result = asyncio.run(pending)
    assert async_result["document"]["version"] == "2.0.0"


@pytest.mark.parametrize("manager", ["orders"], indirect=True)
@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        [
            PydanticModelAdapter,
            [
                semver.Version,
                "test",
                [UserV1, UserV2],
                [((UserV1, UserV2), migrate_v1_to_v2)],
                "orders",
            ],
        ]
    ],
    indirect=["model_adapter", "registry"],
)
def test_manager_defaults_empty_namespace(
    model_adapter: ModelAdapter,
    manager: type[Manager[semver.Version]],
) -> None:
    instance = manager()
    node = instance.get_model(UserV1)
    assert instance.registry.namespace == "orders"
    assert node.namespace == "orders"
    assert node.modelref == instance.adapter.ref(UserV1)
