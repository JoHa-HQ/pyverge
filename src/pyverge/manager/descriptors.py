from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, overload

from pyverge.core.types import (
    Attachable,
    ManagerMigrationKey,
    MigrationFunc,
    MigrationKeyInput,
    ModelPair,
    VersionValue,
)
from pyverge.manager.types import (
    ManagerClassState,
)
from pyverge.providers import JsonPatchMigration
from pyverge.providers.types import (
    ModelHandle,
)

if TYPE_CHECKING:
    from pyverge.manager.manager import Manager


class MigrationDecorator(Protocol):
    @overload
    def __call__(self, func: MigrationFunc) -> MigrationFunc: ...
    @overload
    def __call__(self, func: JsonPatchMigration) -> JsonPatchMigration: ...


class ModelDecorator(Protocol):
    @overload
    def __call__(self) -> Callable[[ModelHandle], ModelHandle]: ...
    @overload
    def __call__(self, model_cls: ModelHandle) -> ModelHandle: ...


class MigrationKeyDecorator:
    """Bind a migration key to an owner and register decorated bodies.

    Both plain migration callables and declarative
    :class:`JsonPatchMigration` specs are passed through verbatim; no
    normalization happens here.  The single unwrap of a spec to its executable
    ``.patch`` happens at manager storage time in
    ``MigrationStoreMixin._resolve_migration`` before the resolved callable
    reaches ``Engine.store_migration``.
    """

    def __init__(
        self,
        owner: type[ManagerClassState[VersionValue]],
        key: MigrationKeyInput,
        *,
        backward_compatible: bool = False,
    ) -> None:
        self._owner = owner
        self._key = key
        self._backward_compatible = backward_compatible

    @overload
    def __call__(self, func: MigrationFunc) -> MigrationFunc: ...
    @overload
    def __call__(self, func: JsonPatchMigration) -> JsonPatchMigration: ...
    def __call__(
        self, func: MigrationFunc | JsonPatchMigration
    ) -> MigrationFunc | JsonPatchMigration:
        self._owner.store_migration(
            self._key,
            func,
            backward_compatible=self._backward_compatible,
        )
        return func


class ModelStoreDecorator:
    """Bind model registration to an owner and return decorated classes.

    ``manager.model`` resolves to an instance of this decorator.  Calling it
    with no model returns the bound method itself, so a single object serves
    both ``@manager.model()`` and bare ``@manager.model``; calling it with a
    model registers that class and hands it straight back.
    """

    __slots__ = ("_owner",)

    def __init__(self, owner: type[ManagerClassState[VersionValue]]) -> None:
        self._owner = owner

    @overload
    def __call__(self) -> Callable[[ModelHandle], ModelHandle]: ...
    @overload
    def __call__(self, model_cls: ModelHandle) -> ModelHandle: ...
    def __call__(
        self, model_cls: ModelHandle | None = None
    ) -> ModelHandle | Callable[[ModelHandle], ModelHandle]:
        if model_cls is None:
            return self.__call__
        if not isinstance(model_cls, type):
            raise TypeError("manager.model expects no args or a model class")
        self._owner.store_model(model_cls)
        return model_cls


class _ModelDescriptor:
    """Metaclass descriptor implementing ``@manager.model(...)``.

    Class-only — accessing ``model`` on an instance raises ``AttributeError``.

    Accepted forms:

        @manager.model
        manager.model(UserV1)
    """

    def __get__(
        self,
        obj: type[Manager[VersionValue]],
        objtype: type | None = None,
    ) -> ModelDecorator:
        owner: type[ManagerClassState[VersionValue]] = obj
        if owner is None:
            raise TypeError("Manager descriptor used without an owner class")
        return ModelStoreDecorator(owner)


class _MigrationDescriptor:
    """Metaclass descriptor implementing ``@manager.migration(...)``.

    Class-only — accessing ``migration`` on an instance raises ``AttributeError``.

    Accepted forms:

        @manager.migration(ManagerMigrationKey("User", "1.0.0", "2.0.0"))
        @manager.migration(ModelPair(UserV1, UserV2))
        @manager.migration(UserV1, UserV2)
        @manager.migration("User", "1.0.0", "2.0.0", backward_compatible=True)
    """

    @staticmethod
    def _migration_key(args: tuple[Any, ...]) -> MigrationKeyInput:
        if len(args) == 1:
            (key,) = args
            if isinstance(key, (ModelPair, ManagerMigrationKey)):
                return key
        elif len(args) == 2:  # noqa: PLR2004
            return ModelPair(*args)
        elif len(args) == 3:  # noqa: PLR2004
            return ManagerMigrationKey(*args)
        raise TypeError(
            "migration expects a pre-built ManagerMigrationKey or ModelPair, "
            "(source_model, target_model), or "
            "(kind, source_version, target_version)"
        )

    def __get__(
        self,
        obj: type[Manager[VersionValue]],
        objtype: type | None = None,
    ) -> Callable[..., MigrationKeyDecorator]:
        owner: type[ManagerClassState[VersionValue]] = obj
        if owner is None:
            raise TypeError("Manager descriptor used without an owner class")

        def decorator(
            *args: Any,
            backward_compatible: bool = False,
        ) -> MigrationKeyDecorator:
            key = self._migration_key(args)
            return MigrationKeyDecorator(
                owner,
                key,
                backward_compatible=backward_compatible,
            )

        return decorator


class _HookDescriptor:
    """Metaclass descriptor implementing ``@manager.hook(...)``.

    Class-only — accessing ``hook`` on an instance raises ``AttributeError``.

    Accepted forms:

        @manager.hook("User", "1.0.0", "2.0.0", hook)
        @manager.hook(UserV1, UserV2, hook)
        @manager.hook(ManagerMigrationKey("User", "1.0.0", "2.0.0"), hook)
        @manager.hook(ModelPair(UserV1, UserV2), hook)
    """

    @staticmethod
    def _hook_key(args: tuple[Any, ...]) -> tuple[MigrationKeyInput, Attachable]:
        message = (
            "hook expects a hook plus a pre-built ManagerMigrationKey or "
            "ModelPair, (source_model, target_model), or "
            "(kind, source_version, target_version)"
        )
        if not args:
            raise TypeError(message)

        *key_args, hook = args
        key_args = tuple(key_args)
        if len(key_args) == 1:
            (key,) = key_args
            if isinstance(key, (ModelPair, ManagerMigrationKey)):
                return key, hook
        elif len(key_args) == 2:  # noqa: PLR2004
            return ModelPair(*key_args), hook
        elif len(key_args) == 3:  # noqa: PLR2004
            return ManagerMigrationKey(*key_args), hook
        raise TypeError(message)

    def __get__(
        self,
        obj: type[Manager[VersionValue]],
        objtype: type | None = None,
    ) -> Callable[..., Callable[[ModelHandle], ModelHandle]]:
        owner: type[ManagerClassState[VersionValue]] = obj
        if owner is None:
            raise TypeError("Manager descriptor used without an owner class")

        def decorator(*args: Any) -> Callable[[ModelHandle], ModelHandle]:
            key, hook = self._hook_key(args)

            def wrapper(marker: ModelHandle) -> ModelHandle:
                owner.add_hook(key, hook)
                return marker

            return wrapper

        return decorator


class ManagerMeta(type):
    """Metaclass exposing class-only registration decorators."""

    model = _ModelDescriptor()
    migration = _MigrationDescriptor()
    hook = _HookDescriptor()
