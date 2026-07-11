"""Type aliases needed in the package."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, Protocol, TypeAlias, TypeVar

from pendulum import Date
from pydantic import BaseModel
from semver import Version as SemVer

# Invariant — used where VModel appears in both input and output positions
VModel = TypeVar("VModel", bound=BaseModel)
# Covariant — used in protocols where VModel is output-only
Container_co = TypeVar("Container_co", bound=BaseModel, covariant=True)
# Invariant — SemVer and Date are parallel strategies, so the components get separated
VersionValue = TypeVar("VersionValue", SemVer, Date)

JsonPrimities: TypeAlias = int | float | str | bool | None | dict[str, Any] | list[Any]
JsonValue: TypeAlias = JsonPrimities | dict[str, JsonPrimities] | list[JsonPrimities]
JsonSchema: TypeAlias = dict[str, JsonValue]
JsonSchemaMode = Literal["validation", "serialization"]
JsonSchemaDefinitions: TypeAlias = dict[str, JsonValue]
JsonSchemaGenerator: TypeAlias = Callable[[type[BaseModel]], JsonSchema]
SchemaTransformer = Callable[[JsonSchema], JsonSchema]

Entry = tuple[tuple[str, ...], int, "VersionedModelProtocol"]
ModelData: TypeAlias = dict[str, Any]
MigrationFunc: TypeAlias = Callable[[ModelData], ModelData]
MigrationKey: TypeAlias = tuple[type[VModel], type[VModel]]
MigrationMap: TypeAlias = dict[MigrationKey, MigrationFunc]
MigrationHookMap: TypeAlias = dict[MigrationKey, list["MigrationHookProtocol"]]

MigrationDirectionStrategy: TypeAlias = Literal["any", "forward", "backward"]
DirectionViolationStragey: TypeAlias = Literal["raise", "warn", "ignore"]
VersionMissingStrategy: TypeAlias = Literal["raise", "warn", "ignore"]
LookupKey: TypeAlias = (
    VersionValue |
    type[VModel] |
    slice
)

VersionValue_co = TypeVar("VersionValue_co", SemVer, Date, covariant=True)
VModel_co = TypeVar("VModel_co", bound=BaseModel, covariant=True)
class VersionedModelProtocol(Protocol[VersionValue_co, VModel_co]):
    """Protocol for version types supporting comparison and serialization."""

    @property
    def strategy(self) -> type[VersionValue]: ...
    @property
    def model(self) -> type[VModel]: ...
    @property
    def version(self) -> VersionValue: ...
    def __lt__(self, other: object) -> bool: ...
    def __gt__(self, other: object) -> bool: ...
    def __eq__(self, other: object) -> bool: ...
    def __hash__(self) -> int: ...
    def __str__(self) -> str: ...


class MigrationHookProtocol(Protocol):
    """Protocol for migration hook callbacks."""

    def before_migrate(
        self,
        from_version: VersionedModelProtocol,
        to_version: VersionedModelProtocol,
        data: dict[str, Any],
    ) -> None: ...

    def after_migrate(
        self,
        from_version: VersionedModelProtocol,
        to_version: VersionedModelProtocol,
        original_data: dict[str, Any],
        migrated_data: dict[str, Any],
    ) -> None: ...

    def on_error(
        self,
        from_version: VersionedModelProtocol,
        to_version: VersionedModelProtocol,
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
