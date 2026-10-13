"""Core type surface: keys, aliases, and provider-neutral protocols.

Behavior classes (``VersionNode``/``VersionEdge``/``SentinelEdge``) live in
:mod:`pyverge.core.versioning`; this module owns only passive type surface so
the core can be imported by every layer without pulling behavior.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import (
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

# ---------------------------------------------------------------------------
# Version axis
# ---------------------------------------------------------------------------

#: Core version value axis: semver and ISO dates are parallel strategies.
VersionValue = TypeVar("VersionValue", SemVer, Date)
#: Covariant form for protocols where the version is output-only.
VersionValue_co = TypeVar("VersionValue_co", SemVer, Date, covariant=True)

Renderable_co = TypeVar("Renderable_co", covariant=True)

#: Opaque, provider-owned model handle.  Core storage keys models by this
#: without naming any provider model base, so a non-Python backend can map it.
ModelHandle: TypeAlias = type[Any]

# ---------------------------------------------------------------------------
# JSON aliases
# ---------------------------------------------------------------------------

JsonPrimities: TypeAlias = int | float | str | bool | None | dict[str, Any] | list[Any]
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

MigrationKey: TypeAlias = tuple[VersionValue, VersionValue]
#: Length of a migration endpoint-pair key, e.g. ``(source, target)``.
MIGRATION_PAIR_LEN: int = 2
MigrationFunc: TypeAlias = Callable[[ModelData], ModelData]
#: How a diff came to be: discovered from a registered migration, or computed
#: from two concrete schemas.  Selects the reflection strategy when no explicit
#: setting applies.
DiffOrigin: TypeAlias = Literal["migration", "schema"]
MigrationDirectionStrategy: TypeAlias = Literal["any", "forward", "backward"]
DirectionViolationStrategy: TypeAlias = Literal["skip", "raise"]
VersionMissingStrategy: TypeAlias = Literal["skip", "raise"]
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

MigrationHookMap: TypeAlias = dict["Migratable", list["Attachable"]]


# ---------------------------------------------------------------------------
# Versioning protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class Orderable(Protocol):
    """Functional aspect: total ordering + hashing + dedupe.

    Shared ordering contract for version nodes and migration edges.
    Compatible with :func:`functools.total_ordering`: ``__le__``/``__ge__``
    are derived from ``__lt__``/``__gt__``/``__eq__`` by the decorator.
    """

    @property
    def kind(self) -> ModelKind: ...
    def __lt__(self, other: object, /) -> bool: ...
    def __gt__(self, other: object, /) -> bool: ...
    def __eq__(self, other: object, /) -> bool: ...
    def __hash__(self) -> int: ...
    def __str__(self) -> str: ...


@runtime_checkable
class Comparable(Orderable, Protocol[VersionValue_co]):
    """Version identity aspect: ``strategy`` + ``version``, plus ordering.

    Implemented by :class:`~pyverge.core.versioning.VersionNode`.
    """

    @property
    def strategy(self) -> type[VersionValue_co]: ...
    @property
    def version(self) -> tuple[ModelKind, VersionValue_co]: ...


@runtime_checkable
class Versionable(Comparable[VersionValue_co], Protocol[VersionValue_co]):
    """Protocol for a model version that always binds an opaque model handle.

    Adds a required ``model`` binding on top of :class:`Comparable`.  The model
    is an opaque, provider-owned :data:`ModelHandle`; core never names a
    provider model base.  Shared by ``VersionNode``.  A model-less node
    (``_model=None``) is orderable and satisfies :class:`Comparable`.
    """

    @property
    def model(self) -> ModelHandle: ...

    @property
    def references(self) -> frozenset[ModelVersionKey]:
        """Versioned ``(kind, version)`` pairs the model's fields declare."""
        ...

    @property
    def fields(self) -> frozenset[str]:
        """The model's field names, minus the identity fields.

        Computed by the adapter when the node is built (like ``references``),
        so the engine can compare two nodes' shapes without an adapter.
        """
        ...


@runtime_checkable
class Transitional(Orderable, Protocol[VersionValue_co]):
    """Edge identity aspect: a directed ``source`` → ``target`` transition.

    Implemented by ``VersionEdge`` and ``SentinelEdge``.  Carries ``source``,
    ``target``, ``edge`` and ordering semantics, but no execution.  Endpoints
    are :class:`Comparable` so edges may reference sentinel keys.
    """

    @property
    def edge(self) -> tuple[Comparable, Comparable]: ...
    @property
    def source(self) -> Comparable: ...
    @property
    def target(self) -> Comparable: ...


@runtime_checkable
class Migratable(Transitional[VersionValue_co], Protocol[VersionValue_co]):
    """Executable aspect: a transition that can run a migration.

    Adds a required ``func`` and ``diff`` on top of :class:`Transitional`.
    Implemented by ``VersionEdge``; sentinels are key-only and satisfy
    :class:`Transitional` only.
    """

    func: MigrationFunc
    diff: Diffable[VersionValue_co]

    def __call__(self, data: ModelData) -> ModelData: ...


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


@runtime_checkable
class Diffable(Protocol[VersionValue_co]):
    """Protocol for objects carrying a computed version diff.

    Implemented by :class:`~pyverge.reflection.Diff`.  Any object that can
    answer structural-change questions about a model version transition
    satisfies this protocol.
    """

    @property
    def source(self) -> Versionable: ...
    @property
    def target(self) -> Versionable: ...
    @property
    def origin(self) -> DiffOrigin: ...
    def inverted(self) -> Diffable: ...
    @property
    def added_fields(self) -> list[str]: ...
    @property
    def removed_fields(self) -> list[str]: ...
    @property
    def modified_fields(self) -> dict[str, dict[str, Any]]: ...
    @property
    def added_field_info(self) -> dict[str, dict[str, Any]]: ...
    @property
    def unchanged_fields(self) -> list[str]: ...
    @property
    def renderer(self) -> type[Renderable]: ...
    @property
    def is_backward_compatible(self) -> bool: ...
    @property
    def kind(self) -> ModelKind: ...
    @property
    def edge(self) -> MigrationKey: ...
    @property
    def is_backward(self) -> bool: ...
    @property
    def is_forward(self) -> bool: ...
    @property
    def has_additions(self) -> bool: ...
    @property
    def has_removals(self) -> bool: ...
    @property
    def has_modifications(self) -> bool: ...
    @property
    def has_type_changes(self) -> bool: ...
    @property
    def has_constraint_changes(self) -> bool: ...
    def is_added(self, field: str) -> bool: ...
    def is_removed(self, field: str) -> bool: ...
    def is_modified(self, field: str) -> bool: ...
    def is_added_required(self, field: str) -> bool: ...
    def added_default(self, field: str) -> Any: ...
    def modified_change(self, field: str, key: str) -> Any | None: ...
    def is_union_expansion(self, field: str) -> bool: ...
    def is_union_contraction(self, field: str) -> bool: ...
    @property
    def render(self) -> Renderable: ...


@runtime_checkable
class Renderable(Protocol[VersionValue_co, Renderable_co]):
    """A renderable object holding its own diff state.

    Implementations preserve the :class:`Diffable` they were built from, so
    callers may keep the renderer around and (re)render or export patches
    later.  Calling it produces the typed rendered output.
    """

    @property
    def diff(self) -> Diffable[VersionValue_co]: ...
    @property
    def format(self) -> str: ...
    def __call__(self) -> Renderable_co: ...


VersionPair = tuple[Versionable[VersionValue_co], Versionable[VersionValue_co]]

LookupKey = Versionable[VersionValue_co] | Migratable[VersionValue_co]

TargetResolver = Callable[
    [Versionable[VersionValue_co]],
    Versionable[VersionValue_co] | None,
]
