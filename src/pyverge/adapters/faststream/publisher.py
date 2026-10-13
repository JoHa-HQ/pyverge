"""The publish decorator: converge a handler's return to an outgoing target.

The counterpart of :func:`.subscriber`. Applied at the endpoint, it converges the
handler's return value to *target* before FastStream serializes and publishes it,
so a handler can bridge schema versions across a topic boundary.
"""

from __future__ import annotations

import inspect
import typing
from collections.abc import Callable
from functools import wraps
from typing import Any, cast

from pyverge import Manager
from pyverge.manager.types import TargetPolicy
from pyverge.providers.types import ModelHandle

from .convergence import Converger
from .types import Fn, PayloadDumper, ResultConverger


def return_model(handler: Any) -> ModelHandle | None:
    """Return the handler's return annotation when it is a class."""
    try:
        hints = typing.get_type_hints(handler)
    except Exception:
        hints = {}
    annotation = hints.get("return")
    if annotation is None:
        annotation = inspect.signature(handler).return_annotation
    return annotation if isinstance(annotation, type) else None


class ReturnConverger:
    """Wrap a handler so its return is dumped and converged before publish.

    When the handler declares a return model, the wrapper's return is
    re-annotated to the resolved *out_model*, so FastStream's response
    serialization validates the converged payload against the version actually
    published.
    """

    def __init__(
        self,
        converger: Converger,
        dump: PayloadDumper,
        out_model: ModelHandle | None = None,
    ) -> None:
        self._converger = converger
        self._dump = dump
        self._out_model = out_model

    def wrap(self, handler: Fn) -> Fn:
        out_model = self._out_model

        @wraps(handler)
        async def converged(*args: Any, **kwargs: Any) -> Any:
            result = await handler(*args, **kwargs)
            if result is None:
                return None
            return self._converger.converge(self._dump(result))

        if out_model is not None:
            annotations = dict(getattr(converged, "__annotations__", {}))
            annotations["return"] = out_model
            setattr(converged, "__annotations__", annotations)
            setattr(
                converged,
                "__signature__",
                inspect.signature(handler).replace(return_annotation=out_model),
            )

        return cast("Fn", converged)


def publisher(
    broker: Any,
    *topics: str,
    manager: Manager,
    target: TargetPolicy = "latest",
    result_converger: ResultConverger | None = None,
    **options: Any,
) -> Callable[[Fn], Any]:
    """Return a decorator registering a converging publisher on *broker*.

    The handler's return value is converged to *target* before publish. Extra
    *options* pass through to ``broker.publisher``.
    """
    converger = Converger(manager, target)

    def decorate(fn: Fn) -> Any:
        declared = return_model(fn)
        out_model = (
            manager.resolve_target_model(declared, target)
            if declared is not None and manager.identifies(declared)
            else None
        )
        result = result_converger or ReturnConverger(
            converger, manager.dump, out_model=out_model
        )
        return broker.publisher(*topics, **options)(result.wrap(fn))

    return decorate


__all__ = ["ReturnConverger", "publisher", "return_model"]
