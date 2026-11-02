"""Handler reflection and signature binding for FastStream."""

from __future__ import annotations

import inspect
from typing import Any

from pyverge.adapters.handlers import HandlerView
from pyverge.schemas.types import ModelHandle


class SignatureBinder:
    """Bind by replacing the handler's reflected signature in place."""

    @staticmethod
    def _first_param_name(handler: Any) -> str | None:
        for name, param in inspect.signature(handler).parameters.items():
            if param.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                return name
        return None

    def bind(self, handler: Any, model: ModelHandle) -> None:
        param = self._first_param_name(handler)
        if param is None:
            return
        signature = inspect.signature(handler)
        handler.__signature__ = signature.replace(
            parameters=[
                p.replace(annotation=model) if name == param else p
                for name, p in signature.parameters.items()
            ]
        )
        annotations = getattr(handler, "__annotations__", None)
        if annotations is not None:
            annotations[param] = model


__all__ = ["HandlerView", "SignatureBinder"]
