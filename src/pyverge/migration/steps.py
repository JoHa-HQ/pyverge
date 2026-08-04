"""Migration step strategies — used by :class:`Engine` for execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Protocol

from .types import (
    Attachable,
    Migratable,
    ModelData,
    VersionValue,
    VSource,
    VTarget,
)


class _Step(Protocol):
    """A single migration step that can be executed."""

    def execute(
        self,
        data: ModelData,
        hooks: list[Attachable],
    ) -> ModelData: ...


@dataclass(frozen=True, slots=True)
class ExplicitStep(Generic[VersionValue, VSource, VTarget]):
    """Step backed by a registered :class:`Migratable` edge.

    ``from_version`` / ``to_version`` are derived from the edge itself and
    passed to the hooks — no external endpoints are required.
    """

    edge: Migratable[VersionValue, VSource, VTarget]

    def execute(
        self,
        data: ModelData,
        hooks: list[Attachable],
    ) -> ModelData:
        kind = self.edge.kind
        from_version = self.edge.source
        to_version = self.edge.target
        for hook in hooks:
            hook.before_migrate(str(kind), from_version, to_version, data)
        result = self.edge(data)
        for hook in hooks:
            hook.after_migrate(str(kind), from_version, to_version, data, result)
        return result
