from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from threading import Lock
from typing import Any, Generic

from pyverge.core.graph.planning.plan import ExtractedEntry, PathPlan
from pyverge.core.types import VersionValue

#: One discovered entry: its payload path and graph identity.
EntrySignature = tuple[tuple[str | int, ...], str]


def target_key(target: Any) -> str | None:
    """Build a stable cache key for a target policy.

    Callable resolvers are dynamic, so they opt out of caching.
    """
    if isinstance(target, type):
        return f"model:{target.__module__}.{target.__qualname__}"
    if isinstance(target, dict):
        items = tuple(
            sorted(
                (str(key), target_key(value) or repr(value))
                for key, value in target.items()
            )
        )
        return f"dict:{items!r}"
    if isinstance(target, (list, tuple)):
        return f"seq:{tuple(target_key(item) or repr(item) for item in target)!r}"
    if all(
        hasattr(target, attribute) for attribute in ("namespace", "kind", "version")
    ):
        return f"node:{target.namespace}:{target.kind}@{target.version}"
    if callable(target):
        return None
    return f"repr:{target!r}"


@dataclass(frozen=True, slots=True)
class PlanKey:
    """Identity of a payload-independent path plan."""

    target: str
    source_model: str | None
    entries: tuple[EntrySignature, ...]

    @classmethod
    def from_entries(
        cls,
        target: Any,
        source_model: Any,
        entries: Sequence[ExtractedEntry[VersionValue]],
    ) -> PlanKey | None:
        resolved_target = target_key(target)
        if resolved_target is None:
            return None
        return cls(
            target=resolved_target,
            source_model=(
                f"{source_model.__module__}.{source_model.__qualname__}"
                if isinstance(source_model, type)
                else None
            ),
            entries=tuple((entry.path, str(entry.node)) for entry in entries),
        )


class PlanCache(Generic[VersionValue]):
    """Bounded or unbounded cache of payload-independent path plans.

    ``0`` disables caching, ``-1`` keeps every entry, and positive values use a
    least-recently-used bound.
    """

    def __init__(self, size: int = 0) -> None:
        if size < -1:
            raise ValueError("plan_cache_size must be 0, -1, or a positive integer")
        self._size = size
        self._entries: OrderedDict[PlanKey, PathPlan[VersionValue]] = OrderedDict()
        self._lock = Lock()

    @property
    def size(self) -> int:
        """Configured cache size: ``0``, ``-1``, or a positive bound."""
        return self._size

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def get(self, key: PlanKey) -> PathPlan[VersionValue] | None:
        """Return a cached plan and mark it as most recently used."""
        if self._size == 0:
            return None
        with self._lock:
            plan = self._entries.get(key)
            if plan is not None:
                self._entries.move_to_end(key)
            return plan

    def put(self, key: PlanKey, plan: PathPlan[VersionValue]) -> None:
        """Store a plan, evicting the least recently used entry when bounded."""
        if self._size == 0:
            return
        with self._lock:
            self._entries[key] = plan
            self._entries.move_to_end(key)
            if self._size > 0:
                while len(self._entries) > self._size:
                    self._entries.popitem(last=False)

    def clear(self) -> None:
        """Drop every cached plan."""
        with self._lock:
            self._entries.clear()


__all__ = [
    "EntrySignature",
    "PlanCache",
    "PlanKey",
    "target_key",
]
