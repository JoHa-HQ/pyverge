"""Framework-agnostic core for serving versioned payloads as tools.

A host framework (FastMCP, raw MCP, …) reflects its own primitives — a tool's
input schema, a prompt's arguments — and this package turns that reflected shape
into the pyverge pieces that do the real work:

* :mod:`.injection` — tell injected (wired) parameters apart from payload,
* :mod:`.reflection` — wrap a schema document as a versioned model,
* :mod:`.contract` — validate a reflected schema against the registered graph,
* :mod:`.convergence` — resolve and run a converging tool call.

The host adapter keeps only the context wiring: discovery, dispatch, transport.
"""

from .contract import ServingContract
from .convergence import Converger, HandlerFor
from .injection import (
    InjectionDetector,
    default_injection_detector,
    injected_names,
    marker_detector,
    never_injected,
)
from .reflection import SchemaReflection

__all__ = [
    "Converger",
    "HandlerFor",
    "InjectionDetector",
    "SchemaReflection",
    "ServingContract",
    "default_injection_detector",
    "injected_names",
    "marker_detector",
    "never_injected",
]
