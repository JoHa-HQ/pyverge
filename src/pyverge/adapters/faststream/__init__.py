"""FastStream adapter: converge message bodies to a target version.

FastStream is a broker-agnostic async messaging framework; its subscribers
receive JSON bodies written at some schema version. pyverge's ``Manager``
converges each body to the consumer's target version before the handler runs —
and can converge the handler's return to an outgoing target on publish.

The adapter is split by responsibility (ports & adapters):

* :mod:`.types` — host-neutral ports plus transport values and decorator ports.
* :mod:`.views` — FastStream wrappers implementing those ports.
* :mod:`.binding` — the default ``HandlerBinder``.
* :mod:`.subscriber` — the consume decorator (converges in FastStream's decoder).
* :mod:`.publisher` — the produce decorator (in/out).

FastStream is imported only here; pyverge core and providers never import it.
"""

from __future__ import annotations

from .binding import SignatureBinder
from .publisher import ReturnConverger, publish_to, publisher
from .source import (
    FastStreamProvider,
    FastStreamSource,
    PublisherProvider,
    SubscriberProvider,
)
from .subscriber import subscriber
from .targets import (
    DefaultTarget,
    FirstMatch,
    HeaderTarget,
    TopicTarget,
)
from .types import (
    Fn,
    HandlerBinder,
    HandlerPort,
    HeaderParser,
    MessageHeaders,
    NegotiationError,
    PayloadDumper,
    PublisherPort,
    ResultConverger,
    SubscriberPort,
    TargetContext,
    TargetSelector,
    TopicTargets,
)
from .views import FastStreamSubscriber, HandlerView

__all__ = [
    "DefaultTarget",
    "FastStreamProvider",
    "FastStreamSource",
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
    "PublisherProvider",
    "ResultConverger",
    "ReturnConverger",
    "SignatureBinder",
    "SubscriberPort",
    "SubscriberProvider",
    "TargetContext",
    "TargetSelector",
    "TopicTarget",
    "TopicTargets",
    "publish_to",
    "publisher",
    "subscriber",
]
