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
from typing import Any, ClassVar, Generic, Literal, cast, overload

from pydantic import BaseModel

from .diff import PydanticDiff
from .engine import Engine
from .exceptions import ModelNotFoundError, RegistryError
from .executor import SequentialExecutor
from .graph import GraphBuilder
from .models import MigrationSettings
from .policy import (
    earliest_target_resolver,
    fixed_target_resolver,
    latest_target_resolver,
    multi_target_resolver,
    skip_target_resolver,
)
from .registry import Registry
from .strategy import DefaultEntryMigration, EntryMigration
from .types import (
    Attachable,
    DirectionViolationStrategy,
    Executor,
    MigrationDirectionStrategy,
    MigrationFunc,
    ModelAdapter,
    ModelBase,
    ModelData,
    ModelKind,
    ModelVersionKey,
    TargetPolicy,
    TargetResolver,
    TargetSpec,
    TContainer,
    Versionable,
    VersionMissingStrategy,
    VersionValue,
    VersionValue_co,
    VModel,
    VModel_co,
    Walker,
)
from .versioning import SentinelNode, VersionNode
from .walker import CompoundKeyWalker


def _model_resolver(
    registry: Registry[VersionValue, ModelBase],
    model_cls: type[BaseModel],
    *,
    version_property: str,
) -> TargetResolver:
    try:
        target = registry.get_model_by_class(model_cls)
    except ModelNotFoundError as exc:
        raise RegistryError(
            registry.name,
            f"Target model {model_cls.__name__} is not registered",
        ) from exc

    def resolve(
        current: Versionable[VersionValue_co, VModel_co],
    ) -> Versionable[VersionValue_co, VModel_co] | None:
        if current.kind != target.kind:
            raise RegistryError(
                registry.name,
                f"Target model {model_cls.__name__} belongs to kind "
                f"{target.kind!r}, but entry kind is {current.kind!r}",
            )
        return target

    return resolve


def _string_resolver(
    registry: Registry[VersionValue, ModelBase],
    value: str,
    adapter: ModelAdapter,
) -> TargetResolver:
    """Resolve an explicit version string to a registered versionable.

    The string is parsed eagerly with the adapter's version parser, which
    understands both semver and ISO date values.  Resolving against an
    unregistered version raises ``ModelNotFoundError``; an unparsable value
    fails fast here.
    """
    try:
        parsed = adapter.of(value)
    except ValueError:
        raise RegistryError(
            registry.name,
            f"Could not resolve string target {value!r} to a version",
        ) from None

    def resolve(
        current: Versionable[VersionValue_co, VModel_co],
    ) -> Versionable[VersionValue_co, VModel_co] | None:
        sentinel: Versionable[VersionValue_co, VModel_co] = cast(
            Versionable[VersionValue_co, VModel_co],
            SentinelNode(current.kind, parsed),
        )
        return registry.get_model(sentinel)

    return resolve


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
            cast(VersionValue, engine.adapter.of(source_version)),
        )
        target_key: ModelVersionKey = (
            kind,
            cast(VersionValue, engine.adapter.of(target_version)),
        )
    else:
        source_cls, target_cls = cast(tuple[type[VModel], type[VModel]], key)
        source_key, target_key = source_cls, target_cls
    return engine.get_model(source_key), engine.get_model(target_key)


class ModelProxy(Generic[VersionValue, VModel]):
    """Binds a model class to its version/kind for later registration.

    Resolves the exact model type so callers can hold a typed versionable.
    """

    __slots__ = ("_kind", "_model", "_value")

    def __init__(
        self,
        model: type[VModel],
        value: VersionValue,
        kind: ModelKind,
    ) -> None:
        self._model = model
        self._value = value
        self._kind = kind

    def __call__(self) -> Versionable[VersionValue, VModel]:
        return VersionNode[VersionValue, VModel](
            _model=self._model,
            _value=self._value,
            _kind=self._kind,
        )


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
    ) -> Callable[
        ...,
        type[VModel]
        | ModelProxy[VersionValue, VModel]
        | Callable[[type[VModel]], type[VModel]],
    ]:
        owner = obj
        if owner is None:
            raise TypeError("ModelManager descriptor used without an owner class")

        def decorator(
            *args: Any,
        ) -> (
            type[VModel]
            | ModelProxy[VersionValue, VModel]
            | Callable[[type[VModel]], type[VModel]]
        ):
            def wrapper(model_cls: type[VModel]) -> type[VModel]:
                engine = owner._engine
                proxy = ModelProxy[VersionValue, VModel](
                    model_cls,
                    cast(
                        VersionValue,
                        engine.adapter.of(engine.adapter.version(model_cls)),
                    ),
                    engine.adapter.kind(model_cls),
                )
                engine.store_model(proxy())
                return model_cls

            if (
                len(args) == 1
                and isinstance(args[0], type)
                and issubclass(args[0], BaseModel)
            ):
                return wrapper(args[0])

            if len(args) != 0:
                raise TypeError("manager.model expects no args or a model class")

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
    _engine: ClassVar[Engine[VersionValue]]  # ty: ignore[invalid-type-form]

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
    def registry(self) -> Registry[VersionValue, ModelBase]:
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
            registry = Registry[VersionValue, ModelBase]()
            active_walker = CompoundKeyWalker(
                registry, settings=settings, adapter=adapter
            )
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

    def compile_target_spec(self, spec: TargetSpec) -> TargetResolver:
        """Compile a single declarative target spec into a resolver closure.

        Spec forms:
            * ``None`` or ``"skip"`` → skip every entry.
            * ``"latest"`` / ``"earliest"`` → registry extreme for the kind.
            * a version string (e.g. ``"1.5.0"``) → the registered version.
            * a model class → the registered version of that model.
            * a :class:`Versionable` → use as-is.
        """
        registry = self.engine.registry
        adapter = self.engine.adapter
        version_property = self.engine.settings.version_property

        if spec is None:
            return skip_target_resolver(registry)

        # Resolve string values first so we never compare a VersionNode/
        # SentinelNode to a string (their ``__eq__`` intentionally raises for
        # mixed types).
        if isinstance(spec, str):
            named_resolvers: dict[
                str,
                Callable[[Registry[VersionValue, ModelBase]], TargetResolver],
            ] = {
                "skip": skip_target_resolver,
                "latest": latest_target_resolver,
                "earliest": earliest_target_resolver,
            }
            if spec in named_resolvers:
                return named_resolvers[spec](registry)
            return _string_resolver(registry, spec, adapter)

        if isinstance(spec, type) and issubclass(spec, ModelBase):
            return _model_resolver(registry, spec, version_property=version_property)

        # Treat any remaining value as an explicit versionable target.  This
        # avoids an ``isinstance(spec, Versionable)`` protocol check that would
        # trigger the strict ``__eq__`` semantics of :class:`VersionNode` /
        # :class:`SentinelNode`.
        return fixed_target_resolver(registry, cast(Versionable, spec))

    def _resolve_kind_mapping(
        self,
        mapping: dict[ModelKind | Literal["*"], TargetSpec],
    ) -> TargetResolver:
        """Compile a per-kind target mapping into a single resolver.

        The special key ``"*"`` is used as the fallback for kinds not
        explicitly listed.
        """
        resolvers: dict[ModelKind | Literal["*"], TargetResolver] = {
            kind: self.compile_target_spec(spec) for kind, spec in mapping.items()
        }
        return multi_target_resolver(resolvers)

    def _resolve_target_policy(
        self,
        target: TargetPolicy,
    ) -> TargetResolver:
        """Normalize a high-level target policy into a single resolver.

        Strings, model classes, versionables, ``None``, dict policies and
        existing callables are all compiled into one ``TargetResolver``.
        """
        if isinstance(target, type) and issubclass(target, ModelBase):
            return self.compile_target_spec(target)

        if isinstance(target, dict):
            return self._resolve_kind_mapping(
                cast(dict[ModelKind | Literal["*"], TargetSpec], target)
            )

        if isinstance(target, str):
            return self.compile_target_spec(target)

        if callable(target):
            return cast(TargetResolver, target)

        return self.compile_target_spec(cast(TargetSpec, target))

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
        target: TargetPolicy = "latest",
        *,
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
        target: TargetPolicy = "latest",
        *,
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
        target: TargetPolicy = "latest",
        *,
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

        *target* accepts a declarative spec (string, model class, versionable,
        ``None``/``"skip"``), a per-kind mapping, or an existing callable
        resolver. Defaults to ``"latest"``.

        When *container* is given, the migrated payload is validated against it
        and a typed container instance is returned instead of a dict.
        """
        resolved_target = self._resolve_target_policy(target)
        migrated = self.engine.migrate(
            data,
            target=resolved_target,
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

    def list_versions(
        self, kind: ModelKind | None = None
    ) -> list[Versionable[VersionValue, VModel]]:
        """Return registered versions, optionally filtered by *kind*."""
        if kind is None:
            return self.registry.versions
        return self.registry.kind_versions(kind)

    def get(self, kind: ModelKind, version: str) -> Versionable[VersionValue, VModel]:
        """Return the registered versionable for ``kind``@``version``."""
        return self.get_model(
            (kind, cast(VersionValue, self.engine.adapter.of(version)))
        )

    def get_latest(self, kind: ModelKind) -> Versionable[VersionValue, VModel]:
        """Return the highest registered version for *kind*."""
        return self.engine.model_latest(kind)

    def validate(self, data: ModelData, kind: ModelKind, version: str) -> None:
        """Validate *data* against ``kind``@``version``.

        Raises :class:`ValidationError` when the payload is invalid.
        """
        versionable = self.get(kind, version)
        self.engine.adapter.validate(data, versionable.model)

    def diff(
        self,
        kind: ModelKind,
        from_version: str,
        to_version: str,
    ) -> PydanticDiff[VersionValue, VModel, VModel]:
        """Build a diff between two versions of *kind*."""
        source = self.get_model(
            (kind, cast(VersionValue, self.engine.adapter.of(from_version)))
        )
        target = self.get_model(
            (kind, cast(VersionValue, self.engine.adapter.of(to_version)))
        )
        return PydanticDiff.from_pair(source=source, target=target)
