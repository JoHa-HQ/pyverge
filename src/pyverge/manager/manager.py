from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from pyverge.core.engine import Engine
from pyverge.core.types import VersionValue
from pyverge.core.versioning import (
    ContentHasher,
    DiffMaterializer,
    default_content_hasher,
)
from pyverge.discovery.reflection import (
    CompositeDiffDiscovery,
    DiffProvider,
    Reflection,
    Reflector,
)
from pyverge.migrations.backend import MigrationMaterializer
from pyverge.migrations.json_patch.backend import JsonPatchMigrationBackend
from pyverge.registry import (
    DEFAULT_HEALTH_LINTERS,
    CompatibilityLinter,
    HealthLinter,
    Registry,
)
from pyverge.schemas.types import (
    ModelAdapter,
)

from .descriptors import ManagerMeta
from .mixins import (
    EngineLifecycleMixin,
    LookupMixin,
    MigrationStoreMixin,
    ModelStoreMixin,
    RuntimeMixin,
    TargetResolutionMixin,
)


class Manager(
    EngineLifecycleMixin[VersionValue],
    TargetResolutionMixin[VersionValue],
    ModelStoreMixin[VersionValue],
    MigrationStoreMixin[VersionValue],
    LookupMixin[VersionValue],
    RuntimeMixin[VersionValue],
    metaclass=ManagerMeta,
):
    """Class factory scoping a migration ``Engine`` to a version strategy.

    Use :meth:`configure` to build a configured class; register models,
    migrations and hooks with the ``model`` / ``migration`` / ``hook``
    decorators at class level or with the registration methods at class or
    instance level; then instantiate for the runtime facade.
    """

    _strategy: ClassVar[type[VersionValue]]  # ty: ignore[invalid-type-form]
    _default_engine: ClassVar[Engine[VersionValue]]  # ty: ignore[invalid-type-form]

    def __class_getitem__(
        cls, strategy: type[VersionValue]
    ) -> type[Manager[VersionValue]]:
        klass = type(
            cls.__name__,
            (cls,),
            {
                "_strategy": strategy,
                "_default_engine": None,
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
    def configure(  # noqa: PLR0913
        cls,
        adapter: ModelAdapter,
        *,
        engine: Engine[VersionValue] | None = None,
        hasher: ContentHasher | None = None,
        model_materializer: DiffMaterializer[object] | None = None,
        migration_materializer: DiffMaterializer[object] | None = None,
        diff_provider: DiffProvider[VersionValue] | None = None,
        on_missing: str = "raise",
        linters: Sequence[HealthLinter] = (),
    ) -> type[Manager[VersionValue]]:
        codec = getattr(adapter, "model_codec", None)
        if codec is None:
            raise ValueError("Adapter must expose a ModelCodec")
        if engine is not None and linters:
            raise ValueError(
                "linters cannot be added to a pre-built engine; configure the "
                "engine's registry instead"
            )
        namespace = codec.namespace
        reflection = Reflector[VersionValue](
            adapter,
            diff_provider or Reflection(adapter, CompositeDiffDiscovery()),
            model_materializer=model_materializer or adapter,
            migration_materializer=(
                migration_materializer
                or MigrationMaterializer(JsonPatchMigrationBackend())
            ),
            on_missing=on_missing,
        )
        if engine is None:
            registry = Registry[VersionValue](
                namespace=namespace,
                hasher=hasher or default_content_hasher(),
                reflection=reflection,
                linters=(
                    *DEFAULT_HEALTH_LINTERS,
                    CompatibilityLinter(
                        frozenset(
                            {
                                adapter.kind_property,
                                adapter.version_property,
                            }
                        )
                    ),
                    *linters,
                ),
                on_missing=on_missing,
            )
            engine = Engine[VersionValue](registry=registry, adapter=adapter)
        cls._default_engine = engine
        return cls
