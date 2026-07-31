"""Migration step strategies — used by :class:`Engine` for execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .types import Attachable, Migratable, ModelData


class _Step(Protocol):
    """A single migration step that can be executed."""

    def execute(
        self,
        data: ModelData,
        hooks: list[Attachable],
        from_version: Any,
        to_version: Any,
    ) -> ModelData: ...


@dataclass(frozen=True, slots=True)
class ExplicitStep:
    """Step backed by a registered :class:`Migratable` edge."""

    edge: Migratable[Any, Any, Any]

    def execute(
        self,
        data: ModelData,
        hooks: list[Attachable],
        from_version: Any,
        to_version: Any,
    ) -> ModelData:
        kind = getattr(from_version, "kind", "unknown")
        for hook in hooks:
            hook.before_migrate(str(kind), from_version, to_version, data)
        result = self.edge(data)
        for hook in hooks:
            hook.after_migrate(str(kind), from_version, to_version, data, result)
        return result
