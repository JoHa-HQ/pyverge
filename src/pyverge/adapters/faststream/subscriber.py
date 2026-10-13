"""The endpoint decorator: bind a convergence policy to a subscriber.

One decorator at the endpoint, pyverge config as keyword arguments. It resolves
the handler's typed parameter (the kind) to the *target* version's model — a
reconstructed class when the target is not the anchor — binds the parameter to
it, and registers the subscriber with a convergence ``decoder``. The handler thus
validates the converged payload against the version actually served.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from pyverge import Manager
from pyverge.manager.types import TargetPolicy

from .binding import SignatureBinder
from .convergence import Converger
from .reflection import typed_model
from .types import HandlerBinder

Fn = TypeVar("Fn", bound=Callable[..., Any])


def subscriber(
    broker: Any,
    *topics: str,
    manager: Manager,
    target: TargetPolicy = "latest",
    binder: HandlerBinder | None = None,
    **options: Any,
) -> Callable[[Fn], Fn]:
    """Return a decorator registering a converging subscriber on *broker*.

    Applied at the endpoint; the body is converged to *target* before the
    handler runs. Parsing is FastStream's (via its injected default decoder).
    Extra *options* pass through to ``broker.subscriber`` (e.g. ``group_id``),
    except the decoder, which pyverge owns.
    """
    if "decoder" in options:
        raise TypeError("subscriber() owns the decoder; drop the decoder option")

    converger = Converger(manager, target)

    async def decode(msg: Any, next_decoder: Any) -> dict[str, Any]:
        # Two parameters on purpose: FastStream binds its default decoder as
        # ``next_decoder`` (its ``ParserComposition``), so parsing stays
        # FastStream's — any content type — and only convergence lives here.
        return converger.converge(await next_decoder(msg))

    binder = binder or SignatureBinder()

    def decorate(fn: Fn) -> Fn:
        declared_handler = getattr(fn, "_original_call", fn)
        declared = typed_model(declared_handler)
        if declared is not None and manager.identifies(declared):
            resolved = manager.resolve_target_model(declared, target)
            if resolved is not None:
                binder.bind(declared_handler, resolved)
        return broker.subscriber(*topics, decoder=decode, **options)(fn)

    return decorate


__all__ = ["subscriber"]
