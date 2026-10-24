"""Execution protocols and type aliases."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

from pyverge.core.context import MigrationContext
from pyverge.core.types import TargetResolver, VersionValue
from pyverge.execution.plan import ExecutionPlan, ExtractedEntry

if TYPE_CHECKING:
    from pyverge.registry import Registry
    from pyverge.versioning import VersionNode

T = TypeVar("T")

#: A discovered versioned entry: ``(path, depth, source)``.
Entry = tuple[tuple[str | int, ...], int, "VersionNode[VersionValue]"]


class EntryExtractor(Protocol[VersionValue]):
    """Protocol for schema-aware payload discovery."""

    @property
    def registry(self) -> Registry[VersionValue]: ...

    def extract(
        self,
        data: dict[str, Any],
        *,
        container: type[Any] | None = None,
        max_depth: int = -1,
    ) -> Iterator[Entry]: ...


@dataclass(frozen=True, slots=True)
class RuntimeCapabilities:
    """Declared runtime capabilities."""

    sync: bool
    async_: bool
    parallel: bool


@runtime_checkable
class ConcurrencyBackend(Protocol):
    """Run sync or async work on a host-appropriate loop/thread."""

    def run(self, work: Callable[..., T], /, *args: Any) -> T: ...
    async def arun(
        self,
        work: Callable[..., Awaitable[T]],
        /,
        *args: Any,
    ) -> T: ...


@runtime_checkable
class RuntimePort(Protocol):
    """Runtime facade consumed by manager/adapters."""

    @property
    def capabilities(self) -> RuntimeCapabilities: ...

    def extract(
        self,
        payload: dict[str, Any],
        *,
        container: type[Any] | None,
        max_depth: int,
    ) -> list[ExtractedEntry]: ...

    def plan(
        self,
        payload: dict[str, Any],
        target_resolver: TargetResolver,
        *,
        container: type[Any] | None,
        max_depth: int,
    ) -> ExecutionPlan: ...

    def execute(
        self,
        plan: ExecutionPlan,
        *,
        context: MigrationContext | None,
    ) -> dict[str, Any]: ...


__all__ = [
    "ConcurrencyBackend",
    "Entry",
    "EntryExtractor",
    "RuntimeCapabilities",
    "RuntimePort",
]
