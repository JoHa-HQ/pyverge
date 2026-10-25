from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from functools import singledispatch, singledispatchmethod
from typing import Any, Protocol, TypeVar, cast

from pyverge.core.types import ModelData, ModelHandle
from pyverge.manager.types import TargetPolicy

Fn = TypeVar("Fn", bound=Callable[..., Any])


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
        return _as_topic_targets(targets, topics)


@singledispatch
def _as_topic_targets(targets: Any, topics: tuple[str, ...]) -> TopicTargets:
    value = cast("TargetPolicy", targets)
    return TopicTargets({topic: value for topic in topics})


@_as_topic_targets.register
def _(
    targets: TopicTargets,
    topics: tuple[str, ...],
) -> TopicTargets:
    return targets


@singledispatch
def _header_name(key: Any) -> str:
    return str(key).lower()


@_header_name.register
def _(key: bytes) -> str:
    return key.decode().lower()


class MessageHeaders(Mapping[str, Any]):
    """Case-insensitive view over FastStream message headers."""

    def __init__(self, headers: Mapping[str, Any]) -> None:
        self._headers = {_header_name(key): value for key, value in headers.items()}

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


class HeaderParser:
    """Parse a negotiated target header.

    Scalar values are target policies; JSON objects are per-kind mappings.
    """

    @singledispatchmethod
    def parse(self, value: Any) -> TargetPolicy:
        raise NegotiationError("version header must be a string")

    @parse.register
    def _(self, value: bytes) -> TargetPolicy:
        return self.parse(value.decode())

    @parse.register
    def _(self, value: str) -> TargetPolicy:
        raw = value.strip()
        if not raw:
            raise NegotiationError("version header must be a non-empty string")
        if raw.startswith("{"):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise NegotiationError(f"invalid version header JSON: {exc}") from exc
            return self._mapping(parsed)
        return raw

    @singledispatchmethod
    def _mapping(self, value: Any) -> TargetPolicy:
        raise NegotiationError(
            "version header mapping must contain string keys and values"
        )

    @_mapping.register
    def _(self, value: dict) -> TargetPolicy:
        if not all(
            isinstance(key, str) and isinstance(item, str)
            for key, item in value.items()
        ):
            raise NegotiationError(
                "version header mapping must contain string keys and values"
            )
        return cast("TargetPolicy", value)


@dataclass(frozen=True)
class TargetContext:
    """Selection inputs for one FastStream message."""

    topic: str
    headers: Mapping[str, Any]


class TargetSelector(Protocol):
    """Select one target policy, or ``None`` when this selector does not apply."""

    def select(self, context: TargetContext) -> TargetPolicy | None: ...


class HandlerBinder(Protocol):
    """Binds a handler's typed payload parameter to a model or union."""

    def bind(self, handler: Any, model: Any) -> None: ...


class ResultConverger(Protocol):
    """Wraps a handler so its return value is converged before publish."""

    def wrap(self, handler: Fn) -> Fn: ...


class PayloadDumper(Protocol):
    """Dumps a handler return value into a payload mapping."""

    def __call__(self, value: object) -> ModelData: ...


class HandlerPort(Protocol):
    """One callable with its declared payload and return models."""

    @property
    def handler(self) -> Callable[..., Any]: ...

    @property
    def input_model(self) -> ModelHandle | None: ...

    @property
    def return_model(self) -> ModelHandle | None: ...


class SubscriberPort(Protocol):
    """One FastStream subscriber exposed as reflected properties."""

    @property
    def topics(self) -> tuple[str, ...]: ...

    @property
    def handler(self) -> Callable[..., Any] | None: ...

    @property
    def input_model(self) -> ModelHandle | None: ...


class PublisherPort(Protocol):
    """One FastStream publisher exposed as reflected properties."""

    @property
    def topics(self) -> tuple[str, ...]: ...

    @property
    def handler(self) -> Callable[..., Any] | None: ...

    @property
    def return_model(self) -> ModelHandle | None: ...


__all__ = [
    "Fn",
    "HandlerBinder",
    "HandlerPort",
    "HeaderParser",
    "MessageHeaders",
    "NegotiationError",
    "PayloadDumper",
    "PublisherPort",
    "ResultConverger",
    "SubscriberPort",
    "TargetContext",
    "TargetSelector",
    "TopicTargets",
]
