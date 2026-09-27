from __future__ import annotations

from typing import Literal

import pendulum
import pytest
import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.adapters import JsonSchemaModelAdapter
from pyverge.core import (
    DiscoveryValidationError,
    MigrationHook,
    MigrationSettings,
    ModelNotFoundError,
    RegistryError,
    VersioningSettings,
)
from pyverge.migration import (
    Engine,
    PydanticModelAdapter,
    PydanticWalker,
)
from pyverge.types import (
    ManagerClassState,
    ManagerInstanceState,
    ManagerMigrationKey,
    MigrationKeyInput,
    ModelAdapter,
    ModelBase,
    ModelPair,
    VersionValue,
    VModel,
)
from tests.examples.json import (
    USER_V1_0_0,
    USER_V1_2_3,
    USER_V2_0_0,
    USER_V2025_01_01,
    USER_V2025_03_10,
    migrate_v20250101_to_v20250310,
)
from tests.examples.pydantic.base import UserBaseModel
from tests.examples.pydantic.chrono import (
    UserV20250310,
    UserV20251231,
)
from tests.examples.pydantic.semver import (
    UserContainer,
    UserV1,
    UserV2,
    UserV3,
    migrate_v1_to_v2,
    migrate_v2_to_v3,
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
            engine.settings, engine.adapter, engine=engine
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
        assert versions == ["User:1.0.0", "User:2.0.0"]

    @pytest.mark.parametrize("model_adapter, registry, key", [
        pytest.param(
            PydanticModelAdapter, [semver.Version, "test", [UserV1, UserV2], []],
            ("User", "1.0.0", "2.0.0"),
            id="pydantic_semver_user_v1_v2_migration_string"
        ),
        pytest.param(
            PydanticModelAdapter, [semver.Version, "test", [UserV1, UserV2], []],
            (UserV1, UserV2),
            id="pydantic_semver_user_v1_v2_migration_schema"
        ),
        pytest.param(
            PydanticModelAdapter, [semver.Version, "test", [UserV1, UserV2], []],
            (ModelPair(UserV1, UserV2)),
            id="pydantic_semver_user_v1_v2_migration_model_pair"
        ),
        pytest.param(
            JsonSchemaModelAdapter, [semver.Version, "test", [USER_V1_0_0, USER_V2_0_0], []],
            ("User", "1.0.0", "2.0.0"),
            id="json_schema_semver_user_v1_v2_migration_string"
        ),
        pytest.param(
            JsonSchemaModelAdapter, [semver.Version, "test", [USER_V1_0_0, USER_V2_0_0], []],
            (USER_V1_0_0, USER_V2_0_0),
            id="json_schema_semver_user_v1_v2_migration_schema"
        ),
    ], indirect=["model_adapter", "registry"])
    def test_migration_decorator(
        self,
        manager: type[Manager[VersionValue]],
        key: tuple[str, str, str] | tuple[ModelBase, ModelBase],
    ) -> None:

        @manager.migration(*key, backward_compatible=True)
        def migrate(data: dict) -> dict:
            return migrate_v1_to_v2(data)

        result = manager().migrate(_payload("1.0.0"))
        assert result["document"]["version"] == "2.0.0"

    @pytest.mark.parametrize(
        "model_adapter, registry, key, anchor",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [UserV1, UserV2],
                    [((UserV1, UserV2), migrate_v1_to_v2)],
                ],
                ("User", "1.0.0", "2.0.0"),
                "1.0.0",
                id="pydantic_semver_user_v1_v2_string"
            ),
            pytest.param(
                JsonSchemaModelAdapter,
                [
                    pendulum.Date,
                    "test",
                    [USER_V2025_01_01, USER_V2025_03_10],
                    [((USER_V2025_01_01, USER_V2025_03_10), migrate_v20250101_to_v20250310)]
                ],
                ("User", "2025-01-01", "2025-03-10"),
                "2025-01-01",
                id="json_schema_semver_user_v1_v2_string"
            ),
        ],
        indirect=["model_adapter", "registry"]
    )
    def test_hook_decorator(
        self,
        manager: type[Manager[semver.Version]],
        key: tuple[str, str, str] | tuple[ModelBase, ModelBase],
        anchor: str,
    ) -> None:
        class CountingHook(MigrationHook):
            def __init__(self) -> None:
                self.calls = 0

            def before_migrate(self, name, from_version, to_version, data) -> None:
                self.calls += 1

        hook = CountingHook()

        @manager.hook(*key, hook)
        class _HookMarker:
            pass

        manager().migrate(_payload(anchor))
        assert hook.calls == 1

    def test_unscoped_registration_raises(self) -> None:
        with pytest.raises(AttributeError):
            Manager.model(UserV1)


class TestInstanceFacade:
    def test_runtime_registration_during_init(
        self, manager: type[Manager[semver.Version]]
    ) -> None:
        class RuntimeManager(manager):  # ty: ignore
            def __init__(self) -> None:
                super().__init__()
                self.store_model(UserV1)
                self.store_model(UserV2)
                self.store_migration(ModelPair(UserV1, UserV2), migrate_v1_to_v2)

        instance = RuntimeManager()
        assert {str(v) for v in instance.registry.versions} == {
            "User:1.0.0",
            "User:2.0.0",
        }
        assert instance.migrate(_payload("1.0.0"))["document"]["version"] == "2.0.0"

    def test_schema_registry_style_registration(
        self, manager: type[Manager[semver.Version]]
    ) -> None:
        instance = manager()
        # Adapter-driven registration at runtime, e.g. loaded from a schema registry.
        instance.store_model(UserV1)
        instance.store_model(UserV2)
        instance.store_model(UserV3)
        instance.store_migration(ModelPair(UserV1, UserV2), migrate_v1_to_v2)
        instance.store_migration(ModelPair(UserV2, UserV3), migrate_v2_to_v3)

        assert instance.migrate(_payload("1.0.0"))["document"]["version"] == "3.0.0"

    @pytest.mark.parametrize(
        "model_adapter, registry, key",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [UserV1, UserV2],
                    []
                ],
                ManagerMigrationKey("User", "1.0.0", "2.0.0"),
                id="pydantic_semver_user_v1_v2"
            ),
        ],
        indirect=["model_adapter", "registry"]
    )
    def test_migration_string_triple_form(
        self,
        manager: type[Manager[semver.Version]],
        key: ManagerMigrationKey,
    ) -> None:
        instance = manager()
        instance.store_migration(
            key, migrate_v1_to_v2
        )

        assert instance.migrate(_payload("1.0.0"))["document"]["version"] == "2.0.0"

    @pytest.mark.parametrize(
        "model_adapter, registry, key",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [UserV1, UserV2],
                    [
                        ((UserV1, UserV2), migrate_v1_to_v2)
                    ]
                ],
                ManagerMigrationKey("User", "1.0.0", "2.0.0"),
                id="pydantic_semver_user_v1_v2"
            ),
        ],
        indirect=["model_adapter", "registry"]
    )
    def test_hook_via_instance_proxy(
        self, manager: type[Manager[semver.Version]], key: ManagerMigrationKey
    ) -> None:
        instance = manager()

        class CountingHook(MigrationHook):
            def __init__(self) -> None:
                self.calls = 0

            def before_migrate(self, name, from_version, to_version, data) -> None:
                self.calls += 1

        hook = CountingHook()
        instance.add_hook(key, hook)

        instance.migrate(_payload("1.0.0"))
        assert hook.calls == 1

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

        def _migrate(data: dict) -> dict:
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
        model: type[VModel],
    ) -> None:
        instance = manager()
        version = envelope_model(
            instance.engine.adapter, instance.engine.settings, model
        )
        found = instance.engine.get_model(version)
        assert found.model is version.model


class TestLookupHelpers:
    @pytest.mark.parametrize(
        ("model_adapter", "registry", "models", "versions"),
        [
            (
                PydanticModelAdapter,
                [semver.Version, "test", [UserV1, UserV2], []],
                [UserV1, UserV2],
                ["1.0.0", "2.0.0"],
            ),
            (
                PydanticModelAdapter,
                [pendulum.Date, "test", [UserV20250310, UserV20251231], []],
                [UserV20250310, UserV20251231],
                ["2025-03-10", "2025-12-31"],
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
    ) -> None:
        for model, version in zip(models, versions, strict=True):
            assert manager.get("User", version).model is model

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
        assert manager.get_latest_model("User").model is latest

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
        with pytest.raises(RegistryError):
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
        assert [n.model for n in manager.list_versions("User")] == expected
        assert manager.list_versions("Missing") == []


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
    def test_instances_share_class_engine(
        self,
        manager: type[Manager],
        model: type,
        version: str,
    ) -> None:
        manager.model(model)

        a, b = manager(), manager()
        assert a.engine is b.engine
        assert a.engine is manager._default_engine

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
    def test_instance_writes_visible_to_class(
        self,
        manager: type[Manager],
        model: type,
        version: str,
    ) -> None:
        manager_instance = manager()
        manager_instance.store_model(model)  # ty: ignore

        expected = f"User:{version}"
        assert [str(v) for v in manager_instance.registry.versions] == [expected]
        assert [str(v) for v in manager().registry.versions] == [expected]

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
    def test_class_registration_visible_to_existing_instances(
        self,
        manager: type[Manager],
        model: type,
        version: str,
    ) -> None:
        manager_instance = manager()
        manager.model(model)

        assert {str(v) for v in manager_instance.registry.versions} == {
            f"User:{version}"
        }


class TestMigrateInstanceOnly:
    def test_migrate_not_available_on_class(
        self, manager: type[Manager[semver.Version]]
    ) -> None:
        with pytest.raises(TypeError):
            manager.migrate({})  # ty: ignore

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
    def test_instance_migrate(self, manager: type[Manager[semver.Version]]) -> None:
        result = manager().migrate(_payload("1.0.0"))
        assert result["document"]["version"] == "2.0.0"
        assert result["document"]["age"] is None


class TestMigrateWithContainer:
    def test_container_guided_migration(
        self,
        migration_settings: MigrationSettings,
        model_adapter: PydanticModelAdapter,
        walker: PydanticWalker,
    ) -> None:
        UserManager = Manager[semver.Version].configure(
            migration_settings,
            model_adapter,
            walker=walker,
        )
        UserManager.model(UserV1)
        UserManager.model(UserV2)
        UserManager.migration("User", "1.0.0", "2.0.0")(migrate_v1_to_v2)

        result = UserManager().migrate(_payload("1.0.0"), container=UserContainer)
        assert result.document.version == "2.0.0"

    def test_container_returns_typed_instance(
        self,
        migration_settings: MigrationSettings,
        model_adapter: PydanticModelAdapter,
        walker: PydanticWalker,
    ) -> None:
        UserManager = Manager[semver.Version].configure(
            migration_settings,
            model_adapter,
            walker=walker,
        )
        UserManager.model(UserV1)
        UserManager.model(UserV2)
        UserManager.migration("User", "1.0.0", "2.0.0")(migrate_v1_to_v2)

        result = UserManager().migrate(_payload("1.0.0"), container=UserContainer)
        assert isinstance(result, UserContainer)
        assert result.document.version == "2.0.0"

    def test_container_validates_payload(
        self,
        migration_settings: MigrationSettings,
        model_adapter: PydanticModelAdapter,
        walker: PydanticWalker,
    ) -> None:
        UserManager = Manager[semver.Version].configure(
            migration_settings,
            model_adapter,
            walker=walker,
        )
        UserManager.model(UserV1)
        UserManager.model(UserV2)
        UserManager.migration("User", "1.0.0", "2.0.0")(migrate_v1_to_v2)

        invalid = {
            "document": {
                "kind": "User",
                "version": "1.0.0",
                "name": "Alice",
                "email": "alice@example.com",
                "role": "bogus",
            }
        }
        with pytest.raises(DiscoveryValidationError):
            UserManager().migrate(invalid, container=UserContainer)


class TestTargetPolicy:
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
    def test_default_target_latest(
        self, manager: type[Manager[semver.Version]]
    ) -> None:
        result = manager().migrate(_payload("1.0.0"))
        assert result["document"]["version"] == "2.0.0"

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
    def test_explicit_string_target(
        self, manager: type[Manager[semver.Version]]
    ) -> None:
        result = manager().migrate(_payload("1.0.0"), target="skip")
        assert result["document"]["version"] == "1.0.0"

    @pytest.mark.parametrize(
        "model_adapter, registry",
        [
            [
                PydanticModelAdapter,
                [
                    semver.Version,
                    "test",
                    [UserV1, UserV2, UserV3],
                    [
                        ((UserV1, UserV2), migrate_v1_to_v2),
                        ((UserV2, UserV3), migrate_v2_to_v3),
                    ],
                ],
            ]
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_per_kind_policy_with_wildcard(
        self, manager: type[Manager[semver.Version]]
    ) -> None:
        result = manager().migrate(
            _payload("1.0.0"),
            target={"Other": "skip", "*": "latest"},
        )
        assert result["document"]["version"] == "3.0.0"


@pytest.mark.parametrize(
    ("source_cls", "spec", "expected"),
    [
        pytest.param(
            PersonV1,
            "skip",
            None,
            id="skip",
        ),
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
        pytest.param(
            PersonV1,
            None,
            None,
            id="none",
        ),
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
    def test_compile_target_spec(  # noqa: PLR0913
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
            assert target.version == expected


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
    with pytest.raises(RegistryError):
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
    with pytest.raises(RegistryError):
        resolver(source)


def test_unregistered_model_class_raises(
    manager: type[Manager[semver.Version]],
) -> None:
    with pytest.raises(RegistryError):
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
        migration_settings, model_adapter
    )

    assert configured._default_settings is migration_settings
    assert configured._default_adapter is model_adapter
    assert configured._default_engine is not None
    assert configured._strategy is semver.Version
    assert callable(configured.configure)


def test_instantiated_manager_satisfies_instance_state_contract(
    migration_settings: MigrationSettings,
    model_adapter: ModelAdapter,
) -> None:
    configured = Manager[semver.Version].configure(migration_settings, model_adapter)
    instance: ManagerInstanceState[semver.Version] = configured()

    assert instance.engine is configured._default_engine
    assert instance.registry is configured._default_engine.registry
    assert instance.settings is migration_settings
    assert instance.adapter is model_adapter
