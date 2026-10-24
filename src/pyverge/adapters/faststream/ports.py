"""FastStream adapter ports.

These protocols isolate the FastStream host objects from pyverge's reflection
and decorator logic. Concrete wrappers in :mod:`.views` implement them.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from pyverge.schemas.types import ModelHandle


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


__all__ = ["HandlerPort", "PublisherPort", "SubscriberPort"]
