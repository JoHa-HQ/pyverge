"""Shared handler reflection for framework adapters."""

from __future__ import annotations

import inspect
import types
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pyverge.schemas.types import ModelAdapter, ModelHandle


@dataclass(frozen=True)
class HandlerView:
    """A callable's declared payload and return models."""

    handler: Callable[..., Any]
    adapter: ModelAdapter

    @staticmethod
    def _original(handler: Any) -> Any:
        return getattr(handler, "_original_call", handler)

    @classmethod
    def _first_model(cls, adapter: ModelAdapter, annotation: Any) -> ModelHandle | None:
        resolved = adapter.resolve_model(annotation)
        if resolved is not None:
            return resolved
        if typing.get_origin(annotation) in (typing.Union, types.UnionType):
            for member in typing.get_args(annotation):
                model = cls._first_model(adapter, member)
                if model is not None:
                    return model
        return None

    @classmethod
    def _resolved_hints(cls, handler: Any) -> dict[str, Any]:
        try:
            return typing.get_type_hints(handler)
        except Exception:
            return {}

    @property
    def input_model(self) -> ModelHandle | None:
        original = self._original(self.handler)
        hints = self._resolved_hints(original)
        for name, param in inspect.signature(original).parameters.items():
            annotation = hints.get(name, param.annotation)
            model = self._first_model(self.adapter, annotation)
            if model is not None:
                return model
        return None

    @property
    def return_model(self) -> ModelHandle | None:
        original = self._original(self.handler)
        hints = self._resolved_hints(original)
        annotation = hints.get("return")
        if annotation is None:
            annotation = inspect.signature(original).return_annotation
        return annotation if isinstance(annotation, type) else None


__all__ = ["HandlerView"]
