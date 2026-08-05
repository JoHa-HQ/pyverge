"""Public facade for building and running migrations.

``ModelManager`` is a class factory.  ``ModelManager.scoped(...)`` returns a
configured subclass carrying an initialized ``Registry`` and ``Engine`` at
class level, so models, migrations and hooks can be registered declaratively
with the ``model`` / ``migration`` / ``hook`` decorators — no instance required.

The scoped class is instantiated for the runtime facade.  Instances share the
class-level ``Engine`` and ``Registry``.

Example:
    .. code-block:: python

        UserManager = ModelManager[semver.Version].scoped(
            PydanticModelAdapter(),
            settings=MigrationSettings(),
        )

        @UserManager.model()
        class UserV1(BaseModel):
            kind: Literal["User"] = "User"
            version: Literal["1.0.0"] = "1.0.0"

        @UserManager.migration("User", "1.0.0", "2.0.0", backward_compatible=True)
        def add_age(data): ...

        manager = UserManager()
        result = manager.migrate(payload)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar, Generic, cast, overload

from pydantic import BaseModel

from .engine import Engine
from .executor import SequentialExecutor
from .graph import GraphBuilder
from .models import MigrationSettings
from .registry import Registry
from .strategy import DefaultEntryMigration, EntryMigration
from .types import (
    Attachable,
    DirectionViolationStrategy,
    Executor,
    MigrationDirectionStrategy,
    MigrationFunc,
    ModelAdapter,
    ModelData,
    ModelKind,
    ModelVersionKey,
    TargetPolicy,
    TargetResolver,
    TContainer,
    Versionable,
    VersionMissingStrategy,
    VersionValue,
    VModel,
    Walker,
)
from .versioning import VersionNode
from .walker import CompoundKeyWalker


def _resolve_migration_key(
    engine: Engine[VersionValue],
    key: tuple[type[VModel], type[VModel]] | tuple[str, str, str],
) -> tuple[Versionable[VersionValue, VModel], Versionable[VersionValue, VModel]]:
    """Resolve a migration key to a ``Versionable`` pair via the engine.

    Accepts a model class pair ``(SrcModel, TgtModel)`` or an explicit
    ``(kind, source_version, target_version)`` string triple.
    """
    if isinstance(key, tuple) and isinstance(key[0], str):
        kind, source_version, target_version = cast(tuple[str, str, str], key)
        source_key: ModelVersionKey = (
            kind,
            cast(VersionValue, VersionNode.of(source_version)),
        )
        target_key: ModelVersionKey = (
            kind,
            cast(VersionValue, VersionNode.of(target_version)),
        )
    else:
        source_cls, target_cls = cast(tuple[type[VModel], type[VModel]], key)
        source_key, target_key = source_cls, target_cls
    return engine.get_model(source_key), engine.get_model(target_key)


class _ModelDescriptor:
    """Metaclass descriptor implementing ``@manager.model(...)``.

    Class-only — accessing ``model`` on an instance raises ``AttributeError``.

    Accepted forms:

        @manager.model()
        manager.model(UserV1)
    """

    def __get__(
        self,
        obj: type[ModelManager[VersionValue]],
        objtype: type | None = None,
    ) -> Callable[..., type[VModel] | Callable[[type[VModel]], type[VModel]]]:
        owner = obj
        if owner is None:
            raise TypeError("ModelManager descriptor used without an owner class")

        def decorator(
            *args: Any,
        ) -> type[VModel] | Callable[[type[VModel]], type[VModel]]:
            if (
                len(args) == 1
                and isinstance(args[0], type)
                and issubclass(args[0], BaseModel)
            ):
                model_cls = args[0]
                engine = owner._engine
                engine.store_model(engine.adapter.versionable(model_cls))
                return model_cls

            if len(args) != 0:
                raise TypeError("manager.model expects no args or a model class")

            def wrapper(model_cls: type[VModel]) -> type[VModel]:
                engine = owner._engine
                engine.store_model(engine.adapter.versionable(model_cls))
                return model_cls

            return wrapper

        return decorator


class _MigrationDescriptor:
    """Metaclass descriptor implementing ``@manager.migration(...)``.

    Class-only — accessing ``migration`` on an instance raises ``AttributeError``.

    Accepted forms:

        @manager.migration("User", "1.0.0", "2.0.0", backward_compatible=True)
        @manager.migration(UserV1, UserV2)
    """

    def __get__(
        self,
        obj: type[ModelManager[VersionValue]],
        objtype: type | None = None,
    ) -> Callable[..., Callable[[MigrationFunc], MigrationFunc]]:
        owner = obj
        if owner is None:
            raise TypeError("ModelManager descriptor used without an owner class")

        def decorator(
            *args: Any,
            backward_compatible: bool = False,
        ) -> Callable[[MigrationFunc], MigrationFunc]:
            def wrapper(func: MigrationFunc) -> MigrationFunc:
                engine = owner._engine
                engine.store_migration(
                    _resolve_migration_key(engine, args),
                    func,
                    backward_compatible=backward_compatible,
                )
                return func

            return wrapper

        return decorator


class _HookDescriptor:
    """Metaclass descriptor implementing ``@manager.hook(...)``.

    Class-only — accessing ``hook`` on an instance raises ``AttributeError``.

    Accepted form:

        @manager.hook("User", "1.0.0", "2.0.0", MyHook())
    """

    def __get__(
        self,
        obj: type[ModelManager[VersionValue]],
        objtype: type | None = None,
    ) -> Callable[..., Callable[[type[VModel]], type[VModel]]]:
        owner = obj
        if owner is None:
            raise TypeError("ModelManager descriptor used without an owner class")

        def decorator(
            kind: str,
            source_version: str,
            target_version: str,
            hook: Attachable,
        ) -> Callable[[type[VModel]], type[VModel]]:
            def wrapper(marker: type[VModel]) -> type[VModel]:
                engine = getattr(owner, "_engine", None)
                if engine is None:
                    raise TypeError(
                        "ModelManager requires a strategy. Use ModelManager.scoped(...)"
                    )
                engine.add_hook(
                    _resolve_migration_key(
                        engine, (kind, source_version, target_version)
                    ),
                    hook,
                )
                return marker

            return wrapper

        return decorator


class _ManagerMeta(type):
    """Metaclass exposing class-only registration decorators."""

    model = _ModelDescriptor()
    migration = _MigrationDescriptor()
    hook = _HookDescriptor()


class ModelManager(Generic[VersionValue], metaclass=_ManagerMeta):
    """Class factory scoping a migration ``Engine`` to a version strategy.

    Use :meth:`scoped` to build a configured class; register models, migrations
    and hooks with the ``model`` / ``migration`` / ``hook`` decorators at class
    level; then instantiate for the runtime facade.
    """

    _settings: ClassVar[MigrationSettings]
    _adapter: ClassVar[ModelAdapter]
    _engine: ClassVar[Engine[VersionValue]]  # type: ignore[misc]

    def __init__(self, engine: Engine[VersionValue] | None = None) -> None:
        """Initialize the runtime facade.

        Args:
            engine: Optional per-instance engine override.  When omitted, the
                instance wraps its own copy of the class registry.
        """
        if engine is None and not hasattr(type(self), "_engine"):
            raise ValueError("Missing the engine instance")
        self.engine = engine or type(self)._engine

    def __class_getitem__(
        cls, strategy: type[VersionValue]
    ) -> type[ModelManager[VersionValue]]:
        klass = type(cls.__name__, (cls,), {})
        klass.__name__ = f"ModelManager[{strategy.__name__}]"
        return klass

    @property
    def registry(self) -> Registry[VersionValue]:
        """Return the instance registry."""
        return self.engine.registry

    @classmethod
    def scoped(
        cls,
        adapter: ModelAdapter,
        *,
        settings: MigrationSettings | None = None,
        engine: Engine[VersionValue] | None = None,
        walker: (Walker | None) = None,
    ) -> type[ModelManager[VersionValue]]:
        """Build a ``ModelManager`` subclass bound to *strategy*.

        The returned class carries an initialized ``Registry`` and ``Engine``
        (either the provided *engine* or a default built from *strategy*,
        *adapter* and *settings*).

        Args:
            adapter: Model adapter used to read version/kind from models.
            settings: Migration configuration; defaults to ``MigrationSettings()``.
            engine: Optional pre-built engine.  The caller is responsible for
                aligning it with *strategy*, *adapter* and *settings*.
            walker: Optional preconfigured payload walker.  When a walker
                instance is given, its ``registry`` becomes the manager's
                registry.  Defaults to the containerless
                :class:`~pyverge.migration.CompoundKeyWalker`; supply a
                schema-driven walker (e.g.
                :class:`~pyverge.migration.PydanticWalker`) to enable
                container-guided discovery.
        """
        settings = settings or MigrationSettings()
        if walker is None:
            registry = Registry[VersionValue]()
            active_walker = CompoundKeyWalker(registry, settings=settings)
        else:
            active_walker = walker
            registry = walker.registry
        engine = engine or Engine[VersionValue](
            registry=registry,
            settings=settings,
            default_executor=SequentialExecutor(),
            graph_builder=GraphBuilder(
                registry,
                settings,
                active_walker,
            ),
            adapter=adapter,
            entry_migration=DefaultEntryMigration(),
        )
        namespace: dict[str, Any] = {
            "_settings": settings,
            "_adapter": adapter,
            "_engine": engine,
            "__module__": cls.__module__,
            "__qualname__": cls.__name__,
        }

        scoped_manager = type(cls.__name__, (cls,), namespace)
        return scoped_manager

    def store_model(
        self,
        key: type[VModel],
    ) -> Versionable[VersionValue, VModel]:
        """Register a model version through the instance engine.

        Accepts a raw model class (converted to a ``Versionable`` by the
        adapter) or a pre-built ``VersionNode``.
        """
        return self.engine.store_model(self.engine.adapter.versionable(key))

    def store_migration(
        self,
        key: tuple[type[VModel], type[VModel]] | tuple[str, str, str],
        func: MigrationFunc,
        *,
        backward_compatible: bool = False,
    ) -> MigrationFunc:
        """Register a migration through the instance engine.

        Accepts a model class pair ``(SrcModel, TgtModel)`` or an explicit
        ``(kind, source_version, target_version)`` string triple.
        """
        return self.engine.store_migration(
            _resolve_migration_key(self.engine, key),
            func,
            backward_compatible=backward_compatible,
        )

    def add_hook(
        self,
        key: tuple[type[VModel], type[VModel]] | tuple[str, str, str],
        hook: Attachable,
    ) -> None:
        """Register a hook through the instance engine.

        Accepts a model class pair ``(SrcModel, TgtModel)`` or an explicit
        ``(kind, source_version, target_version)`` string triple.
        """
        self.engine.add_hook(_resolve_migration_key(self.engine, key), hook)

    def get_model(
        self, key: tuple[ModelKind, VersionValue] | type[VModel]
    ) -> Versionable[VersionValue, VModel]:
        """Return a registered model version."""
        return self.engine.get_model(key)

    def get_migration(
        self,
        key: (
            tuple[ModelVersionKey, ModelVersionKey] | tuple[type[VModel], type[VModel]]
        ),
    ) -> MigrationFunc:
        """Return a registered migration function."""
        return self.engine.get_migration(key)

    @overload
    def migrate(
        self,
        data: ModelData,
        target: TargetPolicy | None = None,
        *,
        target_resolver: TargetResolver | None = None,
        container: type[TContainer],
        version_property: str | None = None,
        depth_limit: int | None = None,
        direction: MigrationDirectionStrategy | None = None,
        on_direction_violation: DirectionViolationStrategy | None = None,
        on_version_not_found: VersionMissingStrategy | None = None,
        executor: Executor | None = None,
        entry_migration: EntryMigration[VersionValue] | None = None,
    ) -> TContainer: ...

    @overload
    def migrate(
        self,
        data: ModelData,
        target: TargetPolicy | None = None,
        *,
        target_resolver: TargetResolver | None = None,
        container: None = None,
        version_property: str | None = None,
        depth_limit: int | None = None,
        direction: MigrationDirectionStrategy | None = None,
        on_direction_violation: DirectionViolationStrategy | None = None,
        on_version_not_found: VersionMissingStrategy | None = None,
        executor: Executor | None = None,
        entry_migration: EntryMigration[VersionValue] | None = None,
    ) -> ModelData: ...

    def migrate(  # noqa: PLR0913
        self,
        data: ModelData,
        target: TargetPolicy | None = None,
        *,
        target_resolver: TargetResolver | None = None,
        container: type[TContainer] | None = None,
        version_property: str | None = None,
        depth_limit: int | None = None,
        direction: MigrationDirectionStrategy | None = None,
        on_direction_violation: DirectionViolationStrategy | None = None,
        on_version_not_found: VersionMissingStrategy | None = None,
        executor: Executor | None = None,
        entry_migration: EntryMigration[VersionValue] | None = None,
    ) -> ModelData | TContainer:
        """Migrate *data* to the configured target policy.

        When *container* is given, the migrated payload is validated against it
        and a typed container instance is returned instead of a dict.
        """
        migrated = self.engine.migrate(
            data,
            target=target,
            target_resolver=target_resolver,
            container=container,
            version_property=version_property,
            depth_limit=depth_limit,
            direction=direction,
            on_direction_violation=on_direction_violation,
            on_version_not_found=on_version_not_found,
            executor=executor,
            entry_migration=entry_migration,
        )
        if container is None:
            return migrated
        return container.model_validate(migrated)

    def info(self) -> dict[str, str | int | dict[str, str | int]]:
        """Return manager metadata."""
        engine = self.engine
        return {
            "adapter": type(engine.adapter).__name__,
            "registry": {
                "name": engine.registry.name,
                "models": len(engine.registry.versions),
                "migrations": len(engine.registry.kinds),
            },
        }
