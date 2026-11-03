from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from functools import singledispatchmethod
from types import MappingProxyType
from typing import Any, Self, cast

from pyverge.core.ids import IdFactory
from pyverge.core.versioning import (
    EdgeId,
    MigrationDescriptor,
    TypeRef,
    VersionNode,
)

from .clock import Clock
from .telemetry import EMPTY_TELEMETRY, TelemetryPublisher

DEFAULT_LOGGER = logging.getLogger("pyverge.runtime")


class MigrationContext(Mapping[str, Any]):
    """Read-only layered view over a migration's runtime bindings."""

    __slots__ = ("_layers",)
    _layers: tuple[Mapping[str, Any], ...]

    def __init__(self, *layers: Mapping[str, Any]) -> None:
        self._layers = tuple(layers)

    @classmethod
    def empty(cls) -> Self:
        return cls()

    @classmethod
    def layered(cls, *layers: Mapping[str, Any]) -> Self:
        return cls(*layers)

    @singledispatchmethod
    @classmethod
    def create(cls, values: Mapping[str, Any] | None = None) -> Self:
        if isinstance(values, MigrationContext):
            return cast(Self, values)
        return cls(cast(Mapping[str, Any], values))

    @create.register(type(None))
    @classmethod
    def _(cls, values: None) -> Self:
        return cls.empty()

    @create.register(dict)
    @classmethod
    def _(cls, values: dict[str, Any]) -> Self:
        return cls(MappingProxyType(values))

    @property
    def view(self) -> Mapping[str, Any]:
        return self

    def __getitem__(self, key: str) -> Any:
        for layer in self._layers:
            if key in layer:
                return layer[key]
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        seen: set[str] = set()
        for layer in self._layers:
            for key in layer:
                if key not in seen:
                    seen.add(key)
                    yield key

    def __len__(self) -> int:
        return sum(1 for _ in self)

    # Mapping supplies value equality, so the context is unhashable — like dict.
    __hash__ = None  # type: ignore[assignment]

    def __repr__(self) -> str:
        return f"MigrationContext({dict(self)!r})"


EMPTY_CONTEXT = MigrationContext.empty()


@dataclass(frozen=True, slots=True)
class ExecutionEnvironment:
    """Host services shared by every run."""

    clock: Clock
    id_factory: IdFactory
    logger: Any
    tracer: Any
    telemetry: TelemetryPublisher = field(default=EMPTY_TELEMETRY)


@dataclass(frozen=True, slots=True)
class RunContext:
    """One execution run."""

    run_id: str
    environment: ExecutionEnvironment
    bindings: MigrationContext

    @property
    def view(self) -> MigrationContext:
        return self.bindings


def _type_ref_name(type_ref: TypeRef) -> str:
    kind = str(type_ref.kind)
    if type_ref.name:
        return f"{kind}[{type_ref.name}]"
    if type_ref.ref is not None:
        return f"{kind}[{type_ref.ref.entity_id}]"
    return kind


@dataclass(frozen=True, slots=True)
class FieldContext:
    """Telemetry-ready description of one model field."""

    name: str
    type: str
    required: bool = False


@dataclass(frozen=True, slots=True)
class DatasetContext:
    """Telemetry-ready description of one versioned dataset."""

    namespace: str
    kind: str
    version: str
    name: str
    fields: tuple[FieldContext, ...] = ()

    @classmethod
    def from_node(cls, node: VersionNode) -> DatasetContext:
        return cls(
            namespace=node.namespace,
            kind=node.kind,
            version=str(node.version),
            name=str(node),
            fields=tuple(
                FieldContext(
                    name=descriptor.name,
                    type=_type_ref_name(descriptor.type_ref),
                    required=descriptor.required,
                )
                for _, descriptor in node.descriptor.fields.sorted_items()
            ),
        )


@dataclass(frozen=True, slots=True)
class StepContext:
    """One migration step inside a run."""

    run: RunContext
    path: tuple[str | int, ...]
    index: int
    source: VersionNode
    target: VersionNode
    edge: EdgeId
    bindings: MigrationContext
    name: str
    migration: MigrationDescriptor | None = None
    source_dataset: DatasetContext = field(init=False)
    target_dataset: DatasetContext = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_dataset",
            DatasetContext.from_node(self.source),
        )
        object.__setattr__(
            self,
            "target_dataset",
            DatasetContext.from_node(self.target),
        )

    @property
    def view(self) -> MigrationContext:
        return MigrationContext.layered(self.bindings, self.run.bindings)


__all__ = [
    "DEFAULT_LOGGER",
    "DatasetContext",
    "ExecutionEnvironment",
    "FieldContext",
    "RunContext",
    "StepContext",
]
