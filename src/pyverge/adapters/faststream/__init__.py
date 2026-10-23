"""FastStream adapter: converge message bodies to a target version.

FastStream is a broker-agnostic async messaging framework; its subscribers
receive JSON bodies written at some schema version. pyverge's ``Manager``
converges each body to the consumer's target version before the handler runs —
and can converge the handler's return to an outgoing target on publish.

The adapter is split by responsibility (ports & adapters):

* :mod:`.ports` — host-neutral handler, subscriber, and publisher ports.
* :mod:`.views` — FastStream wrappers implementing those ports.
* :mod:`.types` — transport values and decorator ports.
* :mod:`.binding` — the default ``HandlerBinder``.
* :mod:`.subscriber` — the consume decorator (converges in FastStream's decoder).
* :mod:`.publisher` — the produce decorator (in/out).
* :mod:`.reflection` — ``SubscriberWalker`` / ``Reflector``.

FastStream is imported only here; pyverge core and providers never import it.
"""

from __future__ import annotations

from .binding import SignatureBinder
from .ports import HandlerPort, PublisherPort, SubscriberPort
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
from .views import FastStreamSubscriber, HandlerView, PublisherView

__all__ = [
    "DEFAULT_TARGET",
    "DEFAULT_VERSION_HEADER",
    "DefaultTarget",
    "FastStreamSubscriber",
    "FirstMatch",
    "Fn",
    "HandlerBinder",
    "HandlerPort",
    "HandlerView",
    "HeaderParser",
    "HeaderTarget",
    "MessageHeaders",
    "NegotiationError",
    "PayloadDumper",
    "PublisherPort",
    "PublisherView",
    "Reflector",
    "ResultConverger",
    "ReturnConverger",
    "SignatureBinder",
    "SubscriberModel",
    "SubscriberPort",
    "SubscriberWalker",
    "TargetContext",
    "TargetSelector",
    "TopicTarget",
    "TopicTargets",
    "publish_to",
    "publisher",
    "subscriber",
]
