from __future__ import annotations

from typing import Any, ClassVar

from pyverge.core.types import VersionValue
from pyverge.discovery.reflection import (
    CompositeDiffDiscovery,
    Reflection,
    Reflector,
)
from pyverge.engine import Engine
from pyverge.migrations.backend import MigrationMaterializer
from pyverge.migrations.identity import (
    DefaultMigrationIdentityResolver,
)
from pyverge.migrations.json_patch.backend import JsonPatchMigrationBackend
from pyverge.registry import Registry
from pyverge.schemas.backend import ModelMaterializer
from pyverge.schemas.types import (
    ModelAdapter,
)
from pyverge.versioning import default_content_hasher

from .descriptors import ManagerMeta
from .mixins import (
    EngineLifecycleMixin,
    LookupMixin,
    MigrationStoreMixin,
    ModelStoreMixin,
    ReflectionMixin,
    RuntimeMixin,
    TargetResolutionMixin,
)
from .types import ManagerConfig


class Manager(
    EngineLifecycleMixin[VersionValue],
    TargetResolutionMixin[VersionValue],
    ModelStoreMixin[VersionValue],
    MigrationStoreMixin[VersionValue],
    LookupMixin[VersionValue],
    ReflectionMixin[VersionValue],
    RuntimeMixin[VersionValue],
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
        return self.engine.adapter

    @property
    def registry(self) -> Registry[VersionValue]:
        return self.engine.registry

    @classmethod
    def configure(
        cls,
        adapter: ModelAdapter,
        *,
        config: ManagerConfig[VersionValue] | None = None,
        **options: Any,
    ) -> type[Manager[VersionValue]]:
        if config is not None and options:
            raise TypeError("configure accepts either config or keyword options")
        settings = config or ManagerConfig(**options)
        if settings.walker is None:
            registry = Registry[VersionValue](
                hasher=settings.hasher or default_content_hasher()
            )
        else:
            registry = settings.walker.registry
        reflector = Reflector[VersionValue](
            adapter,
            settings.diff_provider or Reflection(adapter, CompositeDiffDiscovery()),
            model_materializer=settings.model_materializer
            or ModelMaterializer(adapter),
            migration_materializer=(
                settings.migration_materializer
                or MigrationMaterializer(JsonPatchMigrationBackend())
            ),
            on_missing=settings.on_missing,
        )
        engine = settings.engine or Engine[VersionValue](
            registry=registry,
            adapter=adapter,
            identity_resolver=(
                settings.identity_resolver or DefaultMigrationIdentityResolver()
            ),
            reflector=reflector,
        )
        cls._default_engine = engine
        cls._default_adapter = adapter
        return cls
