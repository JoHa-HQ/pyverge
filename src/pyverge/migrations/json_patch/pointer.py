from __future__ import annotations

from typing import Any

import jsonpointer

from pyverge.core.types import (
    ModelData,
)


class Pointer(tuple[str | int, ...]):
    """RFC 6901 pointer: dict keys as ``str``, list indices as ``int``.

    The array-append marker ``-`` is not numeric and remains a ``str`` token.
    """

    __slots__ = ()

    def __new__(cls, *steps: str | int) -> Pointer:
        return super().__new__(cls, steps)

    @classmethod
    def from_pointer(cls, path: str) -> Pointer:
        if not path:
            return cls()
        parts = jsonpointer.JsonPointer(path).parts
        return cls(*(int(tok) if tok.isdigit() else tok for tok in parts))

    def get(self, data: ModelData) -> Any:
        current: Any = data
        for step in self:
            current = current[step]
        return current

    def set(self, data: ModelData, value: Any) -> None:
        if not self:
            data.clear()
            data.update(value)
            return
        current: Any = data
        for step in self[:-1]:
            current = current[step]
        current[self[-1]] = value
