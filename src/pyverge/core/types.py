from __future__ import annotations

from collections.abc import Callable
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Literal,
    NamedTuple,
    Protocol,
    TypeAlias,
    TypeVar,
    runtime_checkable,
)

from pendulum import Date
from semver import Version as SemVer

from .context import MigrationContext

if TYPE_CHECKING:
    from pyverge.versioning import (
        Comparable,
        VersionNode,
    )

# ---------------------------------------------------------------------------
# Version axis
# ---------------------------------------------------------------------------

#: Core version value axis: semver and ISO dates are parallel strategies.
VersionValue = TypeVar("VersionValue", SemVer, Date)
#: Covariant form for protocols where the version is output-only.
VersionValue_co = TypeVar("VersionValue_co", SemVer, Date, covariant=True)

#: Opaque, provider-owned model handle.  Core storage keys models by this
#: without naming any provider model base, so a non-Python backend can map it.
ModelHandle: TypeAlias = type[Any]

# ---------------------------------------------------------------------------
# JSON aliases
# ---------------------------------------------------------------------------

JsonPrimities: TypeAlias = int | float | str | bool | dict[str, Any] | list[Any] | None
JsonValue: TypeAlias = JsonPrimities | dict[str, JsonPrimities] | list[JsonPrimities]
JsonSchema: TypeAlias = dict[str, JsonValue]
JsonSchemaMode = Literal["validation", "serialization"]
JsonSchemaDefinitions: TypeAlias = dict[str, JsonValue]
JsonSchemaGenerator: TypeAlias = Callable[[type[Any]], JsonSchema]
SchemaTransformer = Callable[[JsonSchema], JsonSchema]

RenderingFormat = Literal["json-patch"]

# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------

ModelKind: TypeAlias = str
ModelData: TypeAlias = dict[str, Any]
ModelVersionKey: TypeAlias = tuple[ModelKind, VersionValue]

#: Length of a migration endpoint-pair key, e.g. ``(source, target)``.
MIGRATION_PAIR_LEN: int = 2
MigrationFunc: TypeAlias = Callable[[ModelData, MigrationContext | None], ModelData]
#: How a diff came to be: discovered from a registered migration, or computed
#: from two concrete schemas.  Selects the reflection strategy when no explicit
#: setting applies.
MigrationDirectionStrategy: TypeAlias = Literal["any", "forward", "backward"]
DirectionViolationStrategy: TypeAlias = Literal["skip", "raise"]
VersionMissingStrategy: TypeAlias = Literal["skip", "raise"]
DepthViolationStrategy: TypeAlias = Literal["skip", "raise"]
ValidationMode: TypeAlias = Literal["strict", "lax", "none"]
MissingFieldStrategy: TypeAlias = Literal["raise", "skip"]
ExtraFieldStrategy: TypeAlias = Literal["raise", "ignore"]
TargetStrategy: TypeAlias = Literal["latest", "earliest", "skip"]


class ModelKey(NamedTuple, Generic[VersionValue]):
    """Typed model key: a model ``kind`` and its ``version`` value."""

    kind: ModelKind
    version: VersionValue


class ManagerMigrationKey(NamedTuple):
    """Typed manager migration key: ``kind`` plus source/target versions."""

    kind: ModelKind
    source_version: str
    target_version: str


class ModelPair(NamedTuple):
    """Typed model-pair key: the ``source`` and ``target`` model handles."""

    source: ModelHandle
    target: ModelHandle


#: Accepted migration-key shapes for the manager's registration methods.
MigrationKeyInput: TypeAlias = ModelPair | ManagerMigrationKey

ManagerKey: TypeAlias = ModelKey | ManagerMigrationKey | ModelPair


# ---------------------------------------------------------------------------
# Behavior protocols (version protocols live in pyverge.versioning)
# ---------------------------------------------------------------------------


@runtime_checkable
class Attachable(Protocol):
    """Protocol for migration hook callbacks."""

    def before_migrate(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        data: dict[str, Any],
    ) -> None: ...

    def after_migrate(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        original_data: dict[str, Any],
        migrated_data: dict[str, Any],
    ) -> None: ...

    def on_error(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        data: dict[str, Any],
        error: Exception,
    ) -> None: ...


class TargetResolver(Protocol[VersionValue]):
    """Resolve a discovered version to its target node, or skip it."""

    def __call__(
        self, current: VersionNode[VersionValue]
    ) -> VersionNode[VersionValue] | None: ...
