"""Path utilities shared across the migration engine.

The internal path representation — :class:`Path` — is used by the executor
and the walkers to locate versioned entries inside a payload.
"""

from __future__ import annotations

from typing import Any

from .types import ModelData


class Path(tuple[str | int, ...]):
    """Containment path: dict keys as ``str``, list indices as ``int``.

    A ``tuple`` subclass, so it is hashable, comparable, and interoperable with
    the engine's ``GraphEntry.path``.
    """

    __slots__ = ()

    def __new__(cls, *steps: str | int) -> Path:
        return super().__new__(cls, steps)


def get_at(data: ModelData, path: tuple[str | int, ...]) -> Any:
    """Return the value at *path* inside *data*."""
    if not path:
        return data
    current: Any = data
    for step in path:
        current = current[step]
    return current


def set_at(data: ModelData, path: tuple[str | int, ...], value: Any) -> None:
    """Write *value* at *path*, mutating *data* in place."""
    if not path:
        if value is data:
            return
        data.clear()
        data.update(value)
        return
    current: Any = data
    for step in path[:-1]:
        current = current[step]
    current[path[-1]] = value
