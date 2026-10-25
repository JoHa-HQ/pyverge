"""Execution protocols and type aliases."""

from __future__ import annotations

from collections.abc import Awaitable, Iterator
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

from pyverge.core.context import MigrationContext
from pyverge.core.types import TargetResolver, VersionValue
from pyverge.execution.context import RunContext
from pyverge.execution.plan import ExecutionPlan
from pyverge.schemas.types import ModelAdapter

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


class BackendPort(Protocol[VersionValue]):
    """Execution backend seam: plan + payload + run context."""

    def execute(
        self,
        plan: ExecutionPlan[VersionValue],
        payload: dict[str, Any],
        run: RunContext,
        adapter: ModelAdapter,
    ) -> dict[str, Any] | Awaitable[dict[str, Any]]: ...


@runtime_checkable
class RuntimePort(Protocol[VersionValue]):
    """Runtime facade consumed by manager/adapters."""

    def plan(
        self,
        payload: dict[str, Any],
        target_resolver: TargetResolver,
        *,
        container: type[Any] | None,
        max_depth: int,
    ) -> ExecutionPlan[VersionValue]: ...

    def run(
        self,
        payload: dict[str, Any],
        target_resolver: TargetResolver,
        *,
        container: type[Any] | None,
        max_depth: int,
        context: MigrationContext | None,
    ) -> Any: ...

    def execute(
        self,
        plan: ExecutionPlan,
        *,
        context: MigrationContext | None,
    ) -> Any: ...


__all__ = [
    "BackendPort",
    "Entry",
    "EntryExtractor",
    "RuntimePort",
]
