"""Type aliases needed in the package."""

from __future__ import annotations

from collections.abc import Callable
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    Protocol,
    TypeAlias,
    TypeVar,
    runtime_checkable,
)

if TYPE_CHECKING:
    from .versioning import VersionSentinel

from pendulum import Date
from pydantic import BaseModel
from semver import Version as SemVer

# Invariant — used where VModel appears in both input and output positions
VModel = TypeVar("VModel", bound=BaseModel)
# Invariant — SemVer and Date are parallel strategies, so the components get separated
VersionValue = TypeVar("VersionValue", SemVer, Date)

JsonPrimities: TypeAlias = int | float | str | bool | None | dict[str, Any] | list[Any]
JsonValue: TypeAlias = JsonPrimities | dict[str, JsonPrimities] | list[JsonPrimities]
JsonSchema: TypeAlias = dict[str, JsonValue]
JsonSchemaMode = Literal["validation", "serialization"]
JsonSchemaDefinitions: TypeAlias = dict[str, JsonValue]
JsonSchemaGenerator: TypeAlias = Callable[[type[BaseModel]], JsonSchema]
SchemaTransformer = Callable[[JsonSchema], JsonSchema]

Entry = tuple[tuple[str, ...], int, "Versionable"]
ModelKind: TypeAlias = str
ModelData: TypeAlias = dict[str, Any]
ModelVersionKey: TypeAlias = tuple[ModelKind, VersionValue]
MigrationKey: TypeAlias = tuple[
    "Versionable[VersionValue, VModel]", "Versionable[VersionValue, VModel]"
]
MigrationFunc: TypeAlias = Callable[[ModelData], ModelData]
MigrationMap: TypeAlias = dict[MigrationKey, MigrationFunc]
MigrationHookMap: TypeAlias = dict[MigrationKey, list["MigrationHookProtocol"]]

MigrationDirectionStrategy: TypeAlias = Literal["any", "forward", "backward"]
DirectionViolationStragey: TypeAlias = Literal["raise", "warn", "ignore"]
VersionMissingStrategy: TypeAlias = Literal["raise", "warn", "ignore"]
LookupKey: TypeAlias = ModelVersionKey | type[VModel] | MigrationKey

# Covariant — used in protocols where VModel is output-only
Container_co = TypeVar("Container_co", bound=BaseModel, covariant=True)
VersionValue_co = TypeVar("VersionValue_co", SemVer, Date, covariant=True)
VModel_co = TypeVar("VModel_co", bound=BaseModel, covariant=True)


@runtime_checkable
class Findable(Protocol[VersionValue_co]):
    """Protocol for registries that support model lookup.

    Queries use this protocol so they don't depend on :class:`Registry`
    directly — avoiding circular imports.
    """

    def find_model(
        self, key: type[BaseModel] | VersionSentinel[VersionValue_co]
    ) -> Versionable | None: ...
    def latest(self, kind: ModelKind) -> Versionable | None: ...
    def find_migration(
        self, from_v: Versionable, to_v: Versionable
    ) -> MigrationFunc: ...


@runtime_checkable
class Versionable(Protocol[VersionValue_co, VModel_co]):
    """Protocol for version types supporting comparison and serialization."""

    @property
    def strategy(self) -> type[VersionValue]: ...
    @property
    def model(self) -> type[VModel]: ...
    @property
    def version(self) -> tuple[ModelKind, VersionValue]: ...
    def __lt__(self, other: object) -> bool: ...
    def __gt__(self, other: object) -> bool: ...
    def __eq__(self, other: object) -> bool: ...
    def __hash__(self) -> int: ...
    def __str__(self) -> str: ...


class MigrationHookProtocol(Protocol):
    """Protocol for migration hook callbacks."""

    def before_migrate(
        self,
        from_version: Versionable,
        to_version: Versionable,
        data: dict[str, Any],
    ) -> None: ...

    def after_migrate(
        self,
        from_version: Versionable,
        to_version: Versionable,
        original_data: dict[str, Any],
        migrated_data: dict[str, Any],
    ) -> None: ...

    def on_error(
        self,
        from_version: Versionable,
        to_version: Versionable,
        data: dict[str, Any],
        error: Exception,
    ) -> None: ...


class PayloadWalker(Protocol):
    """Protocol for payload traversal and transformation."""

    def discover(
        self, model: type[BaseModel], data: dict[str, Any], vp: str
    ) -> list[Entry]: ...

    def path_get(self, data: dict[str, Any], path: tuple[str | int, ...]) -> Any: ...

    def path_set(
        self, data: dict[str, Any], path: tuple[str | int, ...], value: Any
    ) -> None: ...

    def path_exists(
        self, data: dict[str, Any], path: tuple[str | int, ...]
    ) -> bool: ...
