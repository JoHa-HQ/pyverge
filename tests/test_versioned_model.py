"""Tests for VersionedModel internals.

Uses minimal inline models — not from examples — because these tests
exercise VersionedModel internals (not the registration patterns).
"""

from __future__ import annotations

from typing import Annotated, ForwardRef, Literal, get_args

from pydantic import BaseModel, Field

from pydantic_migrator import ModelManager, ModelVersion
from pydantic_migrator.versioned_model import VersionedModel

# ============================================================================
# Minimal models for VersionedModel internal tests
# ============================================================================


class TypedUserV1(BaseModel):
    name: str


class TypedUserV2(BaseModel):
    name: str
    email: str


TypedUserModel = TypedUserV1 | TypedUserV2


class TypedDiscUserV1(BaseModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    name: str


class TypedDiscUserV2(BaseModel):
    schema_version: Literal["2.0.0"] = "2.0.0"
    name: str
    email: str


TypedDiscUserModel = Annotated[
    TypedDiscUserV1 | TypedDiscUserV2,
    Field(discriminator="schema_version"),
]


class FakeManager:
    pass


def test_versioned_model_load() -> None:
    vm = VersionedModel(FakeManager(), "User", "2.0.0", TypedUserV2)

    user = vm.load({"name": "Alice", "email": "a@b.com"})

    assert isinstance(user, TypedUserV2)
    assert user.name == "Alice"
    assert vm.cls is TypedUserV2
    assert vm._versioned_type is TypedUserV2
    assert vm._container_type is None


def test_versioned_model_runtime_types() -> None:
    manager = ModelManager[TypedUserModel]()

    @manager.model[TypedUserV2]("User", "2.0.0")
    class _UserV2(TypedUserV2):
        pass

    vm = manager.get("User", "2.0.0")

    assert vm._container_type == TypedUserModel
    assert vm._versioned_type is _UserV2
    assert vm.cls is _UserV2


def test_manager_orig_class_from_generic() -> None:
    manager = ModelManager[TypedUserModel]()

    orig = getattr(manager, "__orig_class__", None)

    assert orig is not None
    assert get_args(orig)[0] == TypedUserModel


def test_container_type_with_generic() -> None:
    manager = ModelManager[TypedUserModel]()
    assert manager.container_type == TypedUserModel


def test_forward_ref_manager_annotation() -> None:
    mgr: ModelManager["TypedUserModel"] = ModelManager["TypedUserModel"]()  # noqa: UP037

    container_type = mgr.container_type
    assert isinstance(container_type, ForwardRef)
    assert container_type.__forward_arg__ == "TypedUserModel"


def test_manager_container_type_without_generic() -> None:
    manager = ModelManager()
    assert manager.container_type is None


def test_manager_version_map_starts_empty() -> None:
    manager = ModelManager[TypedUserModel]()
    assert manager._version_map == {}


def test_register_subscript() -> None:
    manager = ModelManager[TypedUserModel]()

    @manager.model[TypedUserV2]("User", "2.0.0")
    class _UserV2(TypedUserV2):
        pass

    vm = manager._version_map[("User", ModelVersion.parse("2.0.0"))]

    assert vm.cls is _UserV2
    assert manager.list_models() == ["User"]
    user = vm.load({"name": "Alice", "email": "a@b.com"})
    assert user.name == "Alice"


def test_model_decorator_populates_version_map() -> None:
    manager = ModelManager[TypedUserModel]()

    @manager.model("User", "1.0.0")
    class _UserV1(TypedUserV1):
        pass

    vm = manager.get("User", "1.0.0")

    assert vm.cls is _UserV1
    assert isinstance(vm, VersionedModel)


def test_get_returns_versioned_model() -> None:
    manager = ModelManager[TypedUserModel]()

    @manager.model[TypedUserV2]("User", "2.0.0")
    class _UserV2(TypedUserV2):
        pass

    vm = manager.get("User", "2.0.0")

    assert vm.cls is _UserV2
    assert vm.load({"name": "Bob", "email": "bob@x.com"}).email == "bob@x.com"


def test_get_latest_returns_versioned_model_inline() -> None:
    manager = ModelManager()

    @manager.model("User", "1.0.0")
    class _UserV1(TypedUserV1):
        pass

    @manager.model("User", "2.0.0")
    class _UserV2(TypedUserV2):
        pass

    vm = manager.get_latest("User")
    assert isinstance(vm, VersionedModel)
    assert "email" in vm.cls.model_fields


def test_backward_compat_get_returns_versioned_model_inline() -> None:
    manager = ModelManager()

    @manager.model("User", "1.0.0")
    class _UserV1(TypedUserV1):
        pass

    vm = manager.get("User", "1.0.0")

    assert isinstance(vm, VersionedModel)
    assert vm.cls is _UserV1
    assert manager.container_type is None


def test_discriminated_union_load() -> None:
    manager = ModelManager[TypedDiscUserModel]()

    @manager.model[TypedDiscUserV1]("User", "1.0.0")
    class _UserV1(TypedDiscUserV1):
        pass

    @manager.model[TypedDiscUserV2]("User", "2.0.0")
    class _UserV2(TypedDiscUserV2):
        pass

    v2 = manager.get("User", "2.0.0").load(
        {"schema_version": "2.0.0", "name": "Alice", "email": "a@b.com"}
    )
    v1 = manager.get("User", "1.0.0").load({"schema_version": "1.0.0", "name": "Bob"})

    assert v2.email == "a@b.com"
    assert v1.name == "Bob"
