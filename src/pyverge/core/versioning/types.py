from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
    TypeAlias,
    TypeVar,
    Union,
    runtime_checkable,
)

from pyverge.core.types import (
    ModelKind,
    VersionValue_co,
)

from .canonical import ContentHasher
from .identity import NodeId
from .identity.metadata import KeyRef

if TYPE_CHECKING:
    from pyverge.core.types import Attachable

    from .diff import Diff
    from .identity import EdgeId, EdgeKey, VersionEdge, VersionKey, VersionNode
    from .identity.metadata import ModelDescriptor, ModelRef

T_co = TypeVar("T_co", covariant=True)
RenderOutput = TypeVar("RenderOutput")
MaterializedOutput = TypeVar("MaterializedOutput")


@runtime_checkable
class Digestible(Protocol):
    """Stable identity digest independent of metadata refs."""

    def digest(self, hasher: ContentHasher) -> str: ...


@runtime_checkable
class Identifiable(Digestible, Protocol):
    """Stable identity shared by nodes and edges."""

    @property
    def id(self) -> NodeId[Any] | EdgeId[Any]: ...


@runtime_checkable
class Namespaced(Protocol):
    """Namespace-qualified graph identity."""

    @property
    def namespace(self) -> str: ...
    @property
    def kind(self) -> ModelKind: ...


@runtime_checkable
class Ordered(Protocol):
    """Total ordering, hashing, and display identity."""

    def __lt__(self, other: object, /) -> bool: ...
    def __gt__(self, other: object, /) -> bool: ...
    def __eq__(self, other: object, /) -> bool: ...
    def __hash__(self) -> int: ...
    def __str__(self) -> str: ...


@runtime_checkable
class Versioned(Protocol[VersionValue_co]):
    """Version strategy and parsed version value."""

    @property
    def strategy(self) -> type[VersionValue_co]: ...
    @property
    def version(self) -> VersionValue_co: ...


@runtime_checkable
class Edged(Protocol):
    """Directed edge identity."""

    @property
    def source(self) -> NodeId[Any]: ...
    @property
    def target(self) -> NodeId[Any]: ...
    @property
    def key(self) -> tuple[NodeId[Any], NodeId[Any]]: ...


@runtime_checkable
class Fingerprintable(Protocol):
    """Projects domain content into a canonical payload for hashing."""

    def fingerprint_payload(self) -> Mapping[str, Any]: ...


@runtime_checkable
class Comparable(
    Identifiable,
    Namespaced,
    Ordered,
    Versioned,
    Protocol[VersionValue_co],
):
    """Version identity: namespace, kind, version, and ordering."""

    @property
    def id(self) -> NodeId[Any]: ...


@runtime_checkable
class ModelRefProvider(Protocol):
    """A graph value that can expose a provider model reference."""

    @property
    def modelref(self) -> ModelRef: ...


@runtime_checkable
class Versionable(
    Comparable[VersionValue_co],
    ModelRefProvider,
    Protocol[VersionValue_co],
):
    """Materialized version with a serializable model descriptor."""

    @property
    def descriptor(self) -> ModelDescriptor: ...
    @property
    def modelref(self) -> ModelRef: ...
    @property
    def references(self) -> frozenset[NodeId]: ...
    @property
    def fields(self) -> frozenset[str]: ...


@runtime_checkable
class Transitional(
    Identifiable,
    Namespaced,
    Ordered,
    Edged,
    Protocol[VersionValue_co],
):
    """Directed edge identity: ``source`` -> ``target``."""

    @property
    def id(self) -> EdgeId[Any]: ...


class DiffProvider(Protocol):
    """Anything that can build a schema diff from two version endpoints."""

    def diff(
        self,
        source: Versionable,
        target: Comparable,
    ) -> Diff: ...


@runtime_checkable
class Migratable(
    Transitional[VersionValue_co], Digestible, Protocol[VersionValue_co]
):
    """Executable transition: endpoint identity plus diff and callable."""

    @property
    def diff(self) -> Diffable[VersionValue_co]: ...


@runtime_checkable
class DiffRenderer(Protocol[T_co]):
    """Render a schema diff with a pluggable strategy."""

    def render(self, diff: Diffable) -> T_co: ...


@runtime_checkable
class DiffMaterializer(Protocol[T_co]):
    """Materialize a migration artifact from a schema diff."""

    def materialize(self, diff: Diffable) -> T_co: ...


@runtime_checkable
class Delta(Protocol[T_co]):
    """A structured added/removed/modified delta."""

    @property
    def added(self) -> frozenset[T_co]: ...
    @property
    def removed(self) -> frozenset[T_co]: ...
    @property
    def modified(self) -> frozenset[T_co]: ...
    @property
    def changed(self) -> bool: ...


class DiffOrigin(StrEnum):
    """How a diff was produced."""

    SCHEMA = "schema"
    MIGRATION = "migration"


@runtime_checkable
class Diffable(Protocol[VersionValue_co]):
    """Protocol for objects carrying a computed version diff."""

    @property
    def source(self) -> Versionable: ...
    @property
    def target(self) -> Comparable: ...
    @property
    def origin(self) -> DiffOrigin: ...
    def fingerprint_payload(self) -> Mapping[str, Any]: ...
    def render(self, renderer: DiffRenderer[RenderOutput]) -> RenderOutput: ...
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


MigrationKey: TypeAlias = tuple[NodeId, NodeId]
VersionPair = tuple[Comparable[VersionValue_co], Comparable[VersionValue_co]]
LookupKey = Versionable[VersionValue_co] | Migratable[VersionValue_co]
MigrationHookMap: TypeAlias = dict[Migratable, list["Attachable"]]

#: Normalized node entries accepted by the engine and registry.
NodeEntry: TypeAlias = Union["VersionKey", "VersionNode"]

#: Normalized edge entries accepted by the engine and registry.
EdgeEntry: TypeAlias = Union["EdgeKey", "VersionEdge"]


__all__ = [
    "Comparable",
    "Delta",
    "DiffMaterializer",
    "DiffOrigin",
    "DiffProvider",
    "DiffRenderer",
    "Diffable",
    "Digestible",
    "EdgeEntry",
    "Edged",
    "Fingerprintable",
    "Identifiable",
    "KeyRef",
    "LookupKey",
    "Migratable",
    "MigrationHookMap",
    "MigrationKey",
    "ModelRefProvider",
    "Namespaced",
    "NodeEntry",
    "Ordered",
    "Transitional",
    "VersionPair",
    "Versionable",
    "Versioned",
]
