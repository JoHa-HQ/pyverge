from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import singledispatchmethod
from types import MappingProxyType
from typing import Any, Self, cast

from pyverge.core.ids import IdFactory
from pyverge.core.versioning import EdgeKey, VersionNode

from .clock import Clock


class MigrationContext(Mapping[str, Any]):
    """Read-only view over the migration's runtime bindings."""

    __slots__ = ("_view",)
    _view: Mapping[str, Any]

    def __init__(self, view: MappingProxyType[str, Any] | None = None) -> None:
        self._view = view if view is not None else MappingProxyType({})

    @classmethod
    def empty(cls) -> Self:
        return cls(MappingProxyType({}))

    @singledispatchmethod
    @classmethod
    def create(cls, values: Mapping[str, Any] | None = None) -> Self:
        if isinstance(values, MigrationContext):
            return cast(Self, values)
        return cls(cast(MappingProxyType[str, Any], values))

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
        return self._view

    def __getitem__(self, key: str) -> Any:
        return self._view[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._view)

    def __len__(self) -> int:
        return len(self._view)

    # Mapping supplies value equality, so the context is unhashable — like dict.
    __hash__ = None  # type: ignore[assignment]

    def __repr__(self) -> str:
        return f"MigrationContext({dict(self._view)!r})"


EMPTY_CONTEXT = MigrationContext.empty()


class LayeredView(Mapping[str, Any]):
    """Read-only layered mapping: earlier layers take precedence."""

    def __init__(self, layers: Sequence[Mapping[str, Any]]) -> None:
        self._layers = tuple(layers)

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

    def __repr__(self) -> str:
        return f"LayeredView({dict(self)!r})"


@dataclass(frozen=True, slots=True)
class ExecutionEnvironment:
    """Host services shared by every run."""

    clock: Clock
    id_factory: IdFactory
    logger: Any
    tracer: Any


@dataclass(frozen=True, slots=True)
class RunContext:
    """One execution run."""

    run_id: str
    environment: ExecutionEnvironment
    bindings: MigrationContext

    @property
    def view(self) -> MigrationContext:
        return self.bindings


@dataclass(frozen=True, slots=True)
class StepContext:
    """One migration step inside a run."""

    run: RunContext
    path: tuple[str | int, ...]
    index: int
    source: VersionNode
    target: VersionNode
    edge: EdgeKey
    bindings: MigrationContext

    @property
    def view(self) -> MigrationContext:
        return MigrationContext.create(LayeredView((self.bindings, self.run.bindings)))


__all__ = [
    "ExecutionEnvironment",
    "LayeredView",
    "RunContext",
    "StepContext",
]
