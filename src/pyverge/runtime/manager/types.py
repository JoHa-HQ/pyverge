from __future__ import annotations

from collections.abc import Callable
from typing import (
    TYPE_CHECKING,
    ClassVar,
    Protocol,
    Self,
    TypeAlias,
)

from pyverge.core.graph.planning.targets import (
    DefaultTarget as DefaultTarget,  # noqa: PLC0414
)
from pyverge.core.graph.planning.targets import (
    FirstMatch as FirstMatch,  # noqa: PLC0414
)
from pyverge.core.graph.planning.targets import (
    TargetPolicy as TargetPolicy,  # noqa: PLC0414
)
from pyverge.core.graph.planning.targets import (
    TargetSelector as TargetSelector,  # noqa: PLC0414
)
from pyverge.core.graph.planning.targets import (
    TargetSpec as TargetSpec,  # noqa: PLC0414
)
from pyverge.core.graph.planning.targets import (
    TargetStrategy as TargetStrategy,  # noqa: PLC0414
)
from pyverge.core.graph.planning.targets import (
    VersionRange as VersionRange,  # noqa: PLC0414
)
from pyverge.core.types import (
    MigrationFunc,
    MigrationKeyInput,
    ModelHandle,
    TargetResolver,
    VersionValue,
)
from pyverge.core.versioning import Versionable
from pyverge.schemas.types import (
    ModelAdapter,
)

if TYPE_CHECKING:
    from pyverge.core.engine import Engine
    from pyverge.core.registry import Registry
    from pyverge.core.types import (
        Attachable,
    )
    from pyverge.core.versioning import ContentHasher, DiffMaterializer
    from pyverge.discovery.reflection import DiffProvider
    from pyverge.migrations.json_patch import JsonPatchMigration
    from pyverge.migrations.jsonata import JsonataMigration


#: A callable that binds a registry to a :data:`TargetResolver`; the shape of
#: the ``*_target_resolver`` factories in :mod:`pyverge.runtime.targets`.
ResolverFactory: TypeAlias = Callable[
    ["Registry[VersionValue]"], TargetResolver[VersionValue]
]


class ManagerClassState(Protocol[VersionValue]):
    """Class-level defaults shared by every manager instance.

    Established by :meth:`configure` and read by the registration descriptors
    and target-resolution helpers through the class object.
    """

    _strategy: ClassVar[type[VersionValue]]  # ty: ignore[invalid-type-form]
    _default_engine: ClassVar[Engine[VersionValue]]  # ty: ignore[invalid-type-form]

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
        key: MigrationKeyInput,
        func: MigrationFunc | JsonPatchMigration | JsonataMigration,
        *,
        engine: Engine[VersionValue] | None = None,
        backward_compatible: bool = False,
        migration_id: str | None = None,
    ) -> MigrationFunc: ...

    @classmethod
    def add_hook(
        cls,
        key: MigrationKeyInput,
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
