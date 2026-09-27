"""Public facade for building and running migrations.

``Manager`` is a class factory.  ``Manager.configure(...)`` returns a
configured subclass carrying an initialized ``Registry`` and ``Engine`` at
class level, so models, migrations and hooks can be registered declaratively
with the ``model`` / ``migration`` / ``hook`` decorators — no instance required.

The configured class is instantiated for the runtime facade.  Instances share
the class-level ``Engine`` and ``Registry``.

Example:
    .. code-block:: python

        UserManager = Manager[semver.Version].configure(
            settings=MigrationSettings(),
            adapter=PydanticModelAdapter(),
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

from typing import ClassVar

from pyverge.core.settings import MigrationSettings
from pyverge.migration.engine import Engine
from pyverge.migration.executor import SequentialExecutor
from pyverge.migration.graph import GraphBuilder
from pyverge.migration.registry import Registry
from pyverge.migration.strategy import DefaultMigrationEntry, EntryMigration
from pyverge.migration.walker import CompoundKeyWalker
from pyverge.types import (
    Executor,
    ModelAdapter,
    ModelBase,
    VersionValue,
    Walker,
)

from .descriptors import ManagerMeta
from .mixins import (
    EngineLifecycleMixin,
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
    MigrateMixin[VersionValue],
    metaclass=ManagerMeta,
):
    """Class factory scoping a migration ``Engine`` to a version strategy.

    Use :meth:`configure` to build a configured class; register models,
    migrations and hooks with the ``model`` / ``migration`` / ``hook``
    decorators at class level; then instantiate for the runtime facade.
    """

    _strategy: ClassVar[type[VersionValue]]  # type: ignore[invalid-var-type]
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
    def registry(self) -> Registry[VersionValue, ModelBase]:
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
        entry_migration: EntryMigration[VersionValue] | None = None,
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
