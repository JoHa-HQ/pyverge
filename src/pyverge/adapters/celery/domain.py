"""Domain value objects for the Celery adapter."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pyverge.core.types import ModelHandle
from pyverge.manager.types import TargetPolicy


@dataclass(frozen=True, slots=True)
class TaskContext:
    """Selection inputs for one Celery task invocation."""

    name: str
    queue: str | None
    headers: Mapping[str, Any]

    def header(self, name: str) -> Any:
        """Return a header value case-insensitively."""
        for key, value in self.headers.items():
            normalized = key.decode() if isinstance(key, bytes) else str(key)
            if normalized.lower() == name.lower():
                return value
        return None


@dataclass(frozen=True, slots=True)
class TaskBinding:
    """Decoration-time metadata for one task."""

    name: str
    target: TargetPolicy
    input_model: ModelHandle | None = None
    return_model: ModelHandle | None = None
    header: str | None = None


__all__ = ["TaskBinding", "TaskContext"]
