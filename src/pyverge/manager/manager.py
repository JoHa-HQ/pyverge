from __future__ import annotations

from typing import ClassVar

from pyverge.core.types import VersionValue
from pyverge.discovery.reflection import (
    CompositeDiffDiscovery,
    DiffProvider,
    Reflection,
    Reflector,
)
from pyverge.execution.types import EntryExtractor
from pyverge.migration.engine import Engine
from pyverge.migrations.backend import MigrationMaterializer
from pyverge.migrations.identity import (
    DefaultMigrationIdentityResolver,
    MigrationIdentityResolver,
)
from pyverge.migrations.json_patch.backend import JsonPatchMigrationBackend
from pyverge.registry import Registry
from pyverge.schemas.backend import ModelMaterializer
from pyverge.schemas.types import (
    ModelAdapter,
)
from pyverge.versioning import ContentHasher, DiffMaterializer, default_content_hasher

from .descriptors import ManagerMeta
from .mixins import (
    EngineLifecycleMixin,
    LookupMixin,
    MigrateMixin,
    MigrationStoreMixin,
    ModelStoreMixin,
    ReflectionMixin,
    TargetResolutionMixin,
)


class Manager(
    EngineLifecycleMixin[VersionValue],
    TargetResolutionMixin[VersionValue],
    ModelStoreMixin[VersionValue],
    MigrationStoreMixin[VersionValue],
    LookupMixin[VersionValue],
    MigrateMixin[VersionValue],
    ReflectionMixin[VersionValue],
    metaclass=ManagerMeta,
):
    """Class factory scoping a migration ``Engine`` to a version strategy.

    Use :meth:`configure` to build a configured class; register models,
    migrations and hooks with the ``model`` / ``migration`` / ``hook``
    decorators at class level; then instantiate for the runtime facade.
    """

    _strategy: ClassVar[type[VersionValue]]  # ty: ignore[invalid-type-form]
    _default_adapter: ClassVar[ModelAdapter]
    _default_engine: ClassVar[Engine[VersionValue]]  # ty: ignore[invalid-type-form]
    _reflection_locked: ClassVar[bool] = False

    def __class_getitem__(
        cls, strategy: type[VersionValue]
    ) -> type[Manager[VersionValue]]:
        klass = type(
            cls.__name__,
            (cls,),
            {
                "_strategy": strategy,
                "_default_adapter": None,
                "_default_engine": None,
                "_reflection_locked": False,
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
    def registry(self) -> Registry[VersionValue]:
        """Return the instance registry."""
        return self.engine.registry

    @classmethod
    def configure(  # noqa: PLR0913
        cls,
        adapter: ModelAdapter,
        *,
        engine: Engine[VersionValue] | None = None,
        walker: EntryExtractor | None = None,
        hasher: ContentHasher | None = None,
        identity_resolver: MigrationIdentityResolver | None = None,
        model_materializer: DiffMaterializer[object] | None = None,
        migration_materializer: DiffMaterializer[object] | None = None,
        diff_provider: DiffProvider[VersionValue] | None = None,
        on_missing: str = "raise",
    ) -> type[Manager[VersionValue]]:
        """Build a configured ``Manager`` subclass.

        Args:
            adapter: Model adapter used to read version and kind from models.
            engine: Optional pre-built engine. The caller is responsible for
                aligning it with the strategy and adapter.
            walker: Optional preconfigured payload walker.  When a walker
                instance is given, its ``registry`` becomes the manager's
                registry.  Defaults to the containerless
                :class:`~pyverge.execution.CompositeExtractor`; container-guided
                discovery is enabled by supplying a container at call time.
            entry_migration: Optional per-entry migration defaults.  Defaults
                to :class:`~pyverge.migration.DefaultEntryPlanner`.
        """
        if walker is None:
            registry = Registry[VersionValue](hasher=hasher or default_content_hasher())
        else:
            registry = walker.registry
        reflector = Reflector[VersionValue](
            adapter,
            diff_provider or Reflection(adapter, CompositeDiffDiscovery()),
            model_materializer=model_materializer or ModelMaterializer(adapter),
            migration_materializer=(
                migration_materializer
                or MigrationMaterializer(JsonPatchMigrationBackend())
            ),
            on_missing=on_missing,
        )
        engine = engine or Engine[VersionValue](
            registry=registry,
            adapter=adapter,
            identity_resolver=identity_resolver or DefaultMigrationIdentityResolver(),
            reflector=reflector,
        )
        cls._default_engine = engine
        cls._default_adapter = adapter
        return cls
