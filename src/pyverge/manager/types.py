from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar, Literal, Protocol, Self, TypeAlias

from pyverge.core.types import (
    DirectionViolationStrategy,
    ManagerMigrationKey,
    MigrationDirectionStrategy,
    MigrationFunc,
    ModelData,
    ModelHandle,
    ModelKind,
    ModelPair,
    TargetResolver,
    Versionable,
    VersionMissingStrategy,
    VersionValue,
    VersionValue_co,
)
from pyverge.providers.types import (
    ModelAdapter,
    TContainer,
)

if TYPE_CHECKING:
    from pyverge.core.settings import MigrationSettings
    from pyverge.core.types import (
        Attachable,
    )
    from pyverge.executor import (
        AsyncExecutor,
        Executor,
        MigrationEntry,
        MigrationRun,
    )
    from pyverge.migration.engine import Engine
    from pyverge.migration.registry import Registry
    from pyverge.migration.types import (
        Walker,
    )
    from pyverge.providers.json_patch import JsonPatchMigration
    from pyverge.providers.jsonata import JsonataMigration

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
#: the ``*_target_resolver`` factories in :mod:`pyverge.migration.policy`.
ResolverFactory: TypeAlias = Callable[
    ["Registry[VersionValue]"], TargetResolver[VersionValue]
]


class ManagerClassState(Protocol[VersionValue]):
    """Class-level defaults shared by every manager instance.

    Established by :meth:`configure` and read by the registration descriptors
    and target-resolution helpers through the class object.
    """

    _strategy: ClassVar[type[VersionValue]]  # ty: ignore[invalid-type-form]
    _default_settings: ClassVar[MigrationSettings]
    _default_adapter: ClassVar[ModelAdapter]
    _default_engine: ClassVar[Engine[VersionValue]]  # ty: ignore[invalid-type-form]

    @classmethod
    def configure(
        cls,
        settings: MigrationSettings,
        adapter: ModelAdapter,
        *,
        engine: Engine[VersionValue] | None = None,
        walker: Walker | None = None,
        executor: Executor | AsyncExecutor | None = None,
        entry_migration: MigrationEntry[VersionValue] | None = None,
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
    def settings(self) -> MigrationSettings | None: ...

    @property
    def adapter(self) -> ModelAdapter: ...

    def delegate(
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
        executor: Executor | AsyncExecutor | None = None,
        entry_migration: MigrationEntry[VersionValue] | None = None,
    ) -> MigrationRun[VersionValue]: ...

    def prepare(
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
        executor: Executor | AsyncExecutor | None = None,
        entry_migration: MigrationEntry[VersionValue] | None = None,
    ) -> MigrationRun[VersionValue]: ...
