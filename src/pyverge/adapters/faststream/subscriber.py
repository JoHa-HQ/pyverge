from __future__ import annotations

import operator
from collections.abc import Callable, Mapping
from functools import reduce
from typing import Any, TypeVar

from pyverge.manager.types import TargetPolicy

from .domain import TargetContext, TopicTargets
from .handlers import HandlerView, SignatureBinder
from .ports import HandlerBinder, TargetSelector
from .runtime import FastStreamRuntime
from .targets import FirstMatch

Fn = TypeVar("Fn", bound=Callable[..., Any])


class _MessageConverger:
    """Build FastStream decoders that converge before the handler."""

    def __init__(self, runtime: FastStreamRuntime, selector: TargetSelector) -> None:
        self._runtime = runtime
        self._selector = selector

    def decoder(self, topic: str) -> Callable[[Any, Any], Any]:
        """Return the decoder for one topic."""
        selector = self._selector

        async def converge_message(msg: Any, next_decoder: Any) -> dict[str, Any]:
            payload = await next_decoder(msg)
            target = selector.select(
                TargetContext(topic, getattr(msg, "headers", {}) or {})
            )
            return await self._runtime.converge(
                payload,
                target,
                context=self._runtime.context_for(msg),
            )

        return converge_message


class SubscriberBinding:
    """Bind one handler to one or more converging FastStream subscribers.

    The binding owns the manager, runtime, selector, binder, and broker
    registration for a single decorator call. :func:`subscriber` is only a
    thin factory over it.
    """

    def __init__(  # noqa: PLR0913
        self,
        broker: Any,
        runtime: FastStreamRuntime,
        topics: tuple[str, ...],
        *,
        targets: TargetPolicy | TopicTargets = "latest",
        header: str | None = None,
        selector: TargetSelector | None = None,
        binder: HandlerBinder | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> None:
        self._broker = broker
        self._runtime = runtime
        self._manager = runtime.manager
        self._topics = topics
        self._targets = targets
        self._header = header
        self._explicit_selector = selector is not None
        self._selector = selector or FirstMatch.for_topics(
            topics, targets, default_target="latest", header=header
        )
        self._binder = binder or SignatureBinder()
        self._converger = _MessageConverger(self._runtime, self._selector)
        self._options = dict(options or {})

    def bind(self, fn: Fn) -> Fn:
        """Declare the handler, bind its model, and register the subscribers."""
        declared = HandlerView(fn, self._manager.adapter).input_model
        if declared is not None and self._manager.identifies(declared):
            self._manager.reconcile_model(declared)
            if not self._explicit_selector:
                self._bind_annotation(fn, declared)
        self._register(fn)
        return fn

    def _bind_annotation(self, fn: Fn, declared: Any) -> None:
        unique = list(dict.fromkeys(self._candidate_models(declared)))
        if not unique:
            return
        self._binder.bind(fn, reduce(operator.or_, unique))

    def _candidate_models(self, declared: Any) -> list[Any]:
        manager = self._manager
        kind = manager.get_model(declared).kind
        if self._header is not None:
            return [
                manager.engine.adapter.resolve(version.descriptor.ref)
                for version in manager.list_versions(kind)
            ]
        if isinstance(self._targets, TopicTargets):
            found: list[Any] = []
            for topic in self._topics:
                target = self._targets.get(topic)
                if target is None:
                    continue
                model = manager.resolve_target_model(declared, target)
                if model is not None:
                    found.append(model)
            return found
        model = manager.resolve_target_model(declared, self._targets)
        return [model] if model is not None else []

    def _register(self, fn: Fn) -> None:
        for topic in self._topics:
            self._broker.subscriber(
                topic,
                decoder=self._converger.decoder(topic),
                **self._options,
            )(fn)


def subscriber(  # noqa: PLR0913
    broker: Any,
    *topics: str,
    runtime: FastStreamRuntime,
    targets: TargetPolicy | TopicTargets = "latest",
    header: str | None = None,
    selector: TargetSelector | None = None,
    binder: HandlerBinder | None = None,
    **options: Any,
) -> Callable[[Fn], Fn]:
    if "decoder" in options:
        raise TypeError("subscriber() owns the decoder; drop the decoder option")

    binding = SubscriberBinding(
        broker,
        runtime,
        topics,
        targets=targets,
        header=header,
        selector=selector,
        binder=binder,
        options=options,
    )
    return binding.bind


__all__ = ["SubscriberBinding", "subscriber"]
