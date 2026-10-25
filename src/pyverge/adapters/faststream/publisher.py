"""The publish decorator: converge a handler's return to an outgoing target.

The counterpart of :func:`.subscriber`. Applied at the endpoint, it converges the
handler's return value to *target* before FastStream serializes and publishes it,
so a handler can bridge schema versions across a topic boundary.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from functools import wraps
from typing import Any, cast

from pyverge import Manager
from pyverge.manager.types import TargetPolicy
from pyverge.schemas.types import ModelHandle

from .types import Fn, PayloadDumper, ResultConverger
from .views import HandlerView, PublisherView


def return_model(handler: Any) -> ModelHandle | None:
    """Return the handler's return annotation when it is a class."""
    return HandlerView(handler).return_model


class ReturnConverger:
    """Wrap a handler so its return is dumped and converged before publish.

    When the handler declares a return model, the wrapper's return is
    re-annotated to the resolved *out_model*, so FastStream's response
    serialization validates the converged payload against the version actually
    published.
    """

    def __init__(
        self,
        manager: Manager,
        dump: PayloadDumper,
        target: TargetPolicy,
        out_model: ModelHandle | None = None,
    ) -> None:
        self._manager = manager
        self._dump = dump
        self._target = target
        self._out_model = out_model

    def wrap(self, handler: Fn) -> Fn:
        out_model = self._out_model

        @wraps(handler)
        async def converged(*args: Any, **kwargs: Any) -> Any:
            result = await handler(*args, **kwargs)
            if result is None:
                return None
            runner = self._manager.runner()
            migrated = runner.run(
                self._dump(result),
                self._target,
                container=None,
                max_depth=-1,
                context=None,
            )
            return await migrated if inspect.isawaitable(migrated) else migrated

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

    def decorate(fn: Fn) -> Any:
        published = PublisherView(fn, topics)
        declared = published.return_model
        out_model = (
            manager.resolve_target_model(declared, target)
            if declared is not None and manager.identifies(declared)
            else None
        )
        result = result_converger or ReturnConverger(
            manager,
            manager.dump,
            target,
            out_model=out_model,
        )
        return broker.publisher(*topics, **options)(result.wrap(fn))

    return decorate


def publish_to(
    broker: Any,
    *,
    routes: Mapping[str, TargetPolicy],
    manager: Manager,
    version_header: str = "content-version",
) -> Callable[[Fn], Fn]:
    """Publish one handler result to multiple topics with per-topic targets.

    The handler returns a model (or mapping) unchanged. The result is dumped
    once, then converged separately for each route before publishing.
    """

    def decorate(fn: Fn) -> Fn:
        @wraps(fn)
        async def routed(*args: Any, **kwargs: Any) -> None:
            result = await fn(*args, **kwargs)
            if result is None:
                return
            payload = manager.dump(result)
            for topic, target in routes.items():
                runner = manager.runner()
                migrated = runner.run(
                    payload,
                    target,
                    container=None,
                    max_depth=-1,
                    context=None,
                )
                converged = (
                    await migrated if inspect.isawaitable(migrated) else migrated
                )
                version = converged.get("version")
                headers: dict[str, Any] = {}
                if version is not None:
                    headers[version_header] = str(version)
                await broker.publish(converged, topic, headers=headers)

        annotations = dict(getattr(fn, "__annotations__", {}))
        annotations["return"] = type(None)
        routed.__annotations__ = annotations
        setattr(
            routed,
            "__signature__",
            inspect.signature(fn).replace(return_annotation=type(None)),
        )
        return cast("Fn", routed)

    return decorate


__all__ = [
    "ReturnConverger",
    "publish_to",
    "publisher",
    "return_model",
]
