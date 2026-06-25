from __future__ import annotations

from typing import ForwardRef, get_args

from pydantic_migrator import ModelManager, ModelVersion
from pydantic_migrator.versioned_model import VersionedModel
from tests.conftest import (
    TypedDiscUserModel,
    TypedDiscUserV1,
    TypedDiscUserV2,
    TypedUserModel,
    TypedUserV1,
    TypedUserV2,
)


class FakeManager:
    pass


def test_versioned_model_load() -> None:
    vm = VersionedModel(FakeManager(), "User", "2.0.0", TypedUserV2)  # ty: ignore[invalid-argument-type]

    user = vm.load({"name": "Alice", "email": "a@b.com"})

    assert isinstance(user, TypedUserV2)
    assert user.name == "Alice"
    assert vm.cls is TypedUserV2
    assert vm._versioned_type is TypedUserV2
    assert vm._container_type is None


def test_versioned_model_runtime_types(
    typed_manager: ModelManager[TypedUserModel],
) -> None:
    @typed_manager.register[TypedUserV2]("User", "2.0.0")
    class _UserV2(TypedUserV2):
        pass

    vm = typed_manager.get("User", "2.0.0")

    assert vm._container_type == TypedUserModel
    assert vm._versioned_type is _UserV2
    assert vm.cls is _UserV2


def test_manager_orig_class_from_generic(
    typed_manager: ModelManager[TypedUserModel],
) -> None:
    orig = getattr(typed_manager, "__orig_class__", None)

    assert orig is not None
    assert get_args(orig)[0] == TypedUserModel


def test_container_type_with_generic(
    typed_manager: ModelManager[TypedUserModel],
) -> None:
    assert typed_manager.container_type == TypedUserModel


def test_forward_ref_manager_annotation() -> None:
    mgr: ModelManager["TypedUserModel"] = ModelManager["TypedUserModel"]()  # noqa: UP037

    container_type = mgr.container_type
    assert isinstance(container_type, ForwardRef)
    assert container_type.__forward_arg__ == "TypedUserModel"


def test_manager_container_type_without_generic() -> None:
    manager = ModelManager()

    assert manager.container_type is None


def test_manager_version_map_starts_empty(
    typed_manager: ModelManager[TypedUserModel],
) -> None:
    assert typed_manager._version_map == {}


def test_register_subscript(typed_manager: ModelManager[TypedUserModel]) -> None:
    @typed_manager.register[TypedUserV2]("User", "2.0.0")
    class _UserV2(TypedUserV2):
        pass

    vm = typed_manager._version_map[("User", ModelVersion.parse("2.0.0"))]

    assert vm.cls is _UserV2
    assert typed_manager.list_models() == ["User"]
    user = vm.load({"name": "Alice", "email": "a@b.com"})
    assert user.name == "Alice"


def test_model_decorator_populates_version_map(
    typed_manager: ModelManager[TypedUserModel],
) -> None:
    @typed_manager.model("User", "1.0.0")
    class _UserV1(TypedUserV1):
        pass

    vm = typed_manager.get("User", "1.0.0")

    assert vm.cls is _UserV1
    assert isinstance(vm, VersionedModel)


def test_get_returns_versioned_model(
    typed_manager: ModelManager[TypedUserModel],
) -> None:
    @typed_manager.register[TypedUserV2]("User", "2.0.0")
    class _UserV2(TypedUserV2):
        pass

    vm = typed_manager.get("User", "2.0.0")

    assert vm.cls is _UserV2
    assert vm.load({"name": "Bob", "email": "bob@x.com"}).email == "bob@x.com"


def test_get_latest_returns_versioned_model(manager: ModelManager) -> None:
    vm = manager.get_latest("User")

    assert isinstance(vm, VersionedModel)
    assert "status" in vm.cls.model_fields


def test_backward_compat_get_returns_versioned_model(manager: ModelManager) -> None:
    vm = manager.get("User", "1.0.0")

    assert isinstance(vm, VersionedModel)
    assert "role" in vm.cls.model_fields
    assert manager.container_type is None


def test_discriminated_union_load() -> None:
    manager = ModelManager[TypedDiscUserModel]()

    @manager.register[TypedDiscUserV1]("User", "1.0.0")
    class _UserV1(TypedDiscUserV1):
        pass

    @manager.register[TypedDiscUserV2]("User", "2.0.0")
    class _UserV2(TypedDiscUserV2):
        pass

    v2 = manager.get("User", "2.0.0").load(
        {"schema_version": "2.0.0", "name": "Alice", "email": "a@b.com"}
    )
    v1 = manager.get("User", "1.0.0").load({"schema_version": "1.0.0", "name": "Bob"})

    assert v2.email == "a@b.com"
    assert v1.name == "Bob"
