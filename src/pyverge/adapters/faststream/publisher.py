from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from functools import wraps
from typing import Any, cast

from pyverge.runtime.manager.types import TargetPolicy
from pyverge.schemas.types import ModelHandle

from .handlers import HandlerView
from .ports import Fn, ResultConverger
from .runtime import FastStreamRuntime


class ReturnConverger:
    """Wrap a handler so its return is dumped and converged before publish.

    When the handler declares a return model, the wrapper's return is
    re-annotated to the resolved *out_model*, so FastStream's response
    serialization validates the converged payload against the version actually
    published.
    """

    def __init__(
        self,
        runtime: FastStreamRuntime,
        target: TargetPolicy,
        out_model: ModelHandle | None = None,
    ) -> None:
        self._runtime = runtime
        self._target = target
        self._out_model = out_model

    def wrap(self, handler: Fn) -> Fn:
        out_model = self._out_model

        @wraps(handler)
        async def converged(*args: Any, **kwargs: Any) -> Any:
            result = await handler(*args, **kwargs)
            if result is None:
                return None
            source_model = type(result)
            if not self._runtime.manager.adapter.can_handle(source_model):
                source_model = None
            return await self._runtime.converge(
                self._runtime.dump(result),
                self._target,
                source_model=source_model,
            )

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


class PublisherBinding:
    """Bind one handler to one converging FastStream publisher."""

    def __init__(  # noqa: PLR0913
        self,
        broker: Any,
        runtime: FastStreamRuntime,
        topics: tuple[str, ...],
        *,
        target: TargetPolicy = "latest",
        result_converger: ResultConverger | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> None:
        self._broker = broker
        self._runtime = runtime
        self._manager = runtime.manager
        self._topics = topics
        self._target = target
        self._result_converger = result_converger
        self._options = dict(options or {})

    def bind(self, fn: Fn) -> Any:
        """Declare the handler and register the publisher."""
        declared = HandlerView(fn, self._manager.adapter).return_model
        out_model = None
        if declared is not None and self._manager.identifies(declared):
            self._manager.reconcile_model(declared)
            out_model = self._manager.resolve_target_model(declared, self._target)
        converger = self._result_converger or ReturnConverger(
            self._runtime,
            self._target,
            out_model=out_model,
        )
        return self._broker.publisher(*self._topics, **self._options)(
            converger.wrap(fn)
        )


class RoutePublisher:
    """Bind one handler that converges independently for each route."""

    def __init__(
        self,
        broker: Any,
        runtime: FastStreamRuntime,
        routes: Mapping[str, TargetPolicy],
        *,
        version_header: str = "content-version",
    ) -> None:
        self._broker = broker
        self._runtime = runtime
        self._manager = runtime.manager
        self._routes = dict(routes)
        self._version_header = version_header

    def bind(self, fn: Fn) -> Fn:
        """Wrap the handler and register route-specific publishing."""
        declared = HandlerView(fn, self._manager.adapter).return_model
        if declared is not None and self._manager.identifies(declared):
            self._manager.reconcile_model(declared)

        @wraps(fn)
        async def routed(*args: Any, **kwargs: Any) -> None:
            result = await fn(*args, **kwargs)
            if result is None:
                return
            payload = self._runtime.dump(result)
            source_model = type(result)
            if not self._runtime.manager.adapter.can_handle(source_model):
                source_model = None
            for topic, target in self._routes.items():
                converged = await self._runtime.converge(
                    payload,
                    target,
                    source_model=source_model,
                )
                version = converged.get("version")
                headers: dict[str, Any] = {}
                if version is not None:
                    headers[self._version_header] = str(version)
                await self._broker.publish(converged, topic, headers=headers)

        annotations = dict(getattr(fn, "__annotations__", {}))
        annotations["return"] = type(None)
        routed.__annotations__ = annotations
        setattr(
            routed,
            "__signature__",
            inspect.signature(fn).replace(return_annotation=type(None)),
        )
        return cast("Fn", routed)


def publisher(
    broker: Any,
    *topics: str,
    runtime: FastStreamRuntime,
    target: TargetPolicy = "latest",
    result_converger: ResultConverger | None = None,
    **options: Any,
) -> Callable[[Fn], Any]:
    binding = PublisherBinding(
        broker,
        runtime,
        topics,
        target=target,
        result_converger=result_converger,
        options=options,
    )
    return binding.bind


def publish_to(
    broker: Any,
    *,
    runtime: FastStreamRuntime,
    routes: Mapping[str, TargetPolicy],
    version_header: str = "content-version",
) -> Callable[[Fn], Fn]:
    binding = RoutePublisher(
        broker,
        runtime,
        routes,
        version_header=version_header,
    )
    return binding.bind


__all__ = [
    "PublisherBinding",
    "ReturnConverger",
    "RoutePublisher",
    "publish_to",
    "publisher",
]
