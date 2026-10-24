"""The endpoint decorator: bind a convergence policy to a subscriber.

One decorator at the endpoint, pyverge config as keyword arguments. It resolves
the handler's typed parameter (the kind) to the *target* version's model — a
reconstructed class when the target is not the anchor — binds the parameter to
it, and registers the subscriber with a convergence ``decoder``. The handler thus
validates the converged payload against the version actually served.
"""

from __future__ import annotations

import operator
from collections.abc import Callable
from functools import reduce
from typing import Any, TypeVar

from pyverge import Manager
from pyverge.manager.types import TargetPolicy

from .binding import SignatureBinder
from .targets import DEFAULT_TARGET, FirstMatch
from .types import HandlerBinder, TargetContext, TopicTargets
from .views import HandlerView

Fn = TypeVar("Fn", bound=Callable[..., Any])


def _model_union(models: list[Any]) -> Any:
    """Return one model or the union of all candidate models."""
    unique = list(dict.fromkeys(models))
    if not unique:
        return None
    return reduce(operator.or_, unique)


def _candidate_models(
    manager: Manager,
    declared: Any,
    targets: TargetPolicy | TopicTargets,
    topics: tuple[str, ...],
    header: str | None,
) -> list[Any]:
    kind = manager.get_model(declared).kind
    if header is not None:
        return [version.model for version in manager.list_versions(kind)]
    if isinstance(targets, TopicTargets):
        found: list[Any] = []
        for topic in topics:
            target = targets.get(topic)
            if target is None:
                continue
            model = manager.resolve_target_model(declared, target)
            if model is not None:
                found.append(model)
        return found
    model = manager.resolve_target_model(declared, targets)
    return [model] if model is not None else []


def subscriber(
    broker: Any,
    *topics: str,
    manager: Manager,
    targets: TargetPolicy | TopicTargets = DEFAULT_TARGET,
    header: str | None = None,
    binder: HandlerBinder | None = None,
    **options: Any,
) -> Callable[[Fn], Fn]:
    """Register one converging subscriber per topic.

    ``targets`` is either one policy for every topic or a :class:`TopicTargets`
    mapping. ``header`` enables per-message negotiation, overriding both.
    Extra *options* pass through to ``broker.subscriber``.
    """
    if "decoder" in options:
        raise TypeError("subscriber() owns the decoder; drop the decoder option")

    selector = FirstMatch.for_topics(topics, targets, header)
    binder = binder or SignatureBinder()

    def decode(topic: str) -> Callable[[Any, Any], Any]:
        async def converge_message(msg: Any, next_decoder: Any) -> dict[str, Any]:
            payload = await next_decoder(msg)
            target = selector.select(
                TargetContext(topic, getattr(msg, "headers", {}) or {})
            )
            return await manager.prepare(payload, target=target).arun()

        return converge_message

    def decorate(fn: Fn) -> Fn:
        declared = HandlerView(fn).input_model
        if declared is not None and manager.identifies(declared):
            models = _candidate_models(manager, declared, targets, topics, header)
            annotation = _model_union(models)
            if annotation is not None:
                binder.bind(fn, annotation)
        for topic in topics:
            broker.subscriber(topic, decoder=decode(topic), **options)(fn)
        return fn

    return decorate


__all__ = ["subscriber"]
