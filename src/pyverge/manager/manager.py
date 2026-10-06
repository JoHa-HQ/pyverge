from __future__ import annotations

from typing import ClassVar

from pyverge.core.settings import MigrationSettings
from pyverge.core.types import (
    VersionValue,
)
from pyverge.migration.engine import Engine
from pyverge.migration.executor import SequentialExecutor
from pyverge.migration.graph import GraphBuilder
from pyverge.migration.registry import Registry
from pyverge.migration.strategy import DefaultMigrationEntry
from pyverge.migration.types import (
    Executor,
    MigrationEntry,
    Walker,
)
from pyverge.migration.walker import CompoundKeyWalker
from pyverge.providers.types import (
    ModelAdapter,
)

from .descriptors import ManagerMeta
from .mixins import (
    EngineLifecycleMixin,
    LookupMixin,
    MigrateMixin,
    MigrationStoreMixin,
    ModelStoreMixin,
    TargetResolutionMixin,
)


class Manager(
    EngineLifecycleMixin[VersionValue],
    TargetResolutionMixin[VersionValue],
    ModelStoreMixin[VersionValue],
    MigrationStoreMixin[VersionValue],
    LookupMixin[VersionValue],
    MigrateMixin[VersionValue],
    metaclass=ManagerMeta,
):
    """Class factory scoping a migration ``Engine`` to a version strategy.

    Use :meth:`configure` to build a configured class; register models,
    migrations and hooks with the ``model`` / ``migration`` / ``hook``
    decorators at class level; then instantiate for the runtime facade.
    """

    _strategy: ClassVar[type[VersionValue]]  # ty: ignore[invalid-type-form]
    _default_settings: ClassVar[MigrationSettings]
    _default_adapter: ClassVar[ModelAdapter]
    _default_engine: ClassVar[Engine[VersionValue]]  # ty: ignore[invalid-type-form]

    def __class_getitem__(
        cls, strategy: type[VersionValue]
    ) -> type[Manager[VersionValue]]:
        klass = type(
            cls.__name__,
            (cls,),
            {
                "_strategy": strategy,
                "_default_settings": None,
                "_default_adapter": None,
                "_default_engine": None,
                "__module__": cls.__module__,
                "__qualname__": cls.__name__,
            },
        )
        klass.__name__ = f"Manager[{strategy.__name__}]"
        return klass

    @property
    def adapter(self) -> ModelAdapter:
        """Return the instance adapter."""
        return self.engine.adapter

    @property
    def settings(self) -> MigrationSettings | None:
        """Return the instance settings."""
        return self.engine.settings

    @property
    def registry(self) -> Registry[VersionValue]:
        """Return the instance registry."""
        return self.engine.registry

    @classmethod
    def configure(  # noqa: PLR0913
        cls,
        settings: MigrationSettings,
        adapter: ModelAdapter,
        *,
        engine: Engine[VersionValue] | None = None,
        walker: Walker | None = None,
        executor: Executor | None = None,
        entry_migration: MigrationEntry[VersionValue] | None = None,
    ) -> type[Manager[VersionValue]]:
        """Build a configured ``Manager`` subclass.

        Args:
            settings: Migration configuration.
            adapter: Model adapter used to read version/kind from models.
            engine: Optional pre-built engine.  The caller is responsible for
                aligning it with the strategy, *adapter* and *settings*.
            walker: Optional preconfigured payload walker.  When a walker
                instance is given, its ``registry`` becomes the manager's
                registry.  Defaults to the containerless
                :class:`~pyverge.migration.CompoundKeyWalker`; supply a
                schema-driven walker (e.g.
                :class:`~pyverge.migration.PydanticWalker`) to enable
                container-guided discovery.
            executor: Optional execution strategy.  Defaults to
                :class:`~pyverge.migration.SequentialExecutor`.
            entry_migration: Optional per-entry migration defaults.  Defaults
                to :class:`~pyverge.migration.DefaultMigrationEntry`.
        """
        if walker is None:
            registry = Registry[VersionValue]()
            active_walker = CompoundKeyWalker(
                registry, settings=settings, adapter=adapter
            )
        else:
            active_walker = walker
            registry = walker.registry
        engine = engine or Engine[VersionValue](
            registry=registry,
            settings=settings,
            default_executor=executor or SequentialExecutor(),
            graph_builder=GraphBuilder(
                registry,
                settings,
                active_walker,
            ),
            adapter=adapter,
            entry_migration=entry_migration or DefaultMigrationEntry(),
        )
        cls._default_engine = engine
        cls._default_adapter = adapter
        cls._default_settings = settings
        return cls
