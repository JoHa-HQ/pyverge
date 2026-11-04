from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from typing import Any, Generic, Self, TypeVar, cast

K = TypeVar("K")
V = TypeVar("V")


class FrozenMap(Mapping[K, V], Generic[K, V]):
    """Immutable, deterministic mapping for canonical IR values.

    Keys keep insertion order for iteration. Canonical consumers should use
    :meth:`sorted_items` when order must not depend on construction.
    """

    __slots__ = ("_data", "_hash")

    _data: dict[K, V]
    _hash: int | None

    def __init__(
        self,
        values: Mapping[K, V] | Iterable[tuple[K, V]] = (),
        /,
    ) -> None:
        self._data = dict(values)
        self._hash = None

    def __getitem__(self, key: K) -> V:
        return self._data[key]

    def __iter__(self) -> Iterator[K]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(frozenset(self._data.items()))
        return self._hash

    def __repr__(self) -> str:
        return f"FrozenMap({self._data!r})"

    def __reduce__(self) -> tuple[type[Self], tuple[dict[K, V]]]:
        return type(self), (dict(self._data),)

    def updated(self, values: Mapping[K, V] | Iterable[tuple[K, V]]) -> Self:
        data = dict(self._data)
        data.update(dict(values))
        return type(self)(data)

    def removed(self, keys: Iterable[K]) -> Self:
        drop = set(keys)
        return type(self)(
            (key, value) for key, value in self._data.items() if key not in drop
        )

    def sorted_items(self) -> tuple[tuple[K, V], ...]:
        return tuple(sorted(self._data.items(), key=lambda item: str(item[0])))

    def to_dict(self) -> dict[Any, Any]:
        return {cast(Any, key): value for key, value in self._data.items()}


__all__ = ["FrozenMap"]
