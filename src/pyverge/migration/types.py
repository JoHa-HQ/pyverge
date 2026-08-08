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

ModelBase: TypeAlias = BaseModel

TContainer = TypeVar("TContainer", bound=BaseModel)
# Invariant — used where VModel appears in both input and output positions
VModel = TypeVar("VModel", bound=BaseModel)
# Invariant — SemVer and Date are parallel strategies, so the components get separated
VersionValue = TypeVar("VersionValue", SemVer, Date)

# TypeVar for migration source and target models
VSource_co = TypeVar("VSource_co", bound=BaseModel, covariant=True)
VTarget_co = TypeVar("VTarget_co", bound=BaseModel, covariant=True)

# Covariant — used in protocols where VModel is output-only
VersionValue_co = TypeVar("VersionValue_co", SemVer, Date, covariant=True)
VModel_co = TypeVar("VModel_co", bound=ModelBase, covariant=True)

ProviderBase_co = TypeVar(
    "ProviderBase_co", bound=ModelBase, covariant=True, default=ModelBase
)
Renderable_co = TypeVar("Renderable_co", covariant=True)
Container_co = TypeVar("Container_co", bound=BaseModel, covariant=True)

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
class Orderable(Protocol):
    """Functional aspect: total ordering + hashing + dedupe.

    Shared ordering contract for version nodes and migration edges.
    Compatible with :func:`functools.total_ordering`: ``__le__``/``__ge__``
    are derived from ``__lt__``/``__gt__``/``__eq__`` by the decorator.
    """

    @property
    def kind(self) -> ModelKind: ...
    def __lt__(self, other: object) -> bool: ...
    def __gt__(self, other: object) -> bool: ...
    def __eq__(self, other: object) -> bool: ...
    def __hash__(self) -> int: ...
    def __str__(self) -> str: ...


@runtime_checkable
class Comparable(Orderable, Protocol[VersionValue_co]):
    """Version identity aspect: ``strategy`` + ``version``, plus ordering.

    Implemented by :class:`VersionNode` and :class:`SentinelNode`.
    """

    @property
    def strategy(self) -> type[VersionValue_co]: ...
    @property
    def version(self) -> tuple[ModelKind, VersionValue_co]: ...


@runtime_checkable
class Versionable(Comparable[VersionValue_co], Protocol[VersionValue_co, VModel_co]):
    """Protocol for a model version that always binds a model.

    Adds a required ``model`` binding on top of :class:`Comparable`.  Shared
    by :class:`VersionNode`.  Lightweight sentinels (:class:`SentinelNode`)
    are orderable but model-less, so they satisfy :class:`Comparable` only.
    """

    @property
    def model(self) -> type[VModel_co]: ...


@runtime_checkable
class Transitional(Orderable, Protocol[VersionValue_co, VSource_co, VTarget_co]):
    """Edge identity aspect: a directed ``source`` → ``target`` transition.

    Implemented by :class:`VersionEdge` and :class:`SentinelEdge`.  Carries
    ``source``, ``target``, ``edge`` and ordering semantics, but no execution.
    Endpoints are :class:`Comparable` so edges may reference sentinel keys.
    """

    @property
    def edge(self) -> tuple[Comparable, Comparable]: ...
    @property
    def source(self) -> Comparable: ...
    @property
    def target(self) -> Comparable: ...


@runtime_checkable
class Migratable(
    Transitional[VersionValue, VSource_co, VTarget_co],
    Protocol[VersionValue, VSource_co, VTarget_co],
):
    """Executable aspect: a transition that can run a migration.

    Adds a required ``func`` and ``diff`` on top of :class:`Transitional`.
    Implemented by :class:`VersionEdge`; sentinels are key-only and satisfy
    :class:`Transitional` only.
    """

    func: MigrationFunc
    diff: Diffable[VersionValue]

    def __call__(self, data: ModelData) -> ModelData: ...


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

    @property
    def source(self) -> Versionable: ...

    @property
    def target(self) -> Versionable: ...

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

    def render(self) -> Renderable: ...


@runtime_checkable
class Renderable(Protocol[VersionValue, Renderable_co]):
    """A renderable object holding its own diff state.

    Implementations preserve the :class:`Diffable` they were built from, so
    callers may keep the renderer around and (re)render or export patches
    later.  Calling it produces the typed rendered output.
    """

    @property
    def diff(self) -> Diffable[VersionValue]: ...

    @property
    def format(self) -> str: ...

    def __call__(self) -> Renderable_co: ...


@runtime_checkable
class ModelAdapter(Protocol):
    """Provider-specific model operations.

    Anchored to a model provider via ``ProviderBase_co`` at use sites.
    Implementations are provided for each supported model provider (Pydantic,
    attrs, dataclasses, MessagePack, etc.).  The migration engine and registry
    remain provider-agnostic.
    """

    def version(self, model_cls: type[Any]) -> str: ...
    def kind(self, model_cls: type[Any]) -> str: ...
    def of(self, value: str) -> VersionValue:
        """Parse a version string into a version value.

        Understands both semver and ISO date strings.
        """
        ...

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
        self, model_cls: type[VModel_co]
    ) -> Versionable[VersionValue_co, VModel_co]: ...


VersionPair: TypeAlias = tuple[
    Versionable[VersionValue_co, VModel_co], Versionable[VersionValue_co, VModel_co]
]

LookupKey: TypeAlias = (
    Versionable[VersionValue_co, VModel_co]
    | Migratable[VersionValue_co, VSource_co, VTarget_co]
    | type[VModel_co]
)


class TargetResolver(Protocol):
    """Callable that selects a convergence target for a discovered entry."""

    def __call__(
        self, kind: ModelKind, current: Versionable[VersionValue_co, VModel_co]
    ) -> Versionable[VersionValue_co, VModel_co] | None: ...


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
