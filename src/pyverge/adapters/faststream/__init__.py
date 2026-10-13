"""FastStream adapter: converge message bodies to a target version.

FastStream is a broker-agnostic async messaging framework; its subscribers
receive JSON bodies written at some schema version. pyverge's ``Manager``
converges each body to the consumer's target version before the handler runs —
and can converge the handler's return to an outgoing target on publish.

The adapter is split by responsibility (ports & adapters):

* :mod:`.types` — the ports (``HandlerBinder``, ``ResultConverger``).
* :mod:`.binding` — the default ``HandlerBinder``.
* :mod:`.convergence` — the ``Converger`` application service.
* :mod:`.subscriber` — the consume decorator (converges in FastStream's decoder).
* :mod:`.publisher` — the produce decorator (in/out).
* :mod:`.reflection` — ``SubscriberWalker`` / ``Reflector``.

FastStream is imported only here; pyverge core and providers never import it.
"""

from __future__ import annotations

from .binding import SignatureBinder
from .convergence import Converger
from .publisher import ReturnConverger, publisher
from .reflection import ReflectedSubscriber, Reflector, SubscriberWalker
from .subscriber import subscriber
from .types import (
    Fn,
    HandlerBinder,
    PayloadDumper,
    ResultConverger,
)

__all__ = [
    "Converger",
    "Fn",
    "HandlerBinder",
    "PayloadDumper",
    "ReflectedSubscriber",
    "Reflector",
    "ResultConverger",
    "ReturnConverger",
    "SignatureBinder",
    "SubscriberWalker",
    "publisher",
    "subscriber",
]
