from __future__ import annotations

from typing import Any

from pyverge.core.types import ModelData


class Path(tuple[str | int, ...]):
    """Containment path: dict keys as ``str``, list indices as ``int``.

    A ``tuple`` subclass, so it is hashable, comparable, and interoperable with
    execution plan entries.
    """

    __slots__ = ()

    def __new__(cls, *steps: str | int) -> Path:
        return super().__new__(cls, steps)

    def get(self, data: ModelData) -> Any:
        if not self:
            return data
        current: Any = data
        for step in self:
            current = current[step]
        return current

    def set(self, data: ModelData, value: Any) -> None:
        if not self:
            if value is data:
                return
            data.clear()
            data.update(value)
            return
        current: Any = data
        for step in self[:-1]:
            current = current[step]
        current[self[-1]] = value

    def is_descendant_of(self, parent: tuple[str | int, ...]) -> bool:
        return len(self) > len(parent) and self[: len(parent)] == parent


__all__ = ["Path"]
