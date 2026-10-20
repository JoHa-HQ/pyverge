"""FastStream adapter: converge message bodies to a target version.

FastStream is a broker-agnostic async messaging framework; its subscribers
receive JSON bodies written at some schema version. pyverge's ``Manager``
converges each body to the consumer's target version before the handler runs —
and can converge the handler's return to an outgoing target on publish.

The adapter is split by responsibility (ports & adapters):

* :mod:`.types` — the ports (``HandlerBinder``, ``ResultConverger``).
* :mod:`.binding` — the default ``HandlerBinder``.
* :mod:`.subscriber` — the consume decorator (converges in FastStream's decoder).
* :mod:`.publisher` — the produce decorator (in/out).
* :mod:`.reflection` — ``SubscriberWalker`` / ``Reflector``.

FastStream is imported only here; pyverge core and providers never import it.
"""

from __future__ import annotations

from .binding import SignatureBinder
from .publisher import ReturnConverger, publish_to, publisher
from .reflection import Reflector, SubscriberModel, SubscriberWalker
from .subscriber import subscriber
from .targets import (
    DEFAULT_TARGET,
    DEFAULT_VERSION_HEADER,
    DefaultTarget,
    FirstMatch,
    HeaderTarget,
    TopicTarget,
)
from .types import (
    Fn,
    HandlerBinder,
    HeaderParser,
    MessageHeaders,
    NegotiationError,
    PayloadDumper,
    ResultConverger,
    TargetContext,
    TargetSelector,
    TopicTargets,
)

__all__ = [
    "DEFAULT_TARGET",
    "DEFAULT_VERSION_HEADER",
    "DefaultTarget",
    "FirstMatch",
    "Fn",
    "HandlerBinder",
    "HeaderParser",
    "HeaderTarget",
    "MessageHeaders",
    "NegotiationError",
    "PayloadDumper",
    "Reflector",
    "ResultConverger",
    "ReturnConverger",
    "SignatureBinder",
    "SubscriberModel",
    "SubscriberWalker",
    "TargetContext",
    "TargetSelector",
    "TopicTarget",
    "TopicTargets",
    "publish_to",
    "publisher",
    "subscriber",
]
