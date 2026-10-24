from __future__ import annotations

from collections.abc import Callable
from typing import (
    TYPE_CHECKING,
    ClassVar,
    Literal,
    Protocol,
    Self,
    TypeAlias,
    runtime_checkable,
)

from pyverge.core.types import (
    ManagerMigrationKey,
    MigrationFunc,
    ModelHandle,
    ModelKind,
    ModelPair,
    TargetResolver,
    VersionValue,
    VersionValue_co,
)
from pyverge.schemas.types import (
    ModelAdapter,
)
from pyverge.versioning import Versionable

if TYPE_CHECKING:
    from pyverge.core.types import (
        Attachable,
    )
    from pyverge.discovery.reflection import DiffProvider
    from pyverge.discovery.types import (
        ReflectionReport,
        ReflectionStrategy,
        RegistrationContext,
    )
    from pyverge.execution.types import Walker
    from pyverge.migration.engine import Engine
    from pyverge.migrations.identity import MigrationIdentityResolver
    from pyverge.migrations.json_patch import JsonPatchMigration
    from pyverge.migrations.jsonata import JsonataMigration
    from pyverge.registry import Registry
    from pyverge.sources import SourcePort
    from pyverge.versioning import ContentHasher, DiffMaterializer

TargetStrategy: TypeAlias = Literal["latest", "earliest", "skip"]

TargetSpec: TypeAlias = (
    Versionable[VersionValue_co] | type[ModelHandle] | TargetStrategy | str | None
)
TargetPolicy: TypeAlias = (
    TargetSpec
    | dict[ModelKind | Literal["*"], TargetSpec]
    | TargetResolver[VersionValue_co]
)

#: A callable that binds a registry to a :data:`TargetResolver`; the shape of
#: the ``*_target_resolver`` factories in :mod:`pyverge.execution.targets`.
ResolverFactory: TypeAlias = Callable[
    ["Registry[VersionValue]"], TargetResolver[VersionValue]
]


class ManagerClassState(Protocol[VersionValue]):
    """Class-level defaults shared by every manager instance.

    Established by :meth:`configure` and read by the registration descriptors
    and target-resolution helpers through the class object.
    """

    _strategy: ClassVar[type[VersionValue]]  # ty: ignore[invalid-type-form]
    _default_adapter: ClassVar[ModelAdapter]
    _default_engine: ClassVar[Engine[VersionValue]]  # ty: ignore[invalid-type-form]
    _reflection_locked: ClassVar[bool]

    @classmethod
    def configure(
        cls,
        adapter: ModelAdapter,
        *,
        engine: Engine[VersionValue] | None = None,
        walker: Walker | None = None,
        hasher: ContentHasher | None = None,
        identity_resolver: MigrationIdentityResolver | None = None,
        migration_materializer: DiffMaterializer[object] | None = None,
        diff_provider: DiffProvider[VersionValue] | None = None,
        on_missing: str = "raise",
    ) -> type[Self]: ...

    @classmethod
    def store_model(
        cls,
        key: ModelHandle,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Versionable[VersionValue]: ...

    @classmethod
    def store_migration(
        cls,
        key: ModelPair | ManagerMigrationKey,
        func: MigrationFunc | JsonPatchMigration | JsonataMigration,
        *,
        engine: Engine[VersionValue] | None = None,
        backward_compatible: bool = False,
    ) -> MigrationFunc: ...

    @classmethod
    def add_hook(
        cls,
        key: ModelPair | ManagerMigrationKey,
        hook: Attachable,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> None: ...


class ManagerInstanceState(Protocol[VersionValue]):
    """Runtime state exposed by an instantiated manager."""

    engine: Engine[VersionValue]

    @property
    def registry(self) -> Registry[VersionValue]: ...

    @property
    def adapter(self) -> ModelAdapter: ...


@runtime_checkable
class Reflectable(Protocol):
    """Build-time source reflection surface."""

    @classmethod
    def reflect(
        cls,
        source: SourcePort,
        *,
        strategies: dict[str, ReflectionStrategy] | None = None,
        context: RegistrationContext | None = None,
    ) -> ReflectionReport: ...
