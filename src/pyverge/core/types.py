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
    from pyverge.migration.graph import MigrationGraph
    from pyverge.migration.registry import Registry
    from pyverge.migration.strategy import EntryMigration

ModelBase: TypeAlias = BaseModel

TContainer = TypeVar("TContainer", bound=BaseModel)
# Invariant — used where VModel appears in both input and output positions
VModel = TypeVar("VModel", bound=BaseModel)
# Invariant — SemVer and Date are parallel strategies, so the components get separated
VersionValue = TypeVar("VersionValue", SemVer, Date)

ProviderBase = TypeVar("ProviderBase", bound=ModelBase)

# TypeVar for migration source and target models
VSource_co = TypeVar("VSource_co", bound=BaseModel, covariant=True)
VTarget_co = TypeVar("VTarget_co", bound=BaseModel, covariant=True)
# Covariant — used in protocols where VModel is output-only
VersionValue_co = TypeVar("VersionValue_co", SemVer, Date, covariant=True)
VModel_co = TypeVar("VModel_co", bound=ModelBase, covariant=True)
# Migration-format covariance — any callable `(ModelData) -> ModelData`
# (plain fn or JsonPatch) satisfies the bound.
MigrationFunc_co = TypeVar(
    "MigrationFunc_co",
    bound="Callable[[ModelData], ModelData]",
    covariant=True,
)
# Invariant — Registry is mutable (store/remove), so its type params must be
# invariant even though the protocol-facing covariant variants exist above.
ProviderBase_co = TypeVar("ProviderBase_co", bound=ModelBase, covariant=True)
Renderable_co = TypeVar("Renderable_co", covariant=True)
Container_co = TypeVar("Container_co", bound=BaseModel, covariant=True)

JsonPrimities: TypeAlias = int | float | str | bool | None | dict[str, Any] | list[Any]
JsonValue: TypeAlias = JsonPrimities | dict[str, JsonPrimities] | list[JsonPrimities]
JsonSchema: TypeAlias = dict[str, JsonValue]
JsonSchemaMode = Literal["validation", "serialization"]
JsonSchemaDefinitions: TypeAlias = dict[str, JsonValue]
JsonSchemaGenerator: TypeAlias = Callable[[type[ModelBase]], JsonSchema]
SchemaTransformer = Callable[[JsonSchema], JsonSchema]

RenderingFormat = Literal["json-patch"]

Entry = tuple[tuple[str | int, ...], int, "Versionable[VersionValue, BaseModel]"]
ModelKind: TypeAlias = str
ModelData: TypeAlias = dict[str, Any]
ModelVersionKey: TypeAlias = tuple[ModelKind, VersionValue]

MigrationKey: TypeAlias = tuple[VersionValue, VersionValue]
#: Length of a migration endpoint-pair key, e.g. ``(source, target)``.
MIGRATION_PAIR_LEN: int = 2
MigrationFunc: TypeAlias = Callable[[ModelData], ModelData]
MigrationHookMap: TypeAlias = dict["Migratable", list["Attachable"]]
MigrationDirectionStrategy: TypeAlias = Literal["any", "forward", "backward"]
DirectionViolationStrategy: TypeAlias = Literal["skip", "raise"]
VersionMissingStrategy: TypeAlias = Literal["skip", "raise"]
ValidationMode: TypeAlias = Literal["strict", "lax", "none"]
MissingFieldStrategy: TypeAlias = Literal["raise", "skip"]
ExtraFieldStrategy: TypeAlias = Literal["raise", "ignore"]
TargetStrategy: TypeAlias = Literal["latest", "earliest", "skip"]


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

    @property
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
    def resolve_model(self, annotation: Any) -> type[ModelBase] | None: ...
    def field_model(
        self, parent_model: type[Any], field_name: str
    ) -> type[ModelBase] | None: ...
    def versionable(
        self,
        model_cls: type[VModel_co] | None,
        *,
        kind: str | None = None,
        version: str | None = None,
    ) -> Versionable[VersionValue_co, VModel_co]:
        """Wrap a model class into a versionable, or build a meta versionable.

        With a model class, the node carries it and ``version``/``kind`` are
        read from the class.  With ``None``, a meta node (no concrete model)
        is built from *kind* and *version* strings.
        """
        ...
    def diff(
        self,
        source: Versionable[VersionValue_co, VModel_co],
        target: Versionable[VersionValue_co, VModel_co],
        *,
        is_backward_compatible: bool = False,
    ) -> Diffable[VersionValue_co]: ...

    def materialize(
        self,
        anchor: type[ModelBase],
        diff: Diffable[VersionValue_co],
        version: VersionValue_co,
    ) -> type[ModelBase]:
        """Materialize a model for *version* from an *anchor* and a *diff*.

        The anchor is the nearest version with a concrete model; the diff
        describes the structural change between the anchor and the version to
        materialize.  The returned model conforms to this provider.
        """
        ...


VersionPair: TypeAlias = tuple[
    Versionable[VersionValue_co, VModel_co], Versionable[VersionValue_co, VModel_co]
]

LookupKey: TypeAlias = (
    Versionable[VersionValue_co, VModel_co]
    | Migratable[VersionValue_co, VSource_co, VTarget_co]
    | type[VModel_co]
)

TargetResolver: TypeAlias = Callable[
    [Versionable[VersionValue_co, VModel_co]],
    Versionable[VersionValue_co, VModel_co] | None,
]


ManagerMigrationKeyInput: TypeAlias = (
    tuple[type[VModel_co], type[VModel_co]] | tuple[str, str, str]
)


TargetSpec: TypeAlias = (
    Versionable[VersionValue_co, VModel_co]
    | type[VModel_co]
    | TargetStrategy
    | str
    | None
)
TargetPolicy: TypeAlias = (
    TargetSpec[VersionValue_co, VModel_co]
    | dict[ModelKind | Literal["*"], TargetSpec[VersionValue_co, VModel_co]]
    | TargetResolver[VersionValue_co, VModel_co]
)


class Walker(Protocol):
    """Protocol for schema-aware payload discovery."""

    @property
    def registry(self) -> Registry[VersionValue_co, VModel_co]: ...

    def discover(
        self,
        data: dict[str, Any],
        *,
        container: type[Any] | None = None,
        target_resolver: TargetResolver[VersionValue_co, VModel_co],
        max_depth: int = -1,
    ) -> Iterator[Entry[VersionValue_co]]: ...


class RunnableMigration(Protocol):
    """Deferred migration of a single graph entry."""

    def run(self) -> ModelData: ...


class Executor(Protocol):
    """Protocol for executing a migration graph."""

    def run(
        self,
        data: ModelData,
        graph: MigrationGraph[VersionValue_co],
        *,
        registry: Registry[VersionValue_co, VModel_co],
        entry_migration: EntryMigration[VersionValue_co],
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
    ) -> ModelData: ...
