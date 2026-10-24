"""Runtime values shared with migration providers.

A migration may need values that are only known at execution time — tenant
identifiers, request timestamps, exchange rates. They travel as a
:class:`MigrationContext`: a read-only **view** over the caller's mapping, not a
copy. Creating one is O(1), and the same instance is passed to every provider
in a run.

Because the context is a view, the caller must not mutate the underlying
mapping while a migration is in flight. Read-only here means the context does
not expose mutation, not that it snapshots the values.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from functools import singledispatchmethod
from types import MappingProxyType
from typing import Any, Self, cast


class MigrationContext(Mapping[str, Any]):
    """Read-only view over the migration's runtime bindings."""

    __slots__ = ("_view",)
    _view: Mapping[str, Any]

    def __init__(self, view: MappingProxyType[str, Any] | None = None) -> None:
        """Wrap an already prepared view; factories build the view first."""
        self._view = view if view is not None else MappingProxyType({})

    @classmethod
    def empty(cls) -> Self:
        """Create an empty context."""
        return cls(MappingProxyType({}))

    @singledispatchmethod
    @classmethod
    def create(cls, values: Mapping[str, Any] | None = None) -> Self:
        """Create a context from *values* without copying them."""
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
        """The backing view, for providers that need a plain mapping."""
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
