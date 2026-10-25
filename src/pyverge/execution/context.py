from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pyverge.core.clock import Clock
from pyverge.core.context import MigrationContext
from pyverge.core.ids import IdFactory
from pyverge.versioning import EdgeKey, VersionNode


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
