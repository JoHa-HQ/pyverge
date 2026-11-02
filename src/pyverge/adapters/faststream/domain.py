"""Domain value objects for the FastStream adapter."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from pyverge.core.types import ModelHandle
from pyverge.manager.types import TargetPolicy


class NegotiationError(ValueError):
    """Raised when a negotiated version header cannot be parsed."""


class TopicTargets(Mapping[str, TargetPolicy]):
    """Target policy per topic, for multi-channel subscribers."""

    def __init__(self, targets: Mapping[str, TargetPolicy]) -> None:
        self._targets = dict(targets)

    def __getitem__(self, topic: str) -> TargetPolicy:
        return self._targets[topic]

    def __iter__(self) -> Iterator[str]:
        return iter(self._targets)

    def __len__(self) -> int:
        return len(self._targets)

    def get(self, key: object, default: Any = None) -> Any:
        if not isinstance(key, str):
            return default
        return self._targets.get(key, default)

    @classmethod
    def coerce(
        cls,
        targets: TargetPolicy | TopicTargets,
        topics: tuple[str, ...],
    ) -> TopicTargets:
        """Return *targets* as a per-topic mapping."""
        if isinstance(targets, TopicTargets):
            return targets
        return cls({topic: targets for topic in topics})


class MessageHeaders(Mapping[str, Any]):
    """Case-insensitive view over FastStream message headers."""

    def __init__(self, headers: Mapping[str, Any]) -> None:
        self._headers = {self._normalize(key): value for key, value in headers.items()}

    @staticmethod
    def _normalize(key: Any) -> str:
        if isinstance(key, bytes):
            return key.decode().lower()
        return str(key).lower()

    def __getitem__(self, name: str) -> Any:
        return self._headers[name.lower()]

    def __iter__(self) -> Iterator[str]:
        return iter(self._headers)

    def __len__(self) -> int:
        return len(self._headers)

    def get(self, key: object, default: Any = None) -> Any:
        if not isinstance(key, str):
            return default
        return self._headers.get(key.lower(), default)


@dataclass(frozen=True)
class TargetContext:
    """Selection inputs for one FastStream message."""

    topic: str
    headers: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Binding:
    """Decoration-time metadata for one subscriber or publisher."""

    topics: tuple[str, ...]
    target: TargetPolicy | TopicTargets
    input_model: ModelHandle | None = None
    return_model: ModelHandle | None = None
    header: str | None = None


__all__ = [
    "Binding",
    "MessageHeaders",
    "NegotiationError",
    "TargetContext",
    "TopicTargets",
]
