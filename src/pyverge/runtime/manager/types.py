from __future__ import annotations

import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Generic,
    NamedTuple,
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
    TargetResolver,
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
    ModelHandle,
    VersionValue,
)
from pyverge.core.versioning import EdgeKey, Versionable, VersionEdge
from pyverge.schemas.types import (
    ModelAdapter,
)

if TYPE_CHECKING:
    from pyverge.core.engine import Engine
    from pyverge.core.registry import HealthLinter, Registry
    from pyverge.core.versioning import ContentHasher, DiffMaterializer
    from pyverge.discovery.reflection import DiffProvider
    from pyverge.migrations.json_patch import JsonPatchMigration
    from pyverge.migrations.jsonata import JsonataMigration
    from pyverge.runtime.facade import Runtime
    from pyverge.runtime.hooks import Attachable


class ModelKey(NamedTuple, Generic[VersionValue]):
    """Typed model key: a model ``kind`` and its ``version`` value."""

    kind: str
    version: VersionValue


class ManagerMigrationKey(NamedTuple):
    """Typed manager migration key: ``kind`` plus source/target versions."""

    kind: str
    source_version: str
    target_version: str
    discriminator: str = "default"


class ModelPair(NamedTuple):
    """Deprecated typed model-pair key.

    Use :class:`ManagerMigrationKey` or an ``EdgeKey`` with a discriminator.
    """

    source: ModelHandle
    target: ModelHandle


def warn_model_pair() -> None:
    """Emit the ModelPair deprecation warning."""
    warnings.warn(
        "ModelPair is deprecated; use ManagerMigrationKey or EdgeKey",
        DeprecationWarning,
        stacklevel=3,
    )


MigrationKeyInput: TypeAlias = ModelPair | ManagerMigrationKey | EdgeKey | VersionEdge

ManagerKey: TypeAlias = ModelKey | ManagerMigrationKey | ModelPair


#: A callable that binds a registry to a :data:`TargetResolver`; the shape of
#: the ``*_target_resolver`` factories in :mod:`pyverge.runtime.targets`.
ResolverFactory: TypeAlias = Callable[
    ["Registry[VersionValue]"], TargetResolver[VersionValue]
]


@dataclass(frozen=True, slots=True)
class ManagerConfig(Generic[VersionValue]):
    """Deprecated configuration bag.

    Pass keywords directly to :meth:`Manager.configure`, or expand
    ``to_kwargs()`` at the call site.
    """

    engine: Engine[VersionValue] | None = None
    walker: Any | None = None
    hasher: ContentHasher | None = None
    identity_resolver: Any | None = None
    model_materializer: DiffMaterializer[object] | None = None
    migration_materializer: DiffMaterializer[object] | None = None
    diff_provider: DiffProvider[VersionValue] | None = None
    on_missing: str = "raise"
    linters: Sequence[HealthLinter] = ()

    def __post_init__(self) -> None:
        warnings.warn(
            "ManagerConfig is deprecated; pass keywords to Manager.configure",
            DeprecationWarning,
            stacklevel=2,
        )
        if self.walker is not None or self.identity_resolver is not None:
            warnings.warn(
                "ManagerConfig.walker and identity_resolver are no longer used",
                DeprecationWarning,
                stacklevel=2,
            )

    def to_kwargs(self) -> dict[str, Any]:
        values: dict[str, Any] = {
            "engine": self.engine,
            "hasher": self.hasher,
            "model_materializer": self.model_materializer,
            "migration_materializer": self.migration_materializer,
            "diff_provider": self.diff_provider,
            "on_missing": self.on_missing,
        }
        if self.linters:
            values["linters"] = self.linters
        return {key: value for key, value in values.items() if value is not None}


class ManagerClassState(Protocol[VersionValue]):
    """Class-level defaults shared by every manager instance.

    Established by :meth:`configure` and read by the registration descriptors
    and target-resolution helpers through the class object.
    """

    _strategy: ClassVar[type[VersionValue]]  # ty: ignore[invalid-type-form]
    _default_engine: ClassVar[Engine[VersionValue]]  # ty: ignore[invalid-type-form]
    _default_runtime: ClassVar[Runtime]

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
        config: ManagerConfig[VersionValue] | None = None,
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
