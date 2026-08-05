"""Type aliases needed in the package."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    Protocol,
    TypeAlias,
    TypeVar,
    runtime_checkable,
)

from pendulum import Date
from pydantic import BaseModel
from semver import Version as SemVer

if TYPE_CHECKING:
    from .graph import MigrationGraph
    from .registry import Registry
    from .strategy import EntryMigration

# Invariant — used where VModel appears in both input and output positions
VModel = TypeVar("VModel", bound=BaseModel)
# Invariant — SemVer and Date are parallel strategies, so the components get separated
VersionValue = TypeVar("VersionValue", SemVer, Date)

# TypeVar for migration source and target models
VSource = TypeVar("VSource", bound=BaseModel)
VTarget = TypeVar("VTarget", bound=BaseModel)

# Covariant — used in protocols where VModel is output-only
Container_co = TypeVar("Container_co", bound=BaseModel, covariant=True)
VersionValue_co = TypeVar("VersionValue_co", SemVer, Date, covariant=True)
VModel_co = TypeVar("VModel_co", bound=BaseModel, covariant=True)

JsonPrimities: TypeAlias = int | float | str | bool | None | dict[str, Any] | list[Any]
JsonValue: TypeAlias = JsonPrimities | dict[str, JsonPrimities] | list[JsonPrimities]
JsonSchema: TypeAlias = dict[str, JsonValue]
JsonSchemaMode = Literal["validation", "serialization"]
JsonSchemaDefinitions: TypeAlias = dict[str, JsonValue]
JsonSchemaGenerator: TypeAlias = Callable[[type[BaseModel]], JsonSchema]
SchemaTransformer = Callable[[JsonSchema], JsonSchema]

RenderingFormat = Literal["json-patch"]

Entry = tuple[tuple[str, ...], int, "Versionable[VersionValue, BaseModel]"]
ModelKind: TypeAlias = str
ModelData: TypeAlias = dict[str, Any]
ModelVersionKey: TypeAlias = tuple[ModelKind, VersionValue]

MigrationKey: TypeAlias = tuple[VersionValue, VersionValue]
MigrationFunc: TypeAlias = Callable[[ModelData], ModelData]
MigrationHookMap: TypeAlias = dict["Migratable", list["Attachable"]]
MigrationDirectionStrategy: TypeAlias = Literal["any", "forward", "backward"]
DirectionViolationStrategy: TypeAlias = Literal["skip", "raise"]
VersionMissingStrategy: TypeAlias = Literal["skip", "raise"]
ValidationMode: TypeAlias = Literal["strict", "lax", "none"]
MissingFieldStrategy: TypeAlias = Literal["raise", "skip"]
ExtraFieldStrategy: TypeAlias = Literal["raise", "ignore"]
TargetStrategy: TypeAlias = Literal["latest", "earliest", "skip"]

MigrationKeyInput: TypeAlias = (
    tuple[ModelVersionKey, ModelVersionKey]
    | tuple[type[BaseModel], type[BaseModel]]
    | "VersionPair"
)

TargetSpec: TypeAlias = (
    "Versionable[VersionValue, BaseModel] | type[BaseModel] | TargetStrategy | None"
)
TargetPolicy: TypeAlias = "TargetSpec | dict[ModelKind | Literal['*'], TargetSpec]"


@runtime_checkable
class Versionable(Protocol[VersionValue_co, VModel_co]):
    """Protocol for anything that identifies a model version.

    Shared by :class:`VersionNode` and :class:`SentinelNode`.  The only
    contract is the key dimensions ``(kind, value)`` plus comparison and
    hashing.  A concrete model binding is optional: ``model`` may return
    ``None`` for lightweight sentinels.
    """

    @property
    def strategy(self) -> type[VersionValue_co]: ...
    @property
    def model(self) -> type[VModel_co] | None: ...
    @property
    def version(self) -> tuple[ModelKind, VersionValue_co]: ...
    @property
    def kind(self) -> ModelKind: ...
    def __lt__(self, other: object) -> bool: ...
    def __le__(self, other: object) -> bool: ...
    def __gt__(self, other: object) -> bool: ...
    def __ge__(self, other: object) -> bool: ...
    def __eq__(self, other: object) -> bool: ...
    def __hash__(self) -> int: ...
    def __str__(self) -> str: ...


@runtime_checkable
class Migratable(Protocol[VersionValue, VSource, VTarget]):
    """Protocol for a migration edge identifier.

    Shared by :class:`VersionEdge` and :class:`SentinelEdge`.  Carries
    ``source``, ``target``, ``edge`` and comparison/hash semantics.  A
    registered migration also supplies ``func`` and ``diff``; sentinels
    may leave those as ``None``.
    """

    @property
    def kind(self) -> ModelKind: ...
    @property
    def edge(
        self,
    ) -> tuple[
        Versionable[VersionValue, VSource],
        Versionable[VersionValue, VTarget],
    ]: ...
    @property
    def source(self) -> Versionable[VersionValue, VSource]: ...
    @property
    def target(self) -> Versionable[VersionValue, VTarget]: ...

    func: MigrationFunc | None
    diff: Diffable[VersionValue] | None

    def __call__(self, data: ModelData) -> ModelData: ...
    def __lt__(self, other: object) -> bool: ...
    def __eq__(self, other: object) -> bool: ...
    def __hash__(self) -> int: ...
    def __str__(self) -> str: ...


@runtime_checkable
class Attachable(Protocol):
    """Protocol for migration hook callbacks."""

    def before_migrate(
        self,
        name: str,
        from_version: Versionable,
        to_version: Versionable,
        data: dict[str, Any],
    ) -> None: ...

    def after_migrate(
        self,
        name: str,
        from_version: Versionable,
        to_version: Versionable,
        original_data: dict[str, Any],
        migrated_data: dict[str, Any],
    ) -> None: ...

    def on_error(
        self,
        name: str,
        from_version: Versionable,
        to_version: Versionable,
        data: dict[str, Any],
        error: Exception,
    ) -> None: ...


@runtime_checkable
class Diffable(Protocol[VersionValue_co]):
    """Protocol for objects carrying a computed version diff.

    Implemented by :class:`PydanticDiff`.  Any object that can answer
    structural-change questions about a model version transition
    satisfies this protocol.
    """

    source: Versionable
    target: Versionable
    added_fields: list[str]
    removed_fields: list[str]
    modified_fields: dict[str, dict[str, Any]]
    added_field_info: dict[str, dict[str, Any]]
    unchanged_fields: list[str]
    renderer: type[Renderable]
    is_backward_compatible: bool

    @property
    def kind(self) -> ModelKind:
        """The model family identifier (e.g. ``'User'``)."""
        ...

    @property
    def edge(self) -> MigrationKey:
        """The migration edge key, a tuple of (source, target) versions."""
        ...

    @property
    def is_backward(self) -> bool:
        """True when the source version is newer than the target."""
        ...

    @property
    def is_forward(self) -> bool:
        """True when the source version is older than the target."""
        ...

    @property
    def has_additions(self) -> bool:
        """At least one field was added in the target version."""
        ...

    @property
    def has_removals(self) -> bool:
        """At least one field was removed from the source version."""
        ...

    @property
    def has_modifications(self) -> bool:
        """At least one common field changed type, default, or required status."""
        ...

    @property
    def has_type_changes(self) -> bool:
        """At least one field changed its type annotation."""
        ...

    @property
    def has_constraint_changes(self) -> bool:
        """At least one field changed required/optional status."""
        ...

    def is_added(self, field: str) -> bool:
        """True if *field* exists in target but not source."""
        ...

    def is_removed(self, field: str) -> bool:
        """True if *field* exists in source but not target."""
        ...

    def is_modified(self, field: str) -> bool:
        """True if *field* exists in both but has changed."""
        ...

    def is_added_required(self, field: str) -> bool:
        """True if *field* was added and is required (no default)."""
        ...

    def added_default(self, field: str) -> Any:
        """Return the default value for a newly added field, or None."""
        ...

    def modified_change(self, field: str, key: str) -> Any | None:
        """Return a specific change detail for *field* (e.g. type_changed)."""
        ...

    def is_union_expansion(self, field: str) -> bool:
        """True if *field* changed from required to optional (T -> T|None)."""
        ...

    def is_union_contraction(self, field: str) -> bool:
        """True if *field* changed from optional to required (T|None -> T)."""
        ...

    def render(self) -> Renderable:
        """Render the diff using the configured output strategy."""
        ...


@runtime_checkable
class Renderable(Protocol):
    """Protocol for objects that can be rendered as a string."""

    def __call__(self) -> Any: ...


@runtime_checkable
class ModelAdapter(Protocol):
    """Provider-specific model operations.

    Implementations are provided for each supported model provider
    (Pydantic, attrs, dataclasses, MessagePack, etc.).  The migration
    engine and registry remain provider-agnostic.
    """

    def version(self, model_cls: type[Any]) -> str: ...
    def kind(self, model_cls: type[Any]) -> str: ...
    def finalize(
        self, target_model: type[Any], data: dict[str, Any]
    ) -> dict[str, Any]: ...
    def validate(
        self,
        data: dict[str, Any],
        container: type[Any],
        *,
        strict: bool = False,
    ) -> dict[str, Any]: ...
    def resolve_model(self, annotation: Any) -> type[BaseModel] | None: ...
    def field_model(
        self, parent_model: type[Any], field_name: str
    ) -> type[BaseModel] | None: ...
    def versionable(
        self, model_cls: type[VModel]
    ) -> Versionable[VersionValue, VModel]: ...


VersionPair: TypeAlias = tuple[
    Versionable[VersionValue, VModel], Versionable[VersionValue, VModel]
]

LookupKey: TypeAlias = (
    Versionable[VersionValue, VModel]
    | Migratable[VersionValue, VSource, VTarget]
    | type[VModel]
)


class TargetResolver(Protocol):
    """Callable that selects a convergence target for a discovered entry."""

    def __call__(
        self, kind: ModelKind, current: Versionable[VersionValue, VModel]
    ) -> Versionable[VersionValue, VModel] | None: ...


class Walker(Protocol):
    """Protocol for schema-aware payload discovery."""

    @property
    def registry(self) -> Registry[VersionValue]: ...

    def discover(
        self,
        data: dict[str, Any],
        *,
        container: type[Any] | None = None,
        target_resolver: TargetResolver,
        max_depth: int = -1,
    ) -> Iterator[Entry]: ...


class RunnableMigration(Protocol):
    """Deferred migration of a single graph entry."""

    def run(self) -> ModelData: ...


class Executor(Protocol):
    """Protocol for executing a migration graph."""

    def run(
        self,
        data: ModelData,
        graph: MigrationGraph,
        *,
        registry: Registry,
        entry_migration: EntryMigration,
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
    ) -> ModelData: ...
