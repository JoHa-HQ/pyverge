from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    Protocol,
    TypeAlias,
    TypeVar,
    Union,
    runtime_checkable,
)

if TYPE_CHECKING:
    from pyverge.core.versioning import (
        VersionKey,
        VersionNode,
    )

# ---------------------------------------------------------------------------
# Version axis
# ---------------------------------------------------------------------------


@runtime_checkable
class VersionValueProtocol(Protocol):
    """Ordering and hashing contract for one parsed version value.

    ``semver.Version`` and ``pendulum.Date`` satisfy this. Custom version
    strategies must provide a stable string form, total ordering, equality,
    and hashing before they can occupy the version slot.
    """

    def __str__(self) -> str: ...
    def __lt__(self, other: Any, /) -> bool: ...
    def __gt__(self, other: Any, /) -> bool: ...
    def __le__(self, other: Any, /) -> bool: ...
    def __ge__(self, other: Any, /) -> bool: ...
    def __hash__(self) -> int: ...


#: Core version value axis: any value satisfying the ordering protocol.
VersionValue = TypeVar("VersionValue", bound=VersionValueProtocol)
#: Covariant form for protocols where the version is output-only.
VersionValue_co = TypeVar("VersionValue_co", bound=VersionValueProtocol, covariant=True)

#: Per-execution hook state supplied by the execution backend.
HookState: TypeAlias = ContextVar[dict[int, tuple[Any, ...]]]

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

#: Length of a migration endpoint-pair key, e.g. ``(source, target)``.
MIGRATION_PAIR_LEN: int = 2
MigrationFunc: TypeAlias = Callable[[ModelData, Any], ModelData]
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


#: How a registration handles an existing graph entry.
RegistrationMode: TypeAlias = Literal["strict", "reconcile"]

#: Public node inputs accepted by the manager before normalization.
NodeInput: TypeAlias = Union[ModelHandle, "VersionKey", "VersionNode"]

# ---------------------------------------------------------------------------
# Behavior protocols (version protocols live in pyverge.core.versioning)
# ---------------------------------------------------------------------------
