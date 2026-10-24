"""Default handler binding.

``HandlerBinder`` (the port) lives in :mod:`.types`; ``SignatureBinder`` is its
default adapter. The port lets the mechanism change (a generated shim, or a
wrapper around FastStream's registration) without touching the subscriber
decorator.
"""

from __future__ import annotations

import inspect
from typing import Any

from pyverge.schemas.types import ModelHandle


def first_param_name(handler: Any) -> str | None:
    """Return the name of the handler's first positional parameter."""
    for name, param in inspect.signature(handler).parameters.items():
        if param.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            return name
    return None


class SignatureBinder:
    """Bind by replacing the handler's reflected signature in place."""

    def bind(self, handler: Any, model: ModelHandle) -> None:
        param = first_param_name(handler)
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


__all__ = ["SignatureBinder", "first_param_name"]
