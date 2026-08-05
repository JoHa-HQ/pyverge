"""Usage-example tests for the ModelManager public facade.

Documents the intended API through executable examples:

* ``ModelManager.scoped(strategy, adapter, *, settings=...)`` builds a configured
  class carrying a class-level ``Registry`` and ``Engine``.
* ``model`` / ``migration`` / ``hook`` decorators register entities at class
  level only — they are not available on instances.
* Instances share the class-level ``Engine`` and ``Registry``.
"""

from __future__ import annotations

from typing import Literal

import pendulum
import pytest
import semver

from pyverge.migration import (
    DiscoveryValidationError,
    MigrationHook,
    MigrationSettings,
    ModelManager,
    PydanticModelAdapter,
    PydanticWalker,
    Registry,
)
from tests.examples.pydantic.base import UserBaseModel
from tests.examples.pydantic.chrono import (
    UserV20250310,
    UserV20251231,
)
from tests.examples.pydantic.chrono import (
    migrate_v1_to_v2 as migrate_chrono_v1_to_v2,
)
from tests.examples.pydantic.semver import (
    UserContainer,
    UserV1,
    UserV2,
    UserV3,
    migrate_v1_to_v2,
    migrate_v2_to_v3,
)
from tests.utils import make_engine


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


class TestScoping:
    def test_strategy_only_defaults(
        self, semver_manager: type[ModelManager[semver.Version]]
    ) -> None:
        assert semver_manager._strategy is semver.Version
        assert isinstance(semver_manager().registry, Registry)
        assert semver_manager().registry.versions == []

    def test_strategy_settings_adapter(self) -> None:
        settings = MigrationSettings(version_property="v", kind_property="k")
        adapter = PydanticModelAdapter(version_property="v", kind_property="k")
        UserManager = ModelManager.scoped(semver.Version, adapter, settings=settings)

        assert UserManager._settings is settings
        assert UserManager._adapter is adapter

    def test_explicit_engine_used_as_is(self) -> None:
        registry = Registry[semver.Version]()
        engine = make_engine(registry, MigrationSettings())
        UserManager = ModelManager.scoped(
            semver.Version, PydanticModelAdapter(), engine=engine
        )

        assert UserManager._engine is engine

    def test_engine_missing_strategy_raises(self) -> None:
        with pytest.raises(ValueError):
            ModelManager().engine

    def test_date_strategy(
        self, chrono_manager: type[ModelManager[pendulum.Date]]
    ) -> None:
        assert chrono_manager._strategy is pendulum.Date

    def test_class_decorators_not_available_on_instance(
        self, semver_manager: type[ModelManager[semver.Version]]
    ) -> None:
        manager = semver_manager()
        for attr in ("model", "migration", "hook"):
            with pytest.raises(AttributeError):
                getattr(manager, attr)


class TestClassLevelRegistration:
    def test_bare_model_decorator_derives_key(
        self, semver_manager: type[ModelManager[semver.Version]]
    ) -> None:
        @semver_manager.model()
        class UserV1(UserBaseModel):
            version: Literal["1.0.0"] = "1.0.0"
            name: str

        @semver_manager.model()
        class UserV2(UserBaseModel):
            version: Literal["2.0.0"] = "2.0.0"
            name: str
            age: int | None = None

        versions = [str(v) for v in semver_manager().registry.versions]
        assert versions == ["User:1.0.0", "User:2.0.0"]

    def test_direct_class_form(
        self, semver_manager: type[ModelManager[semver.Version]]
    ) -> None:
        semver_manager.model(UserV1)
        semver_manager.model(UserV2)

        assert {str(v) for v in semver_manager().registry.versions} == {
            "User:1.0.0",
            "User:2.0.0",
        }

    def test_migration_decorator(
        self, semver_manager: type[ModelManager[semver.Version]]
    ) -> None:
        semver_manager.model(UserV1)
        semver_manager.model(UserV2)

        @semver_manager.migration("User", "1.0.0", "2.0.0", backward_compatible=True)
        def migrate(data: dict) -> dict:
            return migrate_v1_to_v2(data)

        result = semver_manager().migrate(_payload("1.0.0"))
        assert result["document"]["version"] == "2.0.0"

    def test_migration_class_pair(
        self, semver_manager: type[ModelManager[semver.Version]]
    ) -> None:
        semver_manager.model(UserV1)
        semver_manager.model(UserV2)

        @semver_manager.migration(UserV1, UserV2)
        def migrate(data: dict) -> dict:
            return migrate_v1_to_v2(data)

        result = semver_manager().migrate(_payload("1.0.0"))
        assert result["document"]["version"] == "2.0.0"

    def test_hook_decorator(
        self, semver_manager: type[ModelManager[semver.Version]]
    ) -> None:
        semver_manager.model(UserV1)
        semver_manager.model(UserV2)
        semver_manager.migration("User", "1.0.0", "2.0.0")(migrate_v1_to_v2)

        class CountingHook(MigrationHook):
            def __init__(self) -> None:
                self.calls = 0

            def before_migrate(self, name, from_version, to_version, data) -> None:
                self.calls += 1

        hook = CountingHook()

        @semver_manager.hook("User", "1.0.0", "2.0.0", hook)
        class _HookMarker:
            pass

        semver_manager().migrate(_payload("1.0.0"))
        assert hook.calls == 1

    def test_chrono_class_level(
        self, chrono_manager: type[ModelManager[pendulum.Date]]
    ) -> None:
        chrono_manager.model(UserV20250310)
        chrono_manager.model(UserV20251231)

        @chrono_manager.migration("User", "2025-03-10", "2025-12-31")
        def migrate(data: dict) -> dict:
            return migrate_chrono_v1_to_v2(data)

        result = chrono_manager().migrate(_payload("2025-03-10"))
        assert result["document"]["version"] == "2025-12-31"

    def test_unscoped_registration_raises(self) -> None:
        with pytest.raises(TypeError, match="scoped"):
            ModelManager.model(UserV1)


class TestInstanceFacade:
    def test_runtime_registration_during_init(
        self, semver_manager: type[ModelManager[semver.Version]]
    ) -> None:
        class RuntimeManager(semver_manager):
            def __init__(self) -> None:
                super().__init__()
                self.store_model(UserV1)
                self.store_model(UserV2)
                self.store_migration((UserV1, UserV2), migrate_v1_to_v2)

        manager = RuntimeManager()
        assert {str(v) for v in manager.registry.versions} == {
            "User:1.0.0",
            "User:2.0.0",
        }
        assert manager.migrate(_payload("1.0.0"))["document"]["version"] == "2.0.0"

    def test_schema_registry_style_registration(
        self, semver_manager: type[ModelManager[semver.Version]]
    ) -> None:
        manager = semver_manager()
        # Adapter-driven registration at runtime, e.g. loaded from a schema registry.
        manager.store_model(UserV1)
        manager.store_model(UserV2)
        manager.store_model(UserV3)
        manager.store_migration((UserV1, UserV2), migrate_v1_to_v2)
        manager.store_migration((UserV2, UserV3), migrate_v2_to_v3)

        assert manager.migrate(_payload("1.0.0"))["document"]["version"] == "3.0.0"

    def test_migration_string_triple_form(
        self, semver_manager: type[ModelManager[semver.Version]]
    ) -> None:
        manager = semver_manager()
        manager.store_model(UserV1)
        manager.store_model(UserV2)
        manager.store_migration(("User", "1.0.0", "2.0.0"), migrate_v1_to_v2)

        assert manager.migrate(_payload("1.0.0"))["document"]["version"] == "2.0.0"

    def test_hook_via_instance_proxy(
        self, semver_manager: type[ModelManager[semver.Version]]
    ) -> None:
        manager = semver_manager()
        manager.store_model(UserV1)
        manager.store_model(UserV2)
        manager.store_migration(("User", "1.0.0", "2.0.0"), migrate_v1_to_v2)

        class CountingHook(MigrationHook):
            def __init__(self) -> None:
                self.calls = 0

            def before_migrate(self, name, from_version, to_version, data) -> None:
                self.calls += 1

        hook = CountingHook()
        manager.add_hook(("User", "1.0.0", "2.0.0"), hook)

        manager.migrate(_payload("1.0.0"))
        assert hook.calls == 1


class TestSharedEngine:
    @pytest.mark.parametrize(
        ("manager", "model", "version"),
        [
            (semver.Version, UserV1, "1.0.0"),
            (pendulum.Date, UserV20250310, "2025-03-10"),
        ],
        indirect=["manager"],
        ids=["semver", "date"],
    )
    def test_instances_share_class_engine(
        self,
        manager: type[ModelManager],
        model: type,
        version: str,
    ) -> None:
        manager.model(model)

        a, b = manager(), manager()
        assert a.engine is b.engine
        assert a.engine is manager._engine

    @pytest.mark.parametrize(
        ("manager", "model", "version"),
        [
            (semver.Version, UserV1, "1.0.0"),
            (pendulum.Date, UserV20250310, "2025-03-10"),
        ],
        indirect=["manager"],
        ids=["semver", "date"],
    )
    def test_instance_writes_visible_to_class(
        self,
        manager: type[ModelManager],
        model: type,
        version: str,
    ) -> None:
        manager_instance = manager()
        manager_instance.store_model(model)

        expected = f"User:{version}"
        assert [str(v) for v in manager_instance.registry.versions] == [expected]
        assert [str(v) for v in manager().registry.versions] == [expected]

    @pytest.mark.parametrize(
        ("manager", "model", "version"),
        [
            (semver.Version, UserV1, "1.0.0"),
            (pendulum.Date, UserV20250310, "2025-03-10"),
        ],
        indirect=["manager"],
        ids=["semver", "date"],
    )
    def test_class_registration_visible_to_existing_instances(
        self,
        manager: type[ModelManager],
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
        self, semver_manager: type[ModelManager[semver.Version]]
    ) -> None:
        with pytest.raises(TypeError):
            semver_manager.migrate({})

    def test_instance_migrate(
        self, semver_manager: type[ModelManager[semver.Version]]
    ) -> None:
        semver_manager.model(UserV1)
        semver_manager.model(UserV2)
        semver_manager.migration("User", "1.0.0", "2.0.0")(migrate_v1_to_v2)

        result = semver_manager().migrate(_payload("1.0.0"))
        assert result["document"]["version"] == "2.0.0"
        assert result["document"]["age"] is None


class TestMigrateWithContainer:
    @pytest.mark.parametrize("walker", [PydanticWalker], indirect=["walker"])
    def test_container_guided_migration(self, walker) -> None:
        UserManager = ModelManager.scoped(
            semver.Version,
            PydanticModelAdapter(),
            walker=walker,
        )
        UserManager.model(UserV1)
        UserManager.model(UserV2)
        UserManager.migration("User", "1.0.0", "2.0.0")(migrate_v1_to_v2)

        result = UserManager().migrate(_payload("1.0.0"), container=UserContainer)
        assert result.document.version == "2.0.0"

    @pytest.mark.parametrize("walker", [PydanticWalker], indirect=["walker"])
    def test_container_returns_typed_instance(self, walker) -> None:
        UserManager = ModelManager.scoped(
            semver.Version,
            PydanticModelAdapter(),
            walker=walker,
        )
        UserManager.model(UserV1)
        UserManager.model(UserV2)
        UserManager.migration("User", "1.0.0", "2.0.0")(migrate_v1_to_v2)

        result = UserManager().migrate(_payload("1.0.0"), container=UserContainer)
        assert isinstance(result, UserContainer)
        assert result.document.version == "2.0.0"

    @pytest.mark.parametrize("walker", [PydanticWalker], indirect=["walker"])
    def test_container_validates_payload(self, walker) -> None:
        UserManager = ModelManager.scoped(
            semver.Version,
            PydanticModelAdapter(),
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
